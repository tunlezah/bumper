# Legacy baseline

This file records how the **unmodified** code base (commit `df36bdd`, the last
upstream commit from June 2021) behaves before modernisation starts. Nothing in
`bumper/` was changed to produce these results.

## Environments

Both legacy environments use CPython **3.9.25** (from `uv python install 3.9`,
python-build-standalone, bundled **OpenSSL 3.5.4**) and the original pins from
`requirements.txt` (aiohttp 3.6.2, hbmqtt 0.9.5, tinydb 3.15.2, passlib 1.7.2,
Jinja2 2.10.3, ...) plus `setuptools<70` (hbmqtt needs `pkg_resources`).

| venv | extra packages | used for |
|---|---|---|
| `.venv-legacy-unit` | `pytest==6.2.5 pytest-aiohttp==0.3.0 pytest-asyncio==0.14.0 pytest-env mock testfixtures` | the existing unit suite in `tests/` |
| `.venv-legacy-harness` | `pytest>=8.3,<8.4 paho-mqtt>=2.1,<3` | the black-box harness in `tests/harness/` |

Recreate them with (`requirements.txt` was removed after the port, so it is
taken from the pre-port commit):

```bash
git show df36bdd:requirements.txt > /tmp/legacy-requirements.txt
uv python install 3.9
uv venv -p 3.9 .venv-legacy-unit
uv pip install -p .venv-legacy-unit/bin/python -r /tmp/legacy-requirements.txt "setuptools<70" \
    pytest==6.2.5 pytest-aiohttp==0.3.0 pytest-asyncio==0.14.0 pytest-env mock testfixtures
uv venv -p 3.9 .venv-legacy-harness
uv pip install -p .venv-legacy-harness/bin/python -r /tmp/legacy-requirements.txt "setuptools<70" \
    "pytest>=8.3,<8.4" "paho-mqtt>=2.1,<3"
```

The legacy *unit* suite has to run from a checkout of the pre-port commit
(the unit tests have been ported since). The harness runs against the
legacy code from any checkout via `BUMPER_HARNESS_SRC` (see
`tests/harness/README.md` and the `legacy-harness` CI job).

## Existing unit suite (`.venv-legacy-unit`, Python 3.9.25)

Command: `.venv-legacy-unit/bin/python -m pytest tests -p no:cacheprovider -rA`

Result: **49 passed, 11 failed** (identical on two consecutive runs).

Passed (49):

```
tests/test_confserver.py::test_confserver_ssl
tests/test_confserver.py::test_confserver_exceptions
tests/test_confserver.py::test_confserver_no_ssl
tests/test_confserver.py::test_get_milli_time
tests/test_confserver.py::test_base[pyloop]
tests/test_confserver.py::test_restartService[pyloop]
tests/test_confserver.py::test_RemoveBot[pyloop]
tests/test_confserver.py::test_RemoveClient[pyloop]
tests/test_confserver.py::test_login[pyloop]
tests/test_confserver.py::test_logout[pyloop]
tests/test_confserver.py::test_checkLogin[pyloop]
tests/test_confserver.py::test_getAuthCode[pyloop]
tests/test_confserver.py::test_checkAgreement[pyloop]
tests/test_confserver.py::test_homePageAlert[pyloop]
tests/test_confserver.py::test_checkVersion[pyloop]
tests/test_confserver.py::test_checkAppVersion[pyloop]
tests/test_confserver.py::test_uploadDeviceInfo[pyloop]
tests/test_confserver.py::test_getAdByPositionType[pyloop]
tests/test_confserver.py::test_getBootScreen[pyloop]
tests/test_confserver.py::test_hasUnreadMsg[pyloop]
tests/test_confserver.py::test_getMsgList[pyloop]
tests/test_confserver.py::test_getSystemReminder[pyloop]
tests/test_confserver.py::test_getCnWapShopConfig[pyloop]
tests/test_confserver.py::test_neng_hasUnreadMessage[pyloop]
tests/test_confserver.py::test_getProductIotMap[pyloop]
tests/test_confserver.py::test_getUsersAPI[pyloop]
tests/test_confserver.py::test_getUserAccountInfo[pyloop]
tests/test_confserver.py::test_postUsersAPI[pyloop]
tests/test_confserver.py::test_appsvr_api[pyloop]
tests/test_confserver.py::test_postLookup[pyloop]
tests/test_confserver.py::test_devmgr[pyloop]
tests/test_confserver.py::test_dim_devmanager[pyloop]
tests/test_db.py::test_db_path
tests/test_db.py::test_user_db
tests/test_db.py::test_bot_db
tests/test_db.py::test_client_db
tests/test_init.py::test_strtobool
tests/test_init.py::test_start_stop
tests/test_init.py::test_start_stop_debug
tests/test_models.py::test_oauth
tests/test_mqttserver.py::test_helperbot_message
tests/test_mqttserver.py::test_helperbot_expire_message
tests/test_mqttserver.py::test_helperbot_sendcommand
tests/test_mqttserver.py::test_mqttserver
tests/test_mqttserver.py::test_nofileauth_mqttserver
tests/test_xmppserver.py::test_xmpp_server
tests/test_z_problem.py::test_argparse
tests/test_z_problem.py::test_createcert
tests/test_z_problem.py::test_main
```

