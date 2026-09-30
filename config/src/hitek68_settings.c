/*
 * Runtime settings for Hitek68 split halves.
 *
 * Persists the deep-sleep timeout via the Zephyr settings subsystem
 * (NVS flash). The value is applied immediately to the sleep timer and
 * saved with a short delay so rapid successive changes don't wear flash.
 */

#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/device.h>
#include <zephyr/settings/settings.h>
#include <zephyr/logging/log.h>

#include <hitek68/settings.h>

LOG_MODULE_REGISTER(hitek68_settings, CONFIG_ZMK_LOG_LEVEL);

/* Default matches our 30-min sleep. */
#define DEFAULT_SLEEP_TIMEOUT_MS 1800000 /* 30 min */

static uint32_t sleep_timeout_ms = DEFAULT_SLEEP_TIMEOUT_MS;

/* Forward-declared: implemented in hitek68_sleep.c (weak if not built). */
__weak void hitek68_sleep_set_timeout(uint32_t timeout_ms) { ARG_UNUSED(timeout_ms); }

/* ---- Getter ---- */

uint32_t hitek68_settings_get_sleep_timeout(void) { return sleep_timeout_ms; }

/* ---- Delayed flash save (avoid wearing NVS on rapid changes) ---- */

#define SETTINGS_SAVE_DELAY_S 5

static void settings_save_work_cb(struct k_work *work) {
    ARG_UNUSED(work);
    settings_save_one("hitek68/sleep_timeout", &sleep_timeout_ms, sizeof(sleep_timeout_ms));
    LOG_INF("Hitek68 settings saved to flash");
}
static K_WORK_DELAYABLE_DEFINE(settings_save_work, settings_save_work_cb);

static void schedule_save(void) {
    k_work_reschedule(&settings_save_work, K_SECONDS(SETTINGS_SAVE_DELAY_S));
}

/* ---- Setter ---- */

int hitek68_settings_set_sleep_timeout(uint32_t timeout_ms) {
    if (timeout_ms != HITEK68_SLEEP_TIMEOUT_DISABLED &&
        (timeout_ms < HITEK68_SLEEP_TIMEOUT_MIN_MS || timeout_ms > HITEK68_SLEEP_TIMEOUT_MAX_MS)) {
        return -EINVAL;
    }
    sleep_timeout_ms = timeout_ms;
    hitek68_sleep_set_timeout(timeout_ms);
    schedule_save();
    LOG_INF("Sleep timeout set: %u ms", timeout_ms);
    return 0;
}

/* ---- Zephyr settings handlers ---- */

static int hitek68_settings_set(const char *name, size_t len, settings_read_cb read_cb,
                                void *cb_arg) {
    const char *next;
    size_t name_len = settings_name_next(name, &next);

    if (!strncmp(name, "sleep_timeout", name_len)) {
        read_cb(cb_arg, &sleep_timeout_ms, sizeof(sleep_timeout_ms));
        return 0;
    }
    return -ENOENT;
}

/* Called after all settings are loaded (from main(), after SYS_INIT).
 * Applies the loaded value to hardware. */
static int hitek68_settings_commit(void) {
    /* Clamp loaded value in case flash holds garbage from an older build. */
    if (sleep_timeout_ms != HITEK68_SLEEP_TIMEOUT_DISABLED &&
        (sleep_timeout_ms < HITEK68_SLEEP_TIMEOUT_MIN_MS ||
         sleep_timeout_ms > HITEK68_SLEEP_TIMEOUT_MAX_MS)) {
        sleep_timeout_ms = DEFAULT_SLEEP_TIMEOUT_MS;
    }

    hitek68_sleep_set_timeout(sleep_timeout_ms);

    LOG_INF("Hitek68 settings loaded: sleep %u ms", sleep_timeout_ms);
    return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(hitek68_settings, "hitek68", NULL, hitek68_settings_set,
                               hitek68_settings_commit, NULL);

/* Apply defaults at boot (before settings are loaded from flash in main()).
 * The commit handler re-applies after load if flash has stored values. */
static int hitek68_settings_init(void) {
    hitek68_sleep_set_timeout(sleep_timeout_ms);
    return 0;
}
