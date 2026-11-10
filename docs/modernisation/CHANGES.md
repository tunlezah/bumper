# Modernisation: changes, private-API touchpoints and follow-ups

This document lists every **deliberate** change of observable behaviour made
during the port to current Python. The legacy behaviour is recorded in
`tests/harness/golden/` (see [BASELINE.md](BASELINE.md)). Each change below
has a matching `golden_changes/` override in the harness, and
`tests/harness/test_golden_changes.py` checks mechanically that the
overrides differ from the legacy goldens *only* in the ways described here
(predicates in `tests/harness/harnesslib/changes.py`).

## Summary

| | before | after |
|---|---|---|
| Python | 3.8 / 3.9 only (Docker: 3.7) | 3.12, 3.13, 3.14 (Docker: 3.13) |
| MQTT broker/client | hbmqtt 0.9.5 (unmaintained) | amqtt 0.12 |
| HTTP | aiohttp 3.6.2 | aiohttp 3.14 |
| DB | TinyDB 3.15, a new never-closed handle per call (closed only by GC, with a `ResourceWarning`) | TinyDB 4.9, one shared instance, closed on shutdown |
| Password hashes | passlib 1.7.2 | libpass 1.9 (maintained fork, same import) |
| Packaging | Pipfile / requirements.txt | `pyproject.toml` + `uv.lock` |
| TLS | whatever the platform allowed | one policy for 443/8883/5223, TLS 1.0+ by default, `BUMPER_TLS_MIN_VERSION` |
| Docker | `python:3.7-alpine`, root, Docker Hub | `python:3.13-slim`, uid 10001, amd64+arm64 on GHCR |
| CI | Travis, AppVeyor | GitHub Actions |

Proof of behaviour preservation: the black-box harness (`tests/harness/`)
recorded the legacy behaviour *before* any change. It passes unchanged
against the legacy code (Python 3.9, legacy profile), against the port
(3.12, 3.13, 3.14) and against the Docker image (amd64 and arm64), apart
from the changes C-001 to C-007 below.

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

### C-005

**XMPP resource bind, XMPP routing and `/api/lg/log.do` work again, byte-for-byte as on Python 3.7 (bug fix: `Element.getchildren()`, attribute order).**

*Legacy:* `xml.etree.ElementTree.Element.getchildren()` was removed in Python
3.9. The legacy code calls it in three places, so on Python >= 3.9 (where the
goldens were recorded):

* XMPP `_handle_bind` raises: the bind `iq` gets no answer, the connection's
  JID stays empty, presence and pings go to `to=""`, and **no stanza is ever
  routed between an app and an XMPP bot**;
* XMPP `_handle_result` raises on `errno='103'`, so Bumper never adds the user
  to a bot last owned by the Ecovacs cloud;
* `/api/lg/log.do` (clean logs) answers `{"ret": "fail", "errno": "0001"}` even
  when the bot answers.

The legacy Docker image (Python 3.7) did not have this problem. See
BASELINE.md: the unit test `test_lg_logs` fails on 3.9 for this reason.

A second, smaller Python change affects the same forwarding paths. Python
3.7 serialised XML attributes in alphabetical order; 3.8+ keeps document
order (bpo-34160), which would move the `from` attribute Bumper adds to the
end of every forwarded stanza. The XMPP unit tests written for 3.7 assert the
sorted form.

*Now:* `list(element)`, which is exactly what `getchildren()` returned, and
the three forwarding serialisations (`_handle_ctl`, `_handle_ping`,
`_handle_result`) use `tostring_py37()`, which sorts attributes first. Debug
log output is not affected. With both, the modern code behaves **exactly** as
the unmodified legacy code did on Python 3.7: `tests/harness/golden_reference/py37/` was recorded from the
legacy image (reproducible with `record_legacy_image.sh` there), and the
override validator requires every C-005 difference to equal that recording.

*Why a fix and not a follow-up:* without it XMPP robots cannot be controlled
at all on any supported Python version. Users moving from the 3.7-based
image would lose XMPP support with the upgrade.

*Goldens:* `xmpp/app_client_session`, `xmpp/bot_and_app_routing`,
`mqtt/helperbot_round_trips` (the `lg_logs` part).

### C-006

**Log files are written to `logs_dir` (`BUMPER_LOGS`) instead of `./logs`.**

*Legacy:* `logs_dir` (from `BUMPER_LOGS`, default `<bumper_dir>/logs`) was
computed and created, but the rotating file handlers opened the relative path
`logs/<name>.log`. So `BUMPER_LOGS` had no effect, and starting Bumper from
another directory either wrote logs there or crashed at import if that
directory had no `logs/`.

