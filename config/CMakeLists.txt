# Hitek68 custom sources — compiled only for the dongle (central) build.
# The peripheral halves don't need battery HID reporting.

if(CONFIG_ZMK_SPLIT_BATTERY_HID_REPORT)
  target_sources(app PRIVATE src/battery_hid.c)
endif()
