/*
 * Hitek68 runtime-adjustable deep sleep.
 *
 * Replaces ZMK's compile-time CONFIG_ZMK_IDLE_SLEEP_TIMEOUT with a RAM
 * variable that can be changed at runtime (and persists via hitek68_settings).
 * Halves keep CONFIG_ZMK_SLEEP=y (needed for zmk_pm_* and sys_poweroff) but
 * set CONFIG_ZMK_IDLE_SLEEP_TIMEOUT to max so only this code triggers sleep.
 *
 * Logic mirrors ZMK's activity.c: when idle longer than the timeout (and not
 * USB-powered), suspend devices and power off. Any keypress wakes (reset).
 */

#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/logging/log.h>

#include <zmk/event_manager.h>
#include <zmk/events/activity_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/events/sensor_event.h>
#include <zmk/pm.h>
#include <zmk/usb.h>

LOG_MODULE_REGISTER(hitek68_sleep, CONFIG_ZMK_LOG_LEVEL);

/* 0 = never sleep. Default 30 min, overridden by settings. */
static uint32_t sleep_timeout_ms = 1800000;

static int64_t last_activity_uptime;

void hitek68_sleep_set_timeout(uint32_t timeout_ms) {
    sleep_timeout_ms = timeout_ms;
    /* Reset the idle clock so a new (shorter) timeout doesn't fire instantly
     * on stale inactivity... actually no: keep the existing activity time so
     * shortening the timeout takes effect promptly. */
}

static bool usb_power_present(void) {
#if IS_ENABLED(CONFIG_USB_DEVICE_STACK)
    return zmk_usb_is_powered();
#else
    return false;
#endif
}

static void sleep_work_handler(struct k_work *work) {
    ARG_UNUSED(work);

    if (sleep_timeout_ms == 0) {
        return; /* Sleep disabled */
    }

    int64_t inactive_ms = k_uptime_get() - last_activity_uptime;

    if (inactive_ms > sleep_timeout_ms && !usb_power_present()) {
        LOG_INF("Idle %lld ms > timeout %u ms, suspending", inactive_ms, sleep_timeout_ms);

        raise_zmk_activity_state_changed(
            (struct zmk_activity_state_changed){.state = ZMK_ACTIVITY_SLEEP});

        if (zmk_pm_suspend_devices() < 0) {
            LOG_ERR("Failed to suspend devices");
            zmk_pm_resume_devices();
            return;
        }

        sys_poweroff();
        /* If poweroff returns (shouldn't), resume. */
        zmk_pm_resume_devices();
    }
}

static K_WORK_DEFINE(sleep_work, sleep_work_handler);

static void sleep_timer_expiry(struct k_timer *timer) {
    ARG_UNUSED(timer);
    k_work_submit(&sleep_work);
}

static K_TIMER_DEFINE(sleep_timer, sleep_timer_expiry, NULL);

static int hitek68_sleep_event_listener(const zmk_event_t *eh) {
    ARG_UNUSED(eh);
    last_activity_uptime = k_uptime_get();
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(hitek68_sleep, hitek68_sleep_event_listener);
ZMK_SUBSCRIPTION(hitek68_sleep, zmk_position_state_changed);
ZMK_SUBSCRIPTION(hitek68_sleep, zmk_sensor_event);

static int hitek68_sleep_init(void) {
    last_activity_uptime = k_uptime_get();
    /* Check every 5s; fine-grained enough for minute-scale timeouts. */
    k_timer_start(&sleep_timer, K_SECONDS(5), K_SECONDS(5));
    return 0;
}

SYS_INIT(hitek68_sleep_init, APPLICATION, 91);
