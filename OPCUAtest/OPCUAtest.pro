CDPVERSION = 5.1
TYPE = system
load(cdp)

DISTFILES += $$files(*.xml, false)

SUBDIRS +=     \
    CraneTest
