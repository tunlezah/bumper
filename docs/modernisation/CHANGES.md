# Modernisation: changes, private-API touchpoints and follow-ups

This document lists every **deliberate** change of observable behaviour made
during the port to current Python. The legacy behaviour is recorded in
`tests/harness/golden/` (see [BASELINE.md](BASELINE.md)). Each change below
has a matching `golden_changes/` override in the harness, and
`tests/harness/test_golden_changes.py` checks mechanically that the
overrides differ from the legacy goldens *only* in the ways described here
(predicates in `tests/harness/harnesslib/changes.py`).

## Deliberate behaviour changes

### C-001

**HTTP handler errors are answered with `500` instead of a dropped connection.**

*Legacy:* about 15 error paths make a request handler return `None`: malformed
JSON to `lookup.do`, `newauth.do` and the devmanager endpoints, missing query
parameters (`checkLogin`-style `logout` without `accessToken`, `getConfig`
without `keys`, global `getAuthCode` without `deviceId`), `getUserAccountInfo`
for non-Home apps, unknown OAuth codes, and unknown `td` values. aiohttp 3.6
then raised `AttributeError: 'NoneType' object has no attribute 'keep_alive'`
inside its own request loop, logged "Unhandled exception" and closed the
connection without sending a response.

*Now:* aiohttp >= 3.7 handles a `None` return itself: it logs "Missing return
statement on request handler" and answers `500 Internal Server Error`
(`text/plain; charset=utf-8`, body `500: Internal Server Error`).

*Why:* the legacy behaviour was a crash inside aiohttp 3.6, not Bumper logic.
Keeping it would mean emulating that crash, by closing the transport from a
middleware. A client sees a failed request either way, and the 500 is the
correct HTTP answer. Every other error response (`{}`,
`{"result": "fail"}`, `null`, 404, 405) is unchanged.

*Where:* not caused by a Bumper code change. It comes from the aiohttp
upgrade (3.6.2 → 3.14) and shows up as soon as the code runs on the new
stack. Goldens: `http/02`–`07`, `http/09`.

### C-002

**MQTT clients that fail authentication receive CONNACK `0x05` (Not authorized) before the connection is closed.**

*Legacy:* hbmqtt closed the TCP/TLS connection without sending a CONNACK
(paho reported "connection closed without CONNACK").

*Now:* amqtt sends `CONNACK` with return code `0x05` and then closes the
connection.

*Why:* this is amqtt's behaviour and what MQTT 3.1.1 §3.2.2.3 asks for. Keeping
the old behaviour would mean overriding amqtt's private session handling
(`Broker._handle_client_session`). Robots are always authenticated by Bumper's
plugin, so this only affects MQTT clients with file or anonymous auth, which
now get a clear "not authorized" instead of a dropped connection.

*Goldens:* `mqtt/file_auth_bad_password`, `mqtt/file_auth_unknown_user`,
`mqtt/file_auth_anonymous`.

### C-003

**The status page lists only connected MQTT sessions.**

*Legacy:* hbmqtt never removed sessions from its session table. A client that
disconnected stayed listed as `disconnected`, and a client that failed
authentication stayed listed as `new`, both counted in "Sessions: N" until
Bumper restarted.

*Now:* amqtt's session monitor removes disconnected clean sessions within about
1 s, so the session table and count show live sessions only.

amqtt 0.12 itself would list a *refused* client as **`connected`** forever:
it registers the session and moves it to `connected` before checking
authentication, and does not undo that on failure. That is worse than legacy
(a failed login looks like a live client). `BumperBroker` therefore marks any
session still bound to a finished connection as `disconnected`
(`release_sessions_of_connection` in `bumper/mqttserver.py`), and amqtt's
monitor then removes it like any other. This is covered by
`tests/test_mqtt_compat.py` and the harness's failed-auth cases.

*Why:* this is amqtt's session lifecycle, plus the fix above so failed logins
don't show as connected. It also stops the session table from growing
without bound. The bots and clients tables come from the database and still
show each device's `mqtt_connection` flag.

*Goldens:* `http/13_unknown_bot_poisons_device_list` (status page after two
bots disconnected), and the `status_rows` of `mqtt/file_auth_bad_password`,
`mqtt/file_auth_unknown_user` and `mqtt/file_auth_anonymous` (refused clients).

### C-004

**TLS 1.0 and 1.1 are accepted again on all three TLS endpoints (443, 8883, 5223 after STARTTLS).**

*Legacy:* the code accepted whatever the platform allowed. The 2021 Docker
image (OpenSSL 1.1.1) accepted TLS 1.0–1.3. The same code on any OpenSSL 3
platform (Python 3.9 in the legacy harness venv, or `python:3.7-alpine`
rebuilt today) rejects TLS 1.0/1.1, and that is what the goldens recorded. See
BASELINE.md for the measurements.

*Now:* all three servers take their context from one factory,
`bumper.tls.server_context()`. By default it accepts TLS 1.0 and newer
(`minimum_version = TLSv1`, plus Python 3.9's server cipher string with
`@SECLEVEL=0`, which OpenSSL 3 needs for TLS < 1.2). `BUMPER_TLS_MIN_VERSION`
(`TLSv1`, `TLSv1_1`, `TLSv1_2`, `TLSv1_3`) tightens it. At `TLSv1_2` or
above, Python's default ciphers and security level are kept. Every accepted
TLS connection is logged at INFO (`bumper.tls` logger) with peer, version and
cipher, and the effective policy is logged at startup.

*Why:* this restores what users of the 2021 image had, so older robots
(especially the XMPP models) that only speak TLS 1.0 are not dropped silently
by the upgrade. Users who know their robots speak TLS 1.2 can tighten the
policy. Whether real robots need TLS 1.0/1.1 is listed under *Needs
real-device testing*. The per-connection log line is there to answer exactly
that question.

Unchanged per endpoint: the MQTT listener still asks for an *optional* client
certificate (`CERT_OPTIONAL`, as hbmqtt/amqtt did), and HTTPS and XMPP don't
ask for one. A modern client still negotiates TLS 1.3 (see the XMPP
transcripts).

*Golden:* `tls_matrix`.

## Remaining private-API touchpoints

## Follow-ups (not done in this port)

## Needs real-device testing
