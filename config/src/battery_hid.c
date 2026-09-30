/*
 * Exposes the left and right split-half battery levels of the Hitek68
 * keyboard to the host over USB, since ZMK only reports battery over BLE.
 *
 * The dongle (central) presents an extra USB HID vendor interface
 * (Usage Page 0xFF00) that pushes a 3-byte INPUT report
 * [0x01, left%, right%] (0xFF = unknown) on every peripheral battery
 * event AND every 10 seconds, so a host reader that (re)connects
 * sees values within one interval.
 *
 * Left/right is auto-detected from keystroke positions: Hitek68 uses
 * a 96-position layout where positions 0-47 are the left half and
 * 48-95 are the right half. The first keypress from a peripheral slot
 * reveals its physical side.
 *
 * Dongle (central) build only. Requires CONFIG_USB_HID_DEVICE_COUNT=2.
 */

#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/device.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/usb/usb_device.h>
#include <zephyr/usb/class/usb_hid.h>
#include <zephyr/logging/log.h>

#include <zmk/event_manager.h>
#include <zmk/events/battery_state_changed.h>
#include <zmk/events/position_state_changed.h>

LOG_MODULE_REGISTER(hitek68_battery_hid, CONFIG_ZMK_LOG_LEVEL);

#define REPORT_ID_BATTERY 0x01
#define REPORT_ID_COMMAND 0x02
#define BATTERY_UNKNOWN 0xFF

/* Command IDs (in output report) */
#define CMD_SET_DEBOUNCE 0x01
#define CMD_SET_SLEEP 0x02

/* Target: 0=both halves, 1=left, 2=right */
#define TARGET_BOTH 0
#define TARGET_LEFT 1
#define TARGET_RIGHT 2

/* Vendor HID report descriptor: Usage Page 0xFF00.
 * - Input report 0x01: two battery bytes [left%, right%]
 * - Output report 0x02: 7-byte command [cmd, target, d0..d4] */
static const uint8_t vendor_report_desc[] = {
    0x06, 0x00, 0xFF,        /* Usage Page (Vendor-Defined 0xFF00) */
    0x09, 0x01,              /* Usage (0x01) */
    0xA1, 0x01,              /* Collection (Application) */
    0x85, REPORT_ID_BATTERY, /* Report ID (1) */
    0x15, 0x00,              /* Logical Minimum (0) */
    0x26, 0xFF, 0x00,        /* Logical Maximum (255) */
    0x75, 0x08,              /* Report Size (8) */
    0x95, 0x02,              /* Report Count (2) */
    0x09, 0x01,              /* Usage (0x01) — left battery */
    0x09, 0x02,              /* Usage (0x02) — right battery */
    0x81, 0x02,              /* Input (Data, Variable, Absolute) */
    0x85, REPORT_ID_COMMAND, /* Report ID (2) */
    0x09, 0x03,              /* Usage (0x03) — command */
    0x95, 0x07,              /* Report Count (7) */
    0x91, 0x02,              /* Output (Data, Variable, Absolute) */
    0xC0,                    /* End Collection */
};

/* Latest state of charge per peripheral slot (slot order = bonding order). */
static uint8_t levels[2] = {BATTERY_UNKNOWN, BATTERY_UNKNOWN};

/* Which slot is the physical LEFT half. Auto-detected from key positions. */
static uint8_t left_slot = 0;

/* Public accessor for the settings relay (target selection). */
uint8_t hitek68_battery_left_slot(void) { return left_slot; }

/* Hitek68: positions 0-47 are left half, 48-95 are right half. */
static bool position_is_left(uint32_t position) { return position < 48; }

/* USB HID device and write synchronization */
static const struct device *hid_dev;
static struct k_sem hid_sem;
static uint8_t hid_buf[3] = {REPORT_ID_BATTERY, BATTERY_UNKNOWN, BATTERY_UNKNOWN};
static uint8_t hid_timeouts;

#define SEM_STRANDED_THRESHOLD 3

static void int_in_ready_cb(const struct device *dev) {
    ARG_UNUSED(dev);
    k_sem_give(&hid_sem);
}

/* Relay API (settings_relay.c). Weak stubs if relay not built. */
__weak int hitek68_relay_set_debounce(uint8_t target, uint32_t press_ms, uint32_t release_ms) {
    ARG_UNUSED(target);
    ARG_UNUSED(press_ms);
    ARG_UNUSED(release_ms);
    return -ENOSYS;
}
__weak int hitek68_relay_set_sleep(uint8_t target, uint32_t timeout_ms) {
    ARG_UNUSED(target);
    ARG_UNUSED(timeout_ms);
    return -ENOSYS;
}

