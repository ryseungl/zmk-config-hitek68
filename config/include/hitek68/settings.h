/*
 * Runtime settings for Hitek68 split halves.
 * Persists debounce times and sleep timeout via Zephyr settings (NVS).
 */

#pragma once

#include <stdint.h>

#define HITEK68_DEBOUNCE_MIN_MS 0
#define HITEK68_DEBOUNCE_MAX_MS 16383

#define HITEK68_SLEEP_TIMEOUT_MIN_MS 60000      /* 1 minute */
#define HITEK68_SLEEP_TIMEOUT_MAX_MS 86400000   /* 24 hours */
#define HITEK68_SLEEP_TIMEOUT_DISABLED 0        /* 0 = never sleep */

/* Getters (always succeed, return current RAM values) */
uint32_t hitek68_settings_get_debounce_press(void);
uint32_t hitek68_settings_get_debounce_release(void);
uint32_t hitek68_settings_get_sleep_timeout(void);

/**
 * Setters: validate, apply immediately to hardware, and persist.
 * @return 0 on success, -EINVAL on out-of-range value.
 */
int hitek68_settings_set_debounce(uint32_t press_ms, uint32_t release_ms);
int hitek68_settings_set_sleep_timeout(uint32_t timeout_ms);
