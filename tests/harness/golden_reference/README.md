# Reference recordings from legacy images

`py37/` holds the harness recordings that differ from `../golden/` when the
**unmodified** legacy code (commit `df36bdd`) runs on Python 3.7, in the
legacy Dockerfile's base image `python:3.7-alpine`.

On Python 3.7, `xml.etree.ElementTree.Element.getchildren()` still existed. On
Python 3.9, where `../golden/` was recorded, it doesn't: XMPP resource bind
gets no answer, nothing is routed between app and bot, and `/api/lg/log.do`
fails. The getchildren() fix (CHANGES.md, C-005) must make the modern code
behave exactly like these files. `harnesslib/changes.py` checks that every
C-005 override equals them, node by node.

Reproduce (needs Docker; the base was pulled through `mirror.gcr.io` because
Docker Hub rate-limited this environment):

```bash
BUILD_CA_CERT=/path/to/proxy-ca.crt \
  tests/harness/golden_reference/record_legacy_image.sh /tmp/py37 df36bdd mirror.gcr.io/library/python:3.7-alpine
```

The script builds the legacy image's final stage from `git archive df36bdd`,
runs it with the test certificates, records the whole harness into a
temporary golden directory (`BUMPER_HARNESS_GOLDEN_DIR`), and copies the
files that differ from `golden/`. On 2026-11-09 these were exactly:

* `mqtt/helperbot_round_trips.json`: `lg_logs` returns the parsed clean logs
* `xmpp/app_client_session.json`: bind answers with the bound JID
* `xmpp/bot_and_app_routing.json`: bind, routing app ↔ bot, errno-103 handling
