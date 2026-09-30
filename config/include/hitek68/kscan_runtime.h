/*
 * Runtime debounce control for the hitek68,kscan-gpio-matrix driver.
 */

#pragma once

#include <zephyr/device.h>
#include <stdint.h>

/**
 * Set the debounce press/release times (ms) at runtime.
 * Values are clamped to DEBOUNCE_COUNTER_MAX (16383).
 *
 * @param dev kscan device (e.g. DEVICE_DT_GET(DT_CHOSEN(zmk_kscan)))
 * @param press_ms debounce time for press, in ms
 * @param release_ms debounce time for release, in ms
 * @return 0 on success, negative errno on failure
 */
int hitek68_kscan_set_debounce(const struct device *dev, uint32_t press_ms, uint32_t release_ms);

/**
 * Get the current debounce times.
 */
int hitek68_kscan_get_debounce(const struct device *dev, uint32_t *press_ms, uint32_t *release_ms);
