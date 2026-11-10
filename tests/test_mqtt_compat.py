"""Pins the amqtt behaviour Bumper relies on.

bumper/mqttserver.py keeps all knowledge of amqtt's session bookkeeping in a
few helper functions and runs its own TLS listener through amqtt's external
listener API. If an amqtt upgrade changes any of that, these tests should be
the first (and only) place that breaks.
"""

import asyncio
import os
import socket

import pytest
from amqtt.client import MQTTClient

import bumper
from bumper import mqttserver

CERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_certs")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def certs(monkeypatch, tmp_path):
    monkeypatch.setattr(bumper, "ca_cert", os.path.join(CERTS, "ca.crt"))
    monkeypatch.setattr(bumper, "server_cert", os.path.join(CERTS, "bumper.crt"))
    monkeypatch.setattr(bumper, "server_key", os.path.join(CERTS, "bumper.key"))
    monkeypatch.setattr(bumper, "data_dir", str(tmp_path))
    monkeypatch.setattr(bumper, "db", str(tmp_path / "bumper.db"))


async def test_broker_config_has_no_plain_listener(certs):
    # amqtt's Broker needs a running event loop, so even this test is async
    server = mqttserver.MQTTServer(("127.0.0.1", 18883), password_file="tests/passwd")
    listeners = server.broker.listeners_config
    # amqtt binds a "default" listener to 0.0.0.0:1883 unless bind is None
    assert listeners["default"].get("bind") is None
    assert listeners["tls1"].get("type") == "external"
    assert listeners["tls1"].get("bind") == "127.0.0.1:18883"


async def test_bumper_plugin_is_loaded_by_dotted_path_with_its_config(certs):
    server = mqttserver.MQTTServer(("127.0.0.1", 18883), password_file="tests/passwd", allow_anonymous=True)
    plugins = [p for p in server.broker.plugins_manager.plugins if isinstance(p, mqttserver.BumperMQTTServer_Plugin)]
    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin.config.allow_anonymous is True
    assert plugin.config.password_file == "tests/passwd"
    # amqtt's own default plugins (anonymous auth, $SYS) must not be loaded
    names = {type(p).__name__ for p in server.broker.plugins_manager.plugins}
    assert names == {"BumperMQTTServer_Plugin"}
    assert "test-client" in plugin._users


async def test_session_helpers_against_a_real_broker(certs):
    port = free_port()
    server = mqttserver.MQTTServer(("127.0.0.1", port), password_file="tests/passwd")
    broker = server.broker
    assert mqttserver.broker_state(broker) == "new"
    await server.broker_coro()
    assert mqttserver.broker_state(broker) == "started"

    client = MQTTClient(client_id="helperbot@bumper/helperbot", config={"check_hostname": False, "auto_reconnect": False})
    assert not mqttserver.client_is_connected(client)  # session is None before connect
    await client.connect("mqtts://127.0.0.1:{}/".format(port), cafile=bumper.ca_cert)
    try:
        assert mqttserver.client_is_connected(client)

        sessions = mqttserver.broker_sessions(broker)
        assert [client_id for client_id, _, _ in sessions] == ["helperbot@bumper/helperbot"]
        client_id, session, handler = sessions[0]
        assert session.client_id == client_id
        assert mqttserver.session_state(session) == "connected"
        assert handler.session is session
        assert handler.writer is not None

        # restart_MQTT closes every connected session's connection this way
        await mqttserver.close_session_connection(handler)
        for _ in range(50):
            if mqttserver.session_state(session) == "disconnected":
                break
            await asyncio.sleep(0.05)
        assert mqttserver.session_state(session) == "disconnected"
    finally:
        await client.disconnect()

    await broker.shutdown()
    assert mqttserver.broker_state(broker) == "stopped"
    # the TLS listener follows the broker lifecycle
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()

    # and comes back when the stopped broker is started again (restart_MQTT)
    await server.broker_coro()
    assert mqttserver.broker_state(broker) == "started"
    socket.create_connection(("127.0.0.1", port), timeout=1).close()
    await broker.shutdown()


async def test_bind_error_is_a_broker_error(certs):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        server = mqttserver.MQTTServer(("127.0.0.1", port))
        with pytest.raises(mqttserver.BrokerError):
            await server.broker.start()


async def test_failed_login_does_not_leave_a_connected_session(certs):
    """amqtt 0.12 leaves a session "connected" after failed authentication;
    BumperBroker releases it once the connection is over."""
    port = free_port()
    server = mqttserver.MQTTServer(("127.0.0.1", port), password_file="tests/passwd")
    await server.broker_coro()
    try:
        client = MQTTClient(client_id="failed-login", config={"check_hostname": False, "auto_reconnect": False})
        with pytest.raises(Exception):
            await client.connect(
                "mqtts://test-client:wrong@127.0.0.1:{}/".format(port), cafile=bumper.ca_cert
            )
        states = None
        for _ in range(60):  # amqtt's session monitor runs once per second
            states = {cid: mqttserver.session_state(s) for cid, s, _ in mqttserver.broker_sessions(server.broker)}
            if "failed-login" not in states:
                break
            await asyncio.sleep(0.1)
        assert "failed-login" not in states, states
    finally:
        await server.broker.shutdown()