*Now:* the handlers use `os.path.join(logs_dir, ...)`. The location is the
same as before whenever Bumper is started from its own directory (the
repository root, or `WORKDIR /bumper` in the Docker image). With
`LOG_TO_STDOUT` set nothing is written to files, as before.

*Why:* requested as part of the port. `BUMPER_LOGS` is documented in
`docs/Env_Var.md` and should work. No golden impact (the harness logs to
stdout); covered by `tests/test_config.py`.

New in the same commit, without changing defaults: `BUMPER_PORT_HTTPS`,
`BUMPER_PORT_HTTP`, `BUMPER_PORT_MQTT`, `BUMPER_PORT_XMPP` (defaults 443,
8007, 8883, 5223). Bots are still told that XMPP is on 5223.

### C-007

**The MQTT single-level wildcard `+` matches exactly one topic level.**

*Legacy:* hbmqtt compiled `+` into the regex `[/\$\s\w\d]+`, which matches
`/` too. A subscription to `iot/atr/+` received
`iot/atr/DustCaseST/<did>/<class>/<res>/x`. The same regex also did *not*
match levels containing characters such as `-` or `.`.

*Now:* amqtt implements MQTT 3.1.1 §4.7.1.3: `+` matches exactly one level,
of any characters. Use `#` for several levels.

*Why:* broker semantics come from amqtt. Emulating the old matcher would mean
replacing amqtt's private topic matching. Bumper does not depend on it: bot
responses and broadcasts are handled from the broker's message-received
event, not through the helperbot's subscriptions (`iot/p2p/+`,
`iot/atr/+`, which now match nothing; see follow-ups). The Ecovacs apps and
libraries we know of subscribe with one `+` per level, which works the
same as before (the `exact` subscriber in the golden).

*Golden:* `mqtt/single_level_wildcard` (characterisation added while porting
the unit tests, which had relied on the old matcher; recorded from the legacy
code).

## Deployment changes (Docker image, configuration)

These do not change protocol behaviour and are not covered by goldens. The
container smoke test (`scripts/docker-smoke.sh`) covers them.

* **Base image:** `python:3.13-slim` (Debian) instead of `python:3.7-alpine`.
  Multi-arch `linux/amd64` + `linux/arm64`, published to
  `ghcr.io/<owner>/bumper` instead of Docker Hub.
* **Non-root:** the process runs as `bumper` (uid/gid 10001); the old image ran
  as root. Bind-mounted `data`/`certs` directories from the old image must be
  `chown`ed (see docs/Docker.md). Port 443 works without root under default
  networking (Docker >= 20.10). Under `network_mode: host` the entrypoint
  stops with an explanation instead of silently not serving 443.
* **Image defaults:** `BUMPER_LISTEN=0.0.0.0` (as the compose example always
  set; needed for the `127.0.0.1` health check) and `LOG_TO_STDOUT=true`. The
  old image listened on the container's IP and logged to `/bumper/logs`.
* **Certificates:** the entrypoint generates them on first start with
  `create_certs` built from source for the target architecture, never
  overwrites an existing set, and tells the user to persist `/bumper/certs`.
  The old image ran `bumper.create_certs()`, which picks a committed binary
  (the 32-bit ARM one on aarch64), then restarted itself with `os.execv`.
* **New:** `HEALTHCHECK`, `VOLUME /bumper/data /bumper/certs /bumper/logs`, and
  env vars `BUMPER_TLS_MIN_VERSION` and `BUMPER_PORT_HTTPS/HTTP/MQTT/XMPP`
  (documented in docs/Env_Var.md; defaults unchanged).
* **Python requirement:** >= 3.12. The `bumper` console script
  (`[project.scripts]`) is new; `python -m bumper` works as before.

## Remaining private-API touchpoints

**`bumper/` accesses no underscore-prefixed attribute of any third-party
library.** Legacy accessed hbmqtt's `Broker._sessions`,
`MQTTClient._handler.writer` and `_connected_state`, aiohttp's
`request._match_info`, asyncio's `Server._serving`, and injected a fake
distribution into `pkg_resources`. All of those are gone. (Checked with a
grep for `<name>._<attr>` on anything but `self`/`cls`.)

What remains depends on **undocumented but public-named** amqtt details. It
is kept in one place and pinned by tests, so an amqtt upgrade breaks loudly
there:

