# Characterisation harness

Black-box tests that pin down Bumper's observable behaviour over real sockets,
so that the modernisation can be proven behaviour-preserving.

* Bumper runs as a **subprocess** (or an already running instance, e.g. the
  Docker container). The tests talk to it only over the network, with the
  stdlib (`http.client`, `ssl`, `socket`, `json`) and `paho-mqtt` as an MQTT
  client that is independent of the broker under test.
* Plain synchronous pytest, no asyncio plugins. The same files run on
  Python 3.9 + the legacy pins and on Python 3.12–3.15 + the modern pins.
* Responses are compared with **golden files** in `golden/` (pretty-printed,
  key-sorted JSON). Volatile values are normalised by exact field path in
  `harnesslib/normalise.py`; each rule is documented there.

## Layout

| path | what |
|---|---|
| `launch_bumper.py` | imports `bumper`, sets the four port globals from `BUMPER_PORT_*`, calls `bumper.main(["--listen", "127.0.0.1", "--announce", "127.0.0.1"])` |
| `conftest.py` | session fixture `target`: starts the subprocess (free ports, temp `BUMPER_DATA`, test certs, `TZ=UTC+3`) or points at `BUMPER_HARNESS_TARGET=host` |
| `http_cases.json` | ordered, stateful HTTP scenarios (login → token → auth code → ...) incl. malformed bodies |
| `test_http_golden.py` | runs the scenarios; needs a pristine instance |
| `test_route_coverage.py` | in-process: walks the aiohttp router (incl. sub-apps) and fails if a route has no case |
| `test_mqtt.py` | bot/app/file/anonymous auth, helperbot round trips and timeout, atr broadcasts, disconnect |
| `test_xmpp.py` | stream, STARTTLS, SASL PLAIN, bind, session, ping, routing app ↔ bot, close |
| `test_tls_matrix.py` | TLS 1.0–1.3 per endpoint (443, 8883, 5223 after STARTTLS) |
| `test_restart.py` | the status page's restart endpoints, followed by functional checks |
| `golden/` | behaviour recorded from the **legacy** code |
| `golden_changes/` | deliberate, documented behaviour changes (see below) |

## Running

```bash
# modern stack (default profile "modern")
uv run pytest tests/harness

# legacy code + legacy pins (Python 3.9)
BUMPER_HARNESS_PROFILE=legacy .venv-legacy-harness/bin/python -m pytest tests/harness

# against a running instance (e.g. the container), see scripts/docker-smoke.sh
BUMPER_HARNESS_TARGET=host BUMPER_HARNESS_CA=/path/to/ca.crt \
  BUMPER_PORT_HTTPS=443 BUMPER_PORT_HTTP=8007 BUMPER_PORT_MQTT=8883 BUMPER_PORT_XMPP=5223 \
  uv run pytest tests/harness
```

All environment variables are documented in `harnesslib/config.py`.

A `host` target must be **fresh** (no bots in its database; the HTTP module
checks this), must run with `TZ=UTC-3` (POSIX notation for UTC+3, see
`config.SERVER_TZ`) and needs `tests/passwd` as `passwd` in its data
directory for the file-auth tests.

## Goldens and deliberate changes

Goldens are only ever recorded from the legacy code base:

```bash
BUMPER_HARNESS_PROFILE=legacy BUMPER_HARNESS_RECORD=1 \
  .venv-legacy-harness/bin/python -m pytest tests/harness
```

Recording with the modern profile is refused. When the port changes behaviour
on purpose, the legacy golden stays as it is and a file with the same name is
added under `golden_changes/`:

```json
{"changes": ["C-001"], "reason": "...", "expected": { ... }}
```

`changes` point at entries in `docs/modernisation/CHANGES.md`, and `test_golden_changes.py` (no server needed) checks that every difference from the legacy golden is explained by one of them (`harnesslib/changes.py`). The modern
profile compares against `expected`; the legacy profile ignores
`golden_changes/`, so CI can keep proving that `golden/` matches the legacy
code. `BUMPER_HARNESS_RECORD=changes` rewrites the `expected` block of
existing change files (it never creates one).
