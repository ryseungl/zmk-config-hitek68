/*
 * Hitek68 settings relay (dongle, central role).
 *
 * Receives settings commands from the USB host (via HID output reports on
 * the vendor interface) and relays them to connected split halves over BLE
 * by writing to their Hitek68 settings GATT characteristics.
 *
 * Target: 0 = all connected halves, 1 = left half, 2 = right half.
 * Left/right uses the battery module's auto-detected slot mapping.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(hitek68_settings_relay, CONFIG_ZMK_LOG_LEVEL);

/* Must match hitek68_settings_gatt.c */
#define HITEK68_SETTINGS_SVC_UUID \
    BT_UUID_128_ENCODE(0x6e400001, 0xb5a3, 0xf393, 0xe0a9, 0xe50e24dcca9e)
#define HITEK68_SETTINGS_DEBOUNCE_UUID \
    BT_UUID_128_ENCODE(0x6e400002, 0xb5a3, 0xf393, 0xe0a9, 0xe50e24dcca9e)
#define HITEK68_SETTINGS_SLEEP_UUID \
    BT_UUID_128_ENCODE(0x6e400003, 0xb5a3, 0xf393, 0xe0a9, 0xe50e24dcca9e)

#define MAX_PERIPHERALS 2

struct hitek68_peripheral {
    struct bt_conn *conn;
    uint16_t debounce_handle;
    uint16_t sleep_handle;
    bool discovering;
    struct k_work_delayable discover_work;
};

static struct hitek68_peripheral peripherals[MAX_PERIPHERALS];

/* Forward: from battery_hid.c — which slot is the left half. */
extern uint8_t hitek68_battery_left_slot(void);

static struct hitek68_peripheral *periph_for_conn(struct bt_conn *conn) {
    for (int i = 0; i < MAX_PERIPHERALS; i++) {
        if (peripherals[i].conn == conn) {
            return &peripherals[i];
        }
    }
    return NULL;
}

static struct hitek68_peripheral *periph_alloc(struct bt_conn *conn) {
    for (int i = 0; i < MAX_PERIPHERALS; i++) {
        if (peripherals[i].conn == NULL) {
            peripherals[i].conn = bt_conn_ref(conn);
            peripherals[i].debounce_handle = 0;
            peripherals[i].sleep_handle = 0;
            peripherals[i].discovering = false;
            k_work_init_delayable(&peripherals[i].discover_work, discover_work_cb);
            return &peripherals[i];
        }
    }
    return NULL;
}

static void periph_free(struct bt_conn *conn) {
    struct hitek68_peripheral *p = periph_for_conn(conn);
    if (p) {
        bt_conn_unref(p->conn);
        p->conn = NULL;
        p->debounce_handle = 0;
        p->sleep_handle = 0;
        p->discovering = false;
    }
}

/* ---- GATT discovery ---- */

struct discover_ctx {
    struct hitek68_peripheral *periph;
    struct bt_gatt_discover_params params;
};

static uint8_t chrc_discover_func(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                                  struct bt_gatt_discover_params *params) {
    struct discover_ctx *ctx = CONTAINER_OF(params, struct discover_ctx, params);
    struct hitek68_peripheral *p = ctx->periph;

    if (!attr) {
        /* Discovery complete */
        p->discovering = false;
        LOG_INF("Settings discovery complete: debounce_handle=%u sleep_handle=%u",
                p->debounce_handle, p->sleep_handle);
        return BT_GATT_ITER_STOP;
    }

    struct bt_gatt_chrc *chrc = attr->user_data;
    const struct bt_uuid *uuid = chrc->uuid;

    struct bt_uuid_128 debounce_uuid = BT_UUID_INIT_128(HITEK68_SETTINGS_DEBOUNCE_UUID);
    struct bt_uuid_128 sleep_uuid = BT_UUID_INIT_128(HITEK68_SETTINGS_SLEEP_UUID);

    if (!bt_uuid_cmp(uuid, &debounce_uuid.uuid)) {
        p->debounce_handle = chrc->value_handle;
        LOG_DBG("Found debounce char: handle %u", chrc->value_handle);
    } else if (!bt_uuid_cmp(uuid, &sleep_uuid.uuid)) {
        p->sleep_handle = chrc->value_handle;
        LOG_DBG("Found sleep char: handle %u", chrc->value_handle);
    }

    return BT_GATT_ITER_CONTINUE;
}