Failed (11):

```
tests/test_confserver.py::test_lg_logs[pyloop]            AssertionError: assert 'fail' == 'ok'
tests/test_xmppserver.py::test_client_connect_no_starttls AttributeError: 'Transport' object attribute 'get_extra_info' is read-only
tests/test_xmppserver.py::test_client_end_stream          (same)
tests/test_xmppserver.py::test_client_connect_starttls_called (same)
tests/test_xmppserver.py::test_xmpp_server_client_tls     AttributeError: can't set attribute  (protocol._stream_reader = ...)
tests/test_xmppserver.py::test_client_init                (same)
tests/test_xmppserver.py::test_bot_connect                (same)
tests/test_xmppserver.py::test_bot_init                   (same)
tests/test_xmppserver.py::test_ping_server                (same)
tests/test_xmppserver.py::test_ping_client_to_client      (same)
tests/test_xmppserver.py::test_client_send_iq             (same)
```

### Correction to the brief: not all failures are in `test_xmppserver.py`

The ten XMPP failures are test bugs, not server bugs: nine assign
`get_extra_info` on a real `asyncio.Transport()`, and
`test_xmpp_server_client_tls` assigns the read-only
`StreamReaderProtocol._stream_reader` property. The eleventh, `test_lg_logs`, is a **real server
bug that only exists on Python >= 3.9**:

```
ERROR root:bumper_confserver_portal_lg.py:102 'xml.etree.ElementTree.Element' object has no attribute 'getchildren'
```

`xml.etree.ElementTree.Element.getchildren()` was removed in Python 3.9. A
cross-check on Python 3.8.20 with the same pins gives **50 passed, 10 failed**:
the ten XMPP test-bug failures, with `test_lg_logs` passing. That explains the
"49–50 passed, 10–11 failed" range in the brief.

`getchildren()` is called in three places in `bumper/`:

| location | effect on Python >= 3.9 |
|---|---|
| `bumper/plugins/bumper_confserver_portal_lg.py` (`handle_lg_log`) | `/api/lg/log.do` always answers `{"ret": "fail", "errno": "0001"}` for an MQTT bot, even when the bot answers |
| `bumper/xmppserver.py` (`_handle_bind`) | XMPP resource bind raises, is logged, and **no bind result is sent**; the client's `bumper_jid` stays empty, so no stanza is ever routed between app and bot |
| `bumper/xmppserver.py` (`_handle_result`, errno 103 branch) | the "add Bumper user to a bot last owned by Ecovacs" recovery never runs |

The XMPP unit tests would have caught the bind failure, but they never reach it
because of the transport test bug. The legacy Docker image
(`python:3.7-alpine`) was not affected, because `getchildren()` still existed
in 3.7.

How the harness and the port handle this is described in the harness section
below and in `CHANGES.md`.

## Other legacy quirks observed while running the suite

* The unit suite writes outside of any temp directory: `logs/*.log` (log
  handlers use the relative path `logs/`, not `logs_dir`), `data/passwd`
  (created by `bumper.main()`), and `tests/tmp.db`. All of these are gitignored.
* `test_z_problem.py::test_main` and `test_init.py` log
  `AttributeError: 'NoneType' object has no attribute 'shutdown'` from
  `ConfServer.stop_server()`. `start()` starts the web servers through
  `start_site()`, which never sets `self.runner`, so `shutdown()` cannot stop
  them this way. This is logged and swallowed; the tests still pass.

## Characterisation harness on the legacy code (`.venv-legacy-harness`)

The black-box harness in `tests/harness/` (see its README) was written and
its goldens recorded **before any production change**, against the unmodified
code on Python 3.9.25 + the original pins:

```bash
BUMPER_HARNESS_PROFILE=legacy BUMPER_HARNESS_RECORD=1 .venv-legacy-harness/bin/python -m pytest tests/harness
```

Then, in compare mode, three times in a row:

```
== run 1   39 passed in 49.60s
== run 2   39 passed in 50.76s
== run 3   39 passed in 49.69s
```

No flakiness and no port collisions (every run picks free ephemeral ports).
The harness was also checked for sensitivity. Against a scratch copy of
`bumper/` (via `BUMPER_HARNESS_SRC`) where one plugin used `datetime.now()`
instead of `datetime.utcnow()` and the iot request id was 5 instead of 4
letters, both mutations were reported as golden diffs.

Coverage: 13 HTTP scenarios with 132 requests (plus 4 MQTT bot connect/disconnect steps) reach all **57 route entries**
(`test_route_coverage.py`), plus 9 MQTT, 3 XMPP, 12 TLS-matrix and 1 restart
test.