| what | where | pinned by |
|---|---|---|
| Shape of `Broker.sessions` (`client_id -> (Session, BrokerProtocolHandler)`), `Session.transitions`/`Broker.transitions` state names, `handler.session`/`handler.writer`, `MQTTClient.session` | `broker_sessions()`, `session_state()`, `broker_state()`, `client_is_connected()`, `close_session_connection()` in `bumper/mqttserver.py` | `tests/test_mqtt_compat.py` |
| The `default` listener must have `bind: None`, or amqtt opens `0.0.0.0:1883` | `MQTTServer.__init__` | `test_broker_config_has_no_plain_listener` |
| The TLS listener is an amqtt *external* listener served by `BumperBroker` through `Broker.external_connected()` and `amqtt.adapters.Stream{Reader,Writer}Adapter` (public, new in 0.12), because amqtt cannot take an `SSLContext` | `BumperBroker` in `bumper/mqttserver.py` | `tests/test_mqtt_compat.py` (start/stop/restart), harness TLS matrix |
| Releasing sessions that amqtt 0.12 leaves `connected` after failed authentication (`Session.transitions.disconnect()`) | `release_sessions_of_connection()` | `test_failed_login_does_not_leave_a_connected_session`, harness `mqtt/file_auth_*` |
| Plugin event names/kwargs (`on_broker_client_connected(*, client_id, client_session)` etc.) and the plugin logger name `amqtt.broker.plugins.BumperMQTTServer_Plugin` | `BumperMQTTServer_Plugin` | harness MQTT tests; `test_nofileauth_mqttserver` |

Other: `BumperBroker` overrides the public `Broker.start()`/`shutdown()` and
keeps its own state in `_bumper_*` attributes to avoid name clashes. The
legacy `ConfServer.stop_server()` behaviour is unchanged (see F-04).


## Follow-ups (not done in this port)

### F-01 API timestamps are off by the server's UTC offset

`datetime.utcnow().timestamp()` interprets a naive *UTC* wall-clock time as
*local* time, so the result is off by the server's UTC offset whenever `TZ`
is not UTC (the compose example sets `TZ: Europe/Rome`, i.e. 1–2 hours). That
affects `time` in every v1/v2 API envelope, `serverTime` (homePageAlert),
`getTimestamp`, and the OAuth grant: `expire_at` is stored as naive UTC,
returned as if it were local time, and `revoke_expired_oauths()` compares it
with local `datetime.now()`, so grants expire one UTC offset early or late.

The port keeps this exactly (`bumper.timeutil.utcnow_naive()` returns the same
value `utcnow()` did; the harness pins `now-3h` with the server in UTC+3).
Fixing it means `int(time.time() * 1000)` for the timestamps, and aware
datetimes (or epoch seconds) for the OAuth expiry plus a migration for stored
`expire_at` strings. It needs its own commit, a golden change (`now-3h` →
`now+0h`) and a check that current Ecovacs apps don't depend on the skew.

### F-02 The helperbot subscribes to topics it never reads

`MQTTHelperBot` subscribes to `iot/p2p/+/+/+/+/helperbot/bumper/helperbot/+/+/+`,
`iot/p2p/+` and `iot/atr/+`, but never calls `deliver_message()`: command
responses are taken from the broker's message-received event instead. amqtt
(like hbmqtt before it) queues every matching message in the client session's
unbounded `delivered_message_queue`, so the helperbot slowly accumulates one
queued message per command response for the life of the process. Before the
port, the over-matching `+` (C-007) made this worse (every bot broadcast was
queued as well). The fix is to drop the subscriptions, or drain the queue.
This changes broker-visible subscriptions, so it belongs in its own change.

### F-03 XMPP STARTTLS race: early client data is answered in plaintext

`XMPPAsyncClient._handle_starttls()` awaits `loop.start_tls()` and only then
calls `protocol.connection_made(new_transport)`. If the client's first data
after the handshake (the new `<stream:stream>` header) arrives in the same read
as its TLS 1.3 `Finished` message, asyncio's SSL protocol decrypts it and
calls `data_received()` before the task resumes. Bumper then answers over the
**old, plaintext** transport inside the TLS session, and the client fails with
a record-layer error.

This is unchanged legacy behaviour (same code, and the 2021 image's OpenSSL
1.1.1 already offered TLS 1.3). It showed up deterministically while porting
`test_xmpp_server_client_tls`, where client and server share one event loop.
The harness clients run in another process and don't hit it. Real clients
could, on a fast LAN with TLS 1.3. Fix: queue outgoing stanzas while the
upgrade is pending and flush them once `connection_made()` has the new
transport. It needs a harness case that sends `Finished` and the stream header
in one segment (MemoryBIO) and should be checked against real XMPP robots and
apps.