static uint8_t svc_discover_func(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                                 struct bt_gatt_discover_params *params) {
    struct discover_ctx *ctx = CONTAINER_OF(params, struct discover_ctx, params);
    struct hitek68_peripheral *p = ctx->periph;

    if (!attr) {
        p->discovering = false;
        LOG_WRN("Settings service not found on peripheral");
        return BT_GATT_ITER_STOP;
    }

    struct bt_gatt_service_val *svc = attr->user_data;

    /* Now discover characteristics within the service */
    ctx->params.uuid = NULL;
    ctx->params.start_handle = attr->handle + 1;
    ctx->params.end_handle = svc->end_handle;
    ctx->params.type = BT_GATT_DISCOVER_CHARACTERISTIC;
    ctx->params.func = chrc_discover_func;

    int err = bt_gatt_discover(conn, &ctx->params);
    if (err) {
        LOG_ERR("Characteristic discovery failed: %d", err);
        p->discovering = false;
    }

    return BT_GATT_ITER_STOP;
}

/* Discovery contexts (one per peripheral, static to avoid alloc) */
static struct discover_ctx disc_ctx[MAX_PERIPHERALS];

static void start_discovery(struct hitek68_peripheral *periph) {
    if (periph->discovering) {
        return;
    }

    int idx = periph - peripherals;
    struct discover_ctx *ctx = &disc_ctx[idx];

    ctx->periph = periph;
    ctx->params.uuid = BT_UUID_DECLARE_128(HITEK68_SETTINGS_SVC_UUID);
    ctx->params.func = svc_discover_func;
    ctx->params.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
    ctx->params.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
    ctx->params.type = BT_GATT_DISCOVER_PRIMARY;

    periph->discovering = true;
    int err = bt_gatt_discover(periph->conn, &ctx->params);
    if (err) {
        LOG_ERR("Service discovery failed: %d", err);
        periph->discovering = false;
    }
}

/* ---- Connection tracking ---- */

static void connected_cb(struct bt_conn *conn, uint8_t err) {
    if (err) {
        return;
    }
    /* Only track peripheral connections (dongle is central, so all LE
     * connections here are to halves). */
    struct hitek68_peripheral *p = periph_alloc(conn);
    if (p) {
        LOG_INF("Peripheral connected, starting settings discovery");
        /* Delay discovery slightly to let ZMK's own discovery finish first */
        k_work_reschedule(&p->discover_work, K_SECONDS(2));
    }
}

static void disconnected_cb(struct bt_conn *conn, uint8_t reason) {
    ARG_UNUSED(reason);
    periph_free(conn);
    LOG_INF("Peripheral disconnected");
}

BT_CONN_CB_DEFINE(conn_cbs) = {
    .connected = connected_cb,
    .disconnected = disconnected_cb,
};

/* Work to start discovery (can't do GATT ops directly in connected callback) */
static void discover_work_cb(struct k_work *work) {
    struct k_work_delayable *dwork = k_work_delayable_from_work(work);
    struct hitek68_peripheral *p =
        CONTAINER_OF(dwork, struct hitek68_peripheral, discover_work);
    if (p->conn) {
        start_discovery(p);
    }
}

/* ---- Public relay API (called from HID output report handler) ---- */

int hitek68_relay_set_debounce(uint8_t target, uint32_t press_ms, uint32_t release_ms) {
    uint8_t value[8];
    sys_put_le32(press_ms, &value[0]);
    sys_put_le32(release_ms, &value[4]);

    uint8_t left_slot = hitek68_battery_left_slot();
    int count = 0;

    for (int i = 0; i < MAX_PERIPHERALS; i++) {
        struct hitek68_peripheral *p = &peripherals[i];
        if (!p->conn || !p->debounce_handle) {
            continue;
        }
        /* Target filter: 0=all, 1=left, 2=right */
        if (target == 1 && i != left_slot) {
            continue;
        }
        if (target == 2 && i != (left_slot ^ 1)) {
            continue;
        }

        int err = bt_gatt_write_without_response(p->conn, p->debounce_handle, value,
                                                 sizeof(value), false);
        if (err) {
            LOG_ERR("Debounce write failed for slot %d: %d", i, err);
        } else {
            count++;
            LOG_INF("Debounce sent to slot %d: %u/%u ms", i, press_ms, release_ms);
        }
    }
    return count;
}

int hitek68_relay_set_sleep(uint8_t target, uint32_t timeout_ms) {
    uint8_t value[4];
    sys_put_le32(timeout_ms, value);

    uint8_t left_slot = hitek68_battery_left_slot();
    int count = 0;

    for (int i = 0; i < MAX_PERIPHERALS; i++) {
        struct hitek68_peripheral *p = &peripherals[i];
        if (!p->conn || !p->sleep_handle) {
            continue;
        }
        if (target == 1 && i != left_slot) {
            continue;
        }
        if (target == 2 && i != (left_slot ^ 1)) {
            continue;
        }

        int err =
            bt_gatt_write_without_response(p->conn, p->sleep_handle, value, sizeof(value), false);
        if (err) {
            LOG_ERR("Sleep write failed for slot %d: %d", i, err);
        } else {
            count++;
            LOG_INF("Sleep timeout sent to slot %d: %u ms", i, timeout_ms);
        }
    }
    return count;
}
