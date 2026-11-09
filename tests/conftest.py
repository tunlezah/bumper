"""Shared setup for the unit tests.

(The characterisation harness in tests/harness/ has its own conftest and
pytest.ini and is not collected by a plain ``pytest`` run.)

``bumper`` reads its configuration from environment variables at import time,
so they are set here, before any test module imports it. Everything Bumper
writes (data, certs, logs) goes to a temporary directory, never into the
repository.

The autouse fixture gives every test a fresh, empty database and restores
the module globals tests modify (debug flag, listen address, ports, server
singletons, ...), so tests are independent of each other and of their order.
"""

import os
import shutil
import socket
import tempfile

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CERTS_DIR = os.path.join(TESTS_DIR, "test_certs")
_SESSION_DIR = tempfile.mkdtemp(prefix="bumper-unit-")

os.environ.setdefault("BUMPER_CA", os.path.join(CERTS_DIR, "ca.crt"))
os.environ.setdefault("BUMPER_CERT", os.path.join(CERTS_DIR, "bumper.crt"))
os.environ.setdefault("BUMPER_KEY", os.path.join(CERTS_DIR, "bumper.key"))
os.environ.setdefault("BUMPER_DATA", os.path.join(_SESSION_DIR, "data"))
os.environ.setdefault("BUMPER_CERTS", os.path.join(_SESSION_DIR, "certs"))
os.environ.setdefault("BUMPER_LOGS", os.path.join(_SESSION_DIR, "logs"))
os.environ.setdefault("BUMPER_LISTEN", "127.0.0.1")

import bumper  # noqa: E402
from bumper.db import db_close  # noqa: E402
from bumper.xmppserver import XMPPServer  # noqa: E402

_RESTORED_GLOBALS = [
    "db",
    "bumper_debug",
    "bumper_listen",
    "bumper_announce_ip",
    "use_auth",
    "shutting_down",
    "ca_cert",
    "server_cert",
    "server_key",
    "mqtt_server",
    "mqtt_helperbot",
    "conf_server",
    "conf_server_2",
    "xmpp_server",
    "mqtt_listen_port",
    "conf1_listen_port",
    "conf2_listen_port",
    "xmpp_listen_port",
]


@pytest.fixture(autouse=True)
def isolated_bumper(tmp_path, monkeypatch):
    db_close()
    for name in _RESTORED_GLOBALS:
        # setattr with the current value: monkeypatch restores it afterwards
        monkeypatch.setattr(bumper, name, getattr(bumper, name))
    monkeypatch.setattr(XMPPServer, "clients", [])
    bumper.db = str(tmp_path / "bumper.db")
    yield
    db_close()


@pytest.fixture
def free_port():
    """A function returning a currently unused TCP port on 127.0.0.1."""

    def pick():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    return pick


def remove_existing_db():
    """Delete the current test database (the next access starts empty)."""
    if bumper.db and os.path.exists(bumper.db):
        os.remove(bumper.db)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SESSION_DIR, ignore_errors=True)


class _LogCheck:
    """The subset of testfixtures.LogCapture the tests used, on top of caplog."""

    def __init__(self, caplog, names):
        self._caplog = caplog
        self._names = names

    def actual(self):
        return [
            (r.name, r.levelname, r.getMessage())
            for r in self._caplog.records
            if not self._names or r.name in self._names or r.name.split(".")[0] in self._names
        ]

    def check_present(self, *expected, order_matters=True):
        actual = self.actual()
        for entry in expected:
            assert entry in actual, "{!r} was not logged; captured: {!r}".format(entry, actual)
        if order_matters:
            positions = [actual.index(entry) for entry in expected]
            assert positions == sorted(positions), "logged in a different order: {!r}".format(actual)

    def clear(self):
        self._caplog.clear()

    def __str__(self):
        return "\n".join("{} {} {}".format(*entry) for entry in self.actual())


@pytest.fixture
def log_capture(caplog):
    """``with log_capture("xmppserver") as l: ... l.check_present((name, level, msg))``"""
    import contextlib
    import logging

    @contextlib.contextmanager
    def capture(*names):
        caplog.set_level(logging.DEBUG)
        for name in names:
            caplog.set_level(logging.DEBUG, logger=name)
        yield _LogCheck(caplog, names)

    return capture
