#!/usr/bin/env python3
"""Start Bumper for the characterisation harness.

This script is deliberately tiny and works against both the legacy code base
(Python 3.9 + the original pins) and the modernised one. It:

1. puts the Bumper source tree on ``sys.path`` (``BUMPER_HARNESS_SRC``, default:
   the repository this file lives in), so the legacy CI job can point it at a
   checkout of the pre-port commit;
2. imports ``bumper`` (which reads ``BUMPER_CA``/``BUMPER_CERT``/``BUMPER_KEY``,
   ``BUMPER_DATA`` and ``LOG_TO_STDOUT`` at import time);
3. overrides the four listen-port module globals from ``BUMPER_PORT_*``. The
   legacy code has no env vars for ports, but ``bumper.start()`` reads these
   globals at run time, so setting them before ``main()`` is enough;
4. calls ``bumper.main(["--listen", "127.0.0.1", "--announce", "127.0.0.1"])``.

All configuration comes from the environment, which the harness fixture in
``conftest.py`` prepares.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BUMPER_HARNESS_SRC") or os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, SRC)

import bumper  # noqa: E402  (must come after the sys.path tweak)

PORT_GLOBALS = {
    "BUMPER_PORT_HTTPS": "conf1_listen_port",
    "BUMPER_PORT_HTTP": "conf2_listen_port",
    "BUMPER_PORT_MQTT": "mqtt_listen_port",
    "BUMPER_PORT_XMPP": "xmpp_listen_port",
}

for env_name, attr in PORT_GLOBALS.items():
    value = os.environ.get(env_name)
    if value:
        setattr(bumper, attr, int(value))

print(
    "harness launcher: bumper from {} (https={} http={} mqtt={} xmpp={})".format(
        os.path.dirname(os.path.abspath(bumper.__file__)),
        bumper.conf1_listen_port,
        bumper.conf2_listen_port,
        bumper.mqtt_listen_port,
        bumper.xmpp_listen_port,
    ),
    flush=True,
)

bumper.main(["--listen", "127.0.0.1", "--announce", "127.0.0.1"])