## TLS versions accepted by the legacy code

Recorded in `tests/harness/golden/tls_matrix.json`. All three endpoints
(443, 8883, 5223 after STARTTLS) behave the same:

| environment | TLS 1.0 | TLS 1.1 | TLS 1.2 | TLS 1.3 |
|---|---|---|---|---|
| Python 3.9.25, OpenSSL 3.5.4 (legacy harness venv, **the goldens**) | rejected | rejected | accepted | accepted |
| `python:3.7-alpine` as published today (3.7.17, Alpine 3.18, OpenSSL 3.1.3) | rejected | rejected | accepted | accepted |
| Alpine 3.13, Python 3.8.15, OpenSSL 1.1.1q (stand-in for the June-2021 image) | **accepted** | **accepted** | accepted | accepted |

Why: the legacy code builds its server contexts with
`ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)`. Before Python 3.10 that
sets no minimum protocol version. Whether TLS 1.0/1.1 work then depends only
on OpenSSL: OpenSSL 1.1.1 allows them at its default security level, but
OpenSSL 3.x only allows them at `@SECLEVEL=0`. So the **same unmodified code**
accepted TLS 1.0 in the image users actually ran in 2021 (Alpine with OpenSSL
1.1.1) and rejects it when rebuilt today, or on any OpenSSL 3 host.

The 2021 base tag (`python:3.7.10-alpine3.13`) could not be pulled here
(Docker Hub and both mirrors rate-limited the request). The stand-in uses the
same Alpine release and OpenSSL 1.1.1 line, with Alpine's packaged Python 3.8.
For this question Python 3.7 and 3.8 behave the same (`create_default_context`
only gained a TLS 1.2 minimum in 3.10).

The goldens record the Python 3.9/OpenSSL 3 behaviour as observed. The
required end state (accept TLS 1.0+ by default, as the 2021 image did) is a
deliberate change from those goldens and is documented in `CHANGES.md`.

### Whole-harness comparison against the legacy images

Both images were built from the pre-port commit's `bumper/` and
`requirements.txt` (scratch builds, not committed), started with the test
certificates, and the harness was run with `BUMPER_HARNESS_TARGET=host`.

| image | result vs. the 3.9 goldens |
|---|---|
| `python:3.7-alpine` today (3.7.17, OpenSSL 3.1.3) | 36 passed, 3 failed: `test_helperbot_round_trips` (`lg/log.do` returns logs), `test_app_client_session` and `test_bot_and_app_routing` (XMPP bind answers and stanzas are routed) |
| Alpine 3.13 / Python 3.8 / OpenSSL 1.1.1q | the same 3, plus the six TLS 1.0/1.1 cells (accepted) |

That confirms the two legacy-environment variables: `getchildren()`
(Python >= 3.9) and OpenSSL >= 3 rejecting TLS < 1.2. Everything else is
identical across Python 3.7, 3.8 and 3.9.

## Legacy behaviour captured by the goldens that is worth knowing

These are recorded as-is. They are listed here so that nobody "fixes" them
by accident:

* **Handler errors drop the connection.** About 15 error paths (malformed JSON
  to `lookup.do`/`newauth.do`/devmanager, missing query parameters,
  `getUserAccountInfo` for non-Home apps, unknown OAuth codes, ...) make the
  handler return `None`. aiohttp 3.6 then crashes internally (`'NoneType'
  object has no attribute 'keep_alive'`) and closes the connection without
  sending a response. Other error paths answer `200` with `{}`,
  `{"result": "fail"}` or `null`.
* **`SetDeviceNick`/`AddOneDevice` for an unknown DID** upserts a bot document
  without a `did` (TinyDB `upsert` inserts when nothing matches). Afterwards
  `GetGlobalDeviceList` answers `{"result": "fail"}` (KeyError on `class`)
  until that document is removed, which is impossible over HTTP.
* **Timestamps** in the v1/v2 API envelopes (`time`, `serverTime`,
  `getTimestamp`) are `datetime.utcnow().timestamp()`, i.e. off by the server's
  UTC offset. The harness runs Bumper in UTC+3 and records them as `now-3h`.
  `nextAlertTime` is local `now + 12h` (correct), and OAuth `expire_at` is
  `utcnow + 15 days` interpreted as local time (`now+357h` in UTC+3).
* **MQTT auth failures** (bad password, unknown user, anonymous) are answered
  by closing the connection **without a CONNACK**.
* **Auth is not enforced** for app clients (`bumper.use_auth` is `False`): an
  MQTT app client with a wrong auth code connects, and XMPP clients are
  accepted with any credentials.
* **XMPP STARTTLS is advertised as `<required/>` but not enforced**: SASL PLAIN
  over the plain TCP connection succeeds.
* **The status page keeps disconnected MQTT sessions**: hbmqtt never removes a
  clean session after disconnect, so the session table lists `disconnected`
  rows forever.
* `GET /` answers the status page because aiohttp turns the root route's empty
  path into `/` when the app is frozen.
