TYPE = application
PROJECTNAME = CraneTest

DEPS += opc-ua-io

HEADERS += Libraries.h
SOURCES += CDPMain.cpp

OTHER_FILES += scripts/apply_ufw_rules.sh

DISTFILES += \
    $$files(*.xml, true) \
    $$files(*.lic, true) \
    $$files(Application/www/*.*, true)

load(cdp)

ID = 1397922600494807141017125 # do not change
