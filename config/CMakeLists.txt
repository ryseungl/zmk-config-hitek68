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

if(CONFIG_ZMK_SPLIT_BATTERY_HID_REPORT)
  target_sources(app PRIVATE src/battery_hid.c)
endif()