/* Handle HID output reports (commands from host app). */
static int set_report_cb(const struct device *dev, struct usb_setup_packet *setup, int32_t *len,
                         uint8_t **data) {
    ARG_UNUSED(dev);

    /* We only handle Output reports via control pipe (SET_REPORT). */
    if ((setup->bmRequestType & USB_REQTYPE_TYPE_MASK) != USB_REQTYPE_TYPE_CLASS) {
        return -ENOTSUP;
    }
    uint8_t report_id = setup->wValue & 0xFF;
    if (report_id != REPORT_ID_COMMAND) {
        return -ENOTSUP;
    }

    /* Output report: [cmd, target, d0, d1, d2, d3, d4] (7 bytes, ID stripped) */
    if (*len < 7) {
        LOG_WRN("Command report too short: %d", *len);
        return -EINVAL;
    }
    uint8_t *r = *data;
    uint8_t cmd = r[0];
    uint8_t target = r[1];

    if (target > TARGET_RIGHT) {
        LOG_WRN("Invalid target: %u", target);
        return -EINVAL;
    }

    switch (cmd) {
    case CMD_SET_DEBOUNCE: {
        uint16_t press = sys_get_le16(&r[2]);
        uint16_t release = sys_get_le16(&r[4]);
        LOG_INF("CMD set debounce: target=%u press=%u release=%u", target, press, release);
        hitek68_relay_set_debounce(target, press, release);
        break;
    }
    case CMD_SET_SLEEP: {
        uint32_t timeout = sys_get_le32(&r[2]);
        LOG_INF("CMD set sleep: target=%u timeout=%u", target, timeout);
        hitek68_relay_set_sleep(target, timeout);
        break;
    }
    default:
        LOG_WRN("Unknown command: 0x%02x", cmd);
        return -EINVAL;
    }
    return 0;
}

static const struct hid_ops hid_ops = {
    .int_in_ready = int_in_ready_cb,
    .set_report = set_report_cb,
};

static int send_battery_report(void) {
    if (!hid_dev) {
        return -ENODEV;
    }

    if (k_sem_take(&hid_sem, K_MSEC(100)) != 0) {
        if (++hid_timeouts < SEM_STRANDED_THRESHOLD) {
            return -EBUSY;
        }
        LOG_WRN("HID completion stranded; recovering");
        k_sem_reset(&hid_sem);
    }
    hid_timeouts = 0;

    /* Emit in true [left, right] order using auto-detected slot mapping */
    hid_buf[1] = levels[left_slot];
    hid_buf[2] = levels[left_slot ^ 1];

    int err = hid_int_ep_write(hid_dev, hid_buf, sizeof(hid_buf), NULL);
    if (err) {
        k_sem_give(&hid_sem);
        LOG_ERR("hid_int_ep_write failed: %d", err);
        return err;
    }
    return 0;
}

static int hitek68_battery_hid_init(void) {
    /* ZMK creates hid devices as "HID_0", "HID_1", etc.
     * HID_0 is ZMK's keyboard; ours is HID_1. */
    hid_dev = device_get_binding("HID_1");
    if (!hid_dev) {
        LOG_ERR("HID_1 not found — is CONFIG_USB_HID_DEVICE_COUNT=2?");
        return -ENODEV;
    }

    /* Register the device with its report descriptor and ops.
     * This must be done before usb_hid_init(). */
    usb_hid_register_device(hid_dev, vendor_report_desc,
                            sizeof(vendor_report_desc), &hid_ops);

    int err = usb_hid_init(hid_dev);
    if (err) {
        LOG_ERR("usb_hid_init failed: %d", err);
        return err;
    }

    k_sem_init(&hid_sem, 1, 1);

    LOG_INF("Hitek68 battery HID interface initialized");
    return 0;
}

SYS_INIT(hitek68_battery_hid_init, APPLICATION, 91);

/* Periodic resend so newly-connected host readers eventually get values */
#define RESEND_INTERVAL_S 10

static void resend_work_cb(struct k_work *work) {
    ARG_UNUSED(work);
    send_battery_report();
}
K_WORK_DEFINE(resend_work, resend_work_cb);

static void resend_timer_cb(struct k_timer *timer) {
    ARG_UNUSED(timer);
    k_work_submit(&resend_work);
}
K_TIMER_DEFINE(resend_timer, resend_timer_cb, NULL);

static int start_resend_timer(void) {
    k_timer_start(&resend_timer, K_SECONDS(RESEND_INTERVAL_S),
                  K_SECONDS(RESEND_INTERVAL_S));
    return 0;
}
SYS_INIT(start_resend_timer, APPLICATION, 92);

/* Event listener: battery updates and key positions for L/R detection */
static int battery_listener(const zmk_event_t *eh) {
    const struct zmk_peripheral_battery_state_changed *bat_ev =
        as_zmk_peripheral_battery_state_changed(eh);
    if (bat_ev) {
        if (bat_ev->source < 2) {
            levels[bat_ev->source] = bat_ev->state_of_charge;
            /* Defer USB write to work queue (we're in BT RX thread) */
            k_work_submit(&resend_work);
            LOG_DBG("battery src=%u soc=%u", bat_ev->source,
                    bat_ev->state_of_charge);
        }
        return ZMK_EV_EVENT_BUBBLE;
    }

    const struct zmk_position_state_changed *pos_ev =
        as_zmk_position_state_changed(eh);
    if (pos_ev && pos_ev->source < 2) {
        uint8_t detected =
            position_is_left(pos_ev->position) ? pos_ev->source : (pos_ev->source ^ 1);
        if (detected != left_slot) {
            left_slot = detected;
            LOG_INF("left half detected in slot %u", left_slot);
            k_work_submit(&resend_work);
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(hitek68_battery_listener, battery_listener);
ZMK_SUBSCRIPTION(hitek68_battery_listener, zmk_peripheral_battery_state_changed);
ZMK_SUBSCRIPTION(hitek68_battery_listener, zmk_position_state_changed);
