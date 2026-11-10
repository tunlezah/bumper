"""Where the harness sends its traffic: a local subprocess or a running host."""

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

from . import config


class Target(object):
    """Addresses of a running Bumper instance."""

    def __init__(self, host, https, http, mqtt, xmpp, ca_file, log_path=None, data_dir=None):
        self.host = host
        self.ports = {"https": https, "http": http, "mqtt": mqtt, "xmpp": xmpp}
        self.ca_file = ca_file
        self.log_path = log_path
        self.data_dir = data_dir

    def port(self, name):
        return self.ports[name]

    def describe(self):
        return "{} {} (ca={})".format(self.host, self.ports, self.ca_file)


def _free_ports(count):
    """Reserve ``count`` distinct ephemeral ports.

    All sockets are held open until every port has been picked, so the kernel
    cannot hand out the same port twice. There is a small window between
    closing them and Bumper binding; the ephemeral range is large enough that
    this has not been a problem in practice.
    """
    socks = []
    try:
        for _ in range(count):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            socks.append(s)
        return [s.getsockname()[1] for s in socks]
    finally:
        for s in socks:
            s.close()


def wait_for_port(host, port, deadline, proc=None):
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


class LocalBumper(object):
    """Bumper started as a subprocess with a fresh data directory."""

    def __init__(self):
        self.workdir = tempfile.mkdtemp(prefix="bumper-harness-")
        self.data_dir = os.path.join(self.workdir, "data")
        os.makedirs(self.data_dir)
        # File-auth tests need a passwd file with the test-client entry.
        shutil.copy(os.path.join(config.REPO_DIR, "tests", "passwd"), os.path.join(self.data_dir, "passwd"))
        self.log_path = os.path.join(self.workdir, "bumper.log")
        https, http, mqtt, xmpp = _free_ports(4)
        self.target = Target(
            "127.0.0.1", https, http, mqtt, xmpp, config.CA_FILE, log_path=self.log_path, data_dir=self.data_dir
        )
        self.proc = None
        self._log = None

    def start(self, timeout=60):
        env = dict(os.environ)
        for key in list(env):
            # Never inherit configuration meant for another Bumper instance.
            if key.startswith("BUMPER_") and not key.startswith("BUMPER_HARNESS_"):
                del env[key]
        env.update(
            {
                "BUMPER_CA": os.path.join(config.TEST_CERTS_DIR, "ca.crt"),
                "BUMPER_CERT": os.path.join(config.TEST_CERTS_DIR, "bumper.crt"),
                "BUMPER_KEY": os.path.join(config.TEST_CERTS_DIR, "bumper.key"),
                "BUMPER_DATA": self.data_dir,
                "BUMPER_HARNESS_SRC": config.SRC_DIR,
                "BUMPER_PORT_HTTPS": str(self.target.port("https")),
                "BUMPER_PORT_HTTP": str(self.target.port("http")),
                "BUMPER_PORT_MQTT": str(self.target.port("mqtt")),
                "BUMPER_PORT_XMPP": str(self.target.port("xmpp")),
                "LOG_TO_STDOUT": "true",
                "PYTHONUNBUFFERED": "1",
                "TZ": config.SERVER_TZ,
            }
        )
        python = os.environ.get("BUMPER_HARNESS_PYTHON") or sys.executable
        launcher = os.path.join(config.HARNESS_DIR, "launch_bumper.py")
        self._log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [python, launcher],
            cwd=self.workdir,
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        # The web servers are started only after the helperbot has connected
        # to the MQTT broker, so once both HTTP ports accept connections the
        # whole instance (MQTT, helperbot, XMPP) is up.
        for name in ("http", "https"):
            if not wait_for_port("127.0.0.1", self.target.port(name), deadline, self.proc):
                self.stop()
                raise RuntimeError(
                    "Bumper did not open its {} port within {}s.\n--- bumper output ---\n{}".format(
                        name, timeout, self.read_log()
                    )
                )
        return self.target

    def read_log(self):
        try:
            with open(self.log_path, "rb") as f:
                return f.read().decode("utf-8", "replace")
        except OSError:
            return "<no log>"

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if self._log is not None:
            self._log.close()
            self._log = None

    def cleanup(self):
        shutil.rmtree(self.workdir, ignore_errors=True)


def wait_for_http(target, deadline):
    """An HTTP response on the plain config port.

    TCP-level checks are not enough for a container: Docker's port publisher
    accepts connections on the host port before anything listens inside.
    Bumper starts its web servers only after the helperbot is connected, so
    a response here also means MQTT (and XMPP, started earlier) are up.
    """
    import http.client

    while time.time() < deadline:
        conn = http.client.HTTPConnection(target.host, target.port("http"), timeout=2)
        try:
            conn.request("GET", "/")
            conn.getresponse().read()
            return True
        except (OSError, http.client.HTTPException):
            time.sleep(0.5)
        finally:
            conn.close()
    return False


def wait_for_tls(target, deadline):
    from . import tlsutil

    ctx = tlsutil.client_context(target.ca_file)
    while time.time() < deadline:
        try:
            with socket.create_connection((target.host, target.port("https")), timeout=2) as raw:
                with ctx.wrap_socket(raw):
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def host_target():
    def port(name, default):
        return int(os.environ.get("BUMPER_PORT_" + name) or default)

    target = Target(
        config.HOST,
        port("HTTPS", 443),
        port("HTTP", 8007),
        port("MQTT", 8883),
        port("XMPP", 5223),
        config.CA_FILE,
    )
    deadline = time.time() + 90
    if not (wait_for_http(target, deadline) and wait_for_tls(target, deadline)):
        raise RuntimeError("Target {} is not serving HTTP/HTTPS".format(target.describe()))
    return target
