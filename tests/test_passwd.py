"""The MQTT file auth still verifies the existing passlib hashes (libpass)."""

import os
import warnings

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))


def read_passwd(path):
    with open(path) as f:
        return dict(line.strip().split(":", 1) for line in f if line.strip() and not line.startswith("#"))


def test_existing_sha512_crypt_hash_verifies_without_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # e.g. passlib 1.7.4 warned about 'crypt' on 3.12
        from passlib.apps import custom_app_context as pwd_context

        stored = read_passwd(os.path.join(TESTS, "passwd"))["test-client"]
        assert stored.startswith("$6$")
        assert pwd_context.identify(stored) == "sha512_crypt"
        assert pwd_context.verify("abc123!", stored)
        assert not pwd_context.verify("abc123", stored)


class _Session:
    def __init__(self, username, password, client_id):
        self.username, self.password, self.client_id = username, password, client_id


@pytest.mark.parametrize("password,expected", [("abc123!", True), ("wrong", False)])
async def test_mqtt_plugin_file_auth(monkeypatch, tmp_path, password, expected):
    import bumper
    from bumper import mqttserver

    monkeypatch.setattr(bumper, "data_dir", str(tmp_path))
    monkeypatch.setattr(bumper, "db", str(tmp_path / "bumper.db"))
    server = mqttserver.MQTTServer(("127.0.0.1", 0), password_file=os.path.join(TESTS, "passwd"))
    plugin = next(p for p in server.broker.plugins_manager.plugins if isinstance(p, mqttserver.BumperMQTTServer_Plugin))
    assert await plugin.authenticate(session=_Session("test-client", password, "file-auth-client")) is expected
