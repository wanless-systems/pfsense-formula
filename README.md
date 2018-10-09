pfsense-formula
===
A salt formula for managing pfSense routers

How to use
---
1. bootstrap the pfsense minion: install the FreeBSD salt package on pfSense using the pkg command
1. configure the minion: either add this formula to the pfSense minion file_roots or connect to a master with the formula

pfsense execution module
---

pfsense.get_config

get the pfsense configuration
