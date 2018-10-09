# pfsense-formula
A salt formula for managing pfSense routers.

Interfaces with pfSense using the php-cgi CLI and pfSense PHP code
to affect the pfSense configuration rather than trying to second guess how
pfSense will operate on modified XML configuration.

## How to use
1. bootstrap the pfsense minion: install the FreeBSD salt package on pfSense using the pkg command
1. configure the minion: either add this formula to the pfSense minion file_roots or connect to a master with the formula

## pfsense execution module
---

### pfsense.get_config
get the pfsense configuration, optionally a subset of the config identified by
a conventonal salt colon delimited nested data key argument.

eg.

`salt 'a.router.your.net' pfsense.get_config interfaces:opt1:descr`

or

`salt 'a.router.your.net' pfsense.get_config`

## See also
---
* https://github.com/alkivi-sas/salt-pfsense
* https://github.com/ndejong/pfsense_fauxapi
