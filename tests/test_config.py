"""Import-time configuration from environment variables (run in subprocesses)."""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def import_bumper(tmp_path, extra_env, code="print(json.dumps([bumper.conf1_listen_port, bumper.conf2_listen_port, bumper.mqtt_listen_port, bumper.xmpp_listen_port]))"):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUMPER_") and k != "LOG_TO_STDOUT"}
    env.update(
        {
            "BUMPER_DATA": str(tmp_path / "data"),
            "BUMPER_CERTS": str(tmp_path / "certs"),
            "BUMPER_LISTEN": "127.0.0.1",
            "PYTHONPATH": REPO,
        }
    )
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import json, bumper\n" + code],
        cwd=str(elsewhere),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_default_ports(tmp_path):
    out = import_bumper(tmp_path, {"LOG_TO_STDOUT": "true"})
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [443, 8007, 8883, 5223]


def test_ports_from_env(tmp_path):
    out = import_bumper(
        tmp_path,
        {"LOG_TO_STDOUT": "true", "BUMPER_PORT_HTTPS": "8443", "BUMPER_PORT_HTTP": "18007", "BUMPER_PORT_MQTT": "18883", "BUMPER_PORT_XMPP": "15223"},
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [8443, 18007, 18883, 15223]


def test_invalid_port_fails_clearly(tmp_path):
    out = import_bumper(tmp_path, {"LOG_TO_STDOUT": "true", "BUMPER_PORT_MQTT": "eighty"})
    assert out.returncode != 0
    assert "BUMPER_PORT_MQTT must be a TCP port number" in out.stderr


def test_log_files_go_to_bumper_logs_not_cwd(tmp_path):
    logs = tmp_path / "custom-logs"
    out = import_bumper(tmp_path, {"BUMPER_LOGS": str(logs)}, code="print(bumper.logs_dir)")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(logs)
    assert sorted(p.name for p in logs.iterdir()) == [
        "boterror.log", "bumper.log", "confserver.log", "helperbot.log", "mqttserver.log", "xmppserver.log",
    ]
    assert not (tmp_path / "elsewhere" / "logs").exists()
