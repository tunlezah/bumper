"""Harness configuration, read once from the environment.

Environment variables
---------------------
BUMPER_HARNESS_TARGET   ``local`` (default): start Bumper as a subprocess.
                        ``host``: talk to an already running instance (e.g. the
                        Docker container); see BUMPER_HARNESS_HOST and the
                        BUMPER_PORT_* variables below.
BUMPER_HARNESS_HOST     Host of the running instance in ``host`` mode
                        (default ``127.0.0.1``).
BUMPER_PORT_HTTPS/HTTP/MQTT/XMPP
                        Ports of the running instance in ``host`` mode
                        (defaults 443/8007/8883/5223). Ignored in ``local`` mode,
                        where free ephemeral ports are picked.
BUMPER_HARNESS_CA       CA certificate used to verify the server
                        (default ``tests/test_certs/ca.crt``).
BUMPER_HARNESS_SRC      Bumper source tree to launch / import in ``local`` mode
                        (default: this repository). The legacy CI job points it
                        at a checkout of the pre-port commit.
BUMPER_HARNESS_PYTHON   Interpreter used to launch Bumper in ``local`` mode
                        (default: the interpreter running pytest).
BUMPER_HARNESS_PROFILE  ``modern`` (default) or ``legacy``. Selects which
                        expectation applies to entries that have a deliberate,
                        documented behaviour change (see golden.py).
BUMPER_HARNESS_RECORD   ``1``: (re)write ``golden/`` from the observed
                        behaviour. Only allowed with PROFILE=legacy, so goldens
                        can only ever come from the legacy code base.
                        ``changes``: rewrite the ``expected`` block of existing,
                        hand-written ``golden_changes/`` entries (modern only).
"""

import os

HARNESS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.abspath(os.path.join(HARNESS_DIR, "..", ".."))
TEST_CERTS_DIR = os.path.join(REPO_DIR, "tests", "test_certs")
GOLDEN_DIR = os.path.join(HARNESS_DIR, "golden")
CHANGES_DIR = os.path.join(HARNESS_DIR, "golden_changes")

TARGET = os.environ.get("BUMPER_HARNESS_TARGET", "local").strip().lower() or "local"
if TARGET not in ("local", "host"):
    raise RuntimeError("BUMPER_HARNESS_TARGET must be 'local' or 'host', not {!r}".format(TARGET))

PROFILE = os.environ.get("BUMPER_HARNESS_PROFILE", "modern").strip().lower() or "modern"
if PROFILE not in ("modern", "legacy"):
    raise RuntimeError("BUMPER_HARNESS_PROFILE must be 'modern' or 'legacy', not {!r}".format(PROFILE))

RECORD = os.environ.get("BUMPER_HARNESS_RECORD", "").strip().lower()
if RECORD in ("0", "false", "no"):
    RECORD = ""
if RECORD not in ("", "1", "true", "yes", "changes"):
    raise RuntimeError("BUMPER_HARNESS_RECORD must be unset, '1' or 'changes', not {!r}".format(RECORD))
if RECORD in ("true", "yes"):
    RECORD = "1"

CA_FILE = os.environ.get("BUMPER_HARNESS_CA") or os.path.join(TEST_CERTS_DIR, "ca.crt")
SRC_DIR = os.path.abspath(os.environ.get("BUMPER_HARNESS_SRC") or REPO_DIR)
HOST = os.environ.get("BUMPER_HARNESS_HOST", "127.0.0.1")

# Fixed, non-UTC, DST-free time zone for the server process ("UTC+3", POSIX
# notation inverts the sign). Several legacy endpoints compute timestamps with
# ``datetime.utcnow().timestamp()``, which is off by the local UTC offset. A
# fixed non-zero offset makes that observable and deterministic, so the
# normaliser can record it as "now-3h" and any change to it shows up as a
# golden diff. In ``host`` mode the server must be started with the same TZ.
SERVER_TZ = "BHT-3"
