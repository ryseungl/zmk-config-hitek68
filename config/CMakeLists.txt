# Hitek68 custom sources.
#
# NOTE: CI copies ZMK_CONFIG into an isolated temp dir for the actual build,
# so this file can get processed from two different physical paths in the
# same build. The global-property guard below prevents double inclusion
# (a plain set() variable would not reliably share scope across both).

get_property(_hitek68_included GLOBAL PROPERTY HITEK68_CMAKELISTS_INCLUDED SET)
if(_hitek68_included)
  return()
endif()
set_property(GLOBAL PROPERTY HITEK68_CMAKELISTS_INCLUDED TRUE)


# Public headers for our module (kscan_runtime.h, etc.)
target_include_directories(app PRIVATE include)

if(CONFIG_ZMK_SPLIT_BATTERY_HID_REPORT)
  target_sources(app PRIVATE src/battery_hid.c)
endif()

if(CONFIG_HITEK68_SETTINGS_RELAY)
  target_sources(app PRIVATE src/settings_relay.c)
endif()

if(CONFIG_HITEK68_RUNTIME_DEBOUNCE OR CONFIG_HITEK68_RUNTIME_SLEEP)
  target_sources(app PRIVATE src/hitek68_settings.c)
endif()

if(CONFIG_HITEK68_RUNTIME_DEBOUNCE)
  # Kscan driver: use zephyr_library (not target_sources) for proper
  # driver registration via DEVICE_DT_INST_DEFINE.
  zephyr_library_named(hitek68_kscan)
  zephyr_library_sources(src/kscan_hitek68_matrix.c)
  zephyr_include_directories(include)
endif()

if(CONFIG_HITEK68_RUNTIME_SLEEP)
  target_sources(app PRIVATE src/hitek68_sleep.c)
endif()

if(CONFIG_HITEK68_SETTINGS_GATT)
  target_sources(app PRIVATE src/hitek68_settings_gatt.c)
endif()
