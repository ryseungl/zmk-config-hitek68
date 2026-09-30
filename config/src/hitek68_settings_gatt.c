/*
 * Hitek68 settings GATT service (split halves, peripheral role).
 *
 * Exposes runtime settings to the dongle (central) over BLE:
 *   Service UUID:  6e400001-b5a3-f393-e0a9-e50e24dcca9e (custom 128-bit)
 *   - Sleep timeout characteristic (read/write, 4 bytes):
 *       [timeout_ms u32 LE]  (0 = never sleep)
 *
 * Writes are validated, applied immediately, and persisted to flash.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/logging/log.h>

#include <hitek68/settings.h>

LOG_MODULE_REGISTER(hitek68_settings_gatt, CONFIG_ZMK_LOG_LEVEL);

/* Custom 128-bit UUIDs (randomly generated for Hitek68). */
#define HITEK68_SETTINGS_SVC_UUID \
    BT_UUID_128_ENCODE(0x6e400001, 0xb5a3, 0xf393, 0xe0a9, 0xe50e24dcca9e)
#define HITEK68_SETTINGS_SLEEP_UUID \
    BT_UUID_128_ENCODE(0x6e400003, 0xb5a3, 0xf393, 0xe0a9, 0xe50e24dcca9e)

static ssize_t read_sleep(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                          uint16_t len, uint16_t offset) {
    uint8_t value[4];
    sys_put_le32(hitek68_settings_get_sleep_timeout(), value);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, value, sizeof(value));
}

static ssize_t write_sleep(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                           uint16_t len, uint16_t offset, uint8_t flags) {
    if (offset != 0 || len != 4) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }
    uint32_t timeout = sys_get_le32(buf);

    int err = hitek68_settings_set_sleep_timeout(timeout);
    if (err) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }
    return len;
}

BT_GATT_SERVICE_DEFINE(hitek68_settings_svc,
                       BT_GATT_PRIMARY_SERVICE(BT_UUID_DECLARE_128(HITEK68_SETTINGS_SVC_UUID)),
                       BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_128(HITEK68_SETTINGS_SLEEP_UUID),
                                              BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                                              BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT,
                                              read_sleep, write_sleep, NULL), );