### F-04 `shutdown()` does not stop the web servers

`start()` serves 443 and 8007 through `ConfServer.start_site()`, which keeps
its runners in `ConfServer.runners`. `shutdown()` calls
`ConfServer.stop_server()`, which only knows `self.runner` (never set on this
path) and logs an `AttributeError`. The listening sockets stay open until the
process exits, which it normally does right after `shutdown()`. The unit tests
clean the runners up themselves. Fix: `stop_server()` should call
`cleanup()` on every runner in `self.runners`.

### F-05 Certificates are valid for 2 years and are never renewed

`create_certs` (and therefore the Docker entrypoint) issues the CA and the
server certificate for 2 years. Nothing renews them, and the entrypoint only
generates certificates when none exist, so after two years every device
stops trusting Bumper until new certificates are made and installed
everywhere. Options: a longer-lived CA with a short-lived server certificate
re-signed automatically from it (devices keep trusting the CA), plus an expiry
warning in the log and on the status page.

### F-06 Bind failures of the web servers are silent

`start()` starts the 443/8007 sites as background tasks without error
handling, and Bumper sets the `asyncio` logger to CRITICAL+1. A port that
cannot be bound (in use, privileged) is therefore never logged, and the
health check (port 8007) does not notice a missing 443. The Docker
entrypoint now catches the privileged-port case up front. The general fix is
to await the sites in `start()` and log (or exit on) bind errors.

### F-07 Security defaults kept from legacy (recorded by the harness)

All unchanged on purpose, but worth a decision:

* `bumper.use_auth` is `False`: app clients authenticate over MQTT and XMPP
  with any auth code (`mqtt/app_client_connect`), and XMPP accepts any
  credentials.
* XMPP advertises STARTTLS as `<required/>` but accepts SASL PLAIN over plain
  TCP (`xmpp/auth_without_starttls`).
* TLS 1.0/1.1 at OpenSSL security level 0 by default (C-004), for old robots.
  The per-connection TLS log line shows whether it is needed.
* The certificate private keys in the certs volume are readable by the
  container user; the CA key is only needed to issue certificates.

### F-08 Other legacy quirks kept (see BASELINE.md for the full list)

* `SetDeviceNick`/`AddOneDevice` for an unknown DID inserts a bot without a
  DID, which breaks `GetGlobalDeviceList` until removed
  (`http/13_unknown_bot_poisons_device_list`).
* `LOG_TO_STDOUT` is enabled by any non-empty value, including `false`, and
  log lines appear twice on stdout (a stream handler plus `basicConfig`).
* `bumper.create_certs()` (non-Docker) still selects the 32-bit ARM binary on
  aarch64.

### F-09 Upstream reports and dependency watch

* amqtt 0.12: a session is left `connected` after failed authentication
  (worked around in `BumperBroker`, C-003). Worth reporting upstream.
* libpass declares Python classifiers up to 3.13 and "Development Status ::
  3 - Alpha"; it is checked on 3.14 by `tests/test_passwd.py`.
* GitHub Actions are pinned by SHA; Dependabot (or Renovate) for actions,
  `uv.lock` and the base images would keep them current.

## Needs real-device testing

Nothing in this port was tested with a real robot or the current Ecovacs
apps. The harness reproduces the legacy behaviour, but the following can
only be confirmed with hardware:

* **Which TLS versions old robots actually negotiate**, especially the XMPP
  models, on 443, 8883 and 5223. Bumper now logs it per connection
  (`TLS <service> connection from <ip>: <version> <cipher>`). If no robot uses
  TLS < 1.2, the default could be tightened (C-004).
* **Current Ecovacs app versions** (Ecovacs and Ecovacs Home, Android and iOS)
  against the HTTP API, MQTT over 443 through the nginx SNI proxy, and the
  auth flows. Also whether any app relies on the UTC-offset skew (F-01).
* **Current robot firmware**, both MQTT ("eco-ng") and XMPP models.
* **XMPP robots and apps after the bind/routing fix (C-005).** It reproduces
  the Python 3.7 image byte for byte, but no XMPP robot was available here.
  The STARTTLS race (F-03) should be checked with TLS 1.3 clients.
* **MQTT clients with file auth** (e.g. Home Assistant integrations, `sucks`):
  they now get CONNACK "not authorized" (C-002) and spec-compliant `+`
  matching (C-007).
* **Docker on users' hosts:** NAS/ARM boards (arm64 was only tested under
  QEMU here), rootless Docker/podman, upgrades from the root image with
  existing bind mounts, and `network_mode: host`.
