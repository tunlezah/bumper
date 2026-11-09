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

Recreate them with:

```bash
uv python install 3.9
uv venv -p 3.9 .venv-legacy-unit
uv pip install -p .venv-legacy-unit/bin/python -r requirements.txt "setuptools<70" \
    pytest==6.2.5 pytest-aiohttp==0.3.0 pytest-asyncio==0.14.0 pytest-env mock testfixtures
uv venv -p 3.9 .venv-legacy-harness
uv pip install -p .venv-legacy-harness/bin/python -r requirements.txt "setuptools<70" \
    "pytest>=8.3,<8.4" "paho-mqtt>=2.1,<3"
```

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
