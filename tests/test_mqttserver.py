from unittest import mock
import bumper
import asyncio
import pytest
import os
import json
import xml.etree.ElementTree as ET
import logging
import time

from amqtt.client import MQTTClient
from amqtt.errors import ConnectError
from amqtt.mqtt.constants import QOS_0

from bumper.mqttserver import client_is_connected


# The legacy tests checked hbmqtt's private Client._connected_state._value;
# client_is_connected() asserts the same behaviour (the session is connected).
#
# They also waited for the helperbot's own client to receive each published
# message (deliver_message), which only worked because the legacy broker's '+'
# matched several topic levels (CHANGES.md C-007). What they assert is that
# the broker plugin handled and logged the message, so they now wait for that
# log record.


async def wait_logged(l, *expected, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(entry in l.actual() for entry in expected):
            return
        await asyncio.sleep(0.02)


@pytest.fixture
def mqtt_address(free_port):
    return ("127.0.0.1", free_port())


async def test_helperbot_message(log_capture, mqtt_address):
    mqtt_server = bumper.MQTTServer(mqtt_address, password_file="tests/passwd")
    await mqtt_server.broker_coro()

    with log_capture() as l:

        # Test broadcast message
        mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
        await mqtt_helperbot.start_helper_bot()
        assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected
        msg_payload = "<ctl ts='1547822804960' td='DustCaseST' st='0'/>"
        msg_topic_name = "iot/atr/DustCaseST/bot_serial/ls1ok3/wC3g/x"
        await mqtt_helperbot.Client.publish(
            msg_topic_name, msg_payload.encode(), QOS_0
        )

        expected = (
            "helperbot",
            "DEBUG",
            "Received Broadcast - Topic: iot/atr/DustCaseST/bot_serial/ls1ok3/wC3g/x - Message: <ctl ts='1547822804960' td='DustCaseST' st='0'/>",
        )
        await wait_logged(l, expected)
        l.check_present(expected)  # Check broadcast message was logged
        l.clear()
        await mqtt_helperbot.Client.disconnect()

        # Send command to bot
        mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
        await mqtt_helperbot.start_helper_bot()
        assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected
        msg_payload = "{}"
        msg_topic_name = (
            "iot/p2p/GetWKVer/helperbot/bumper/helperbot/bot_serial/ls1ok3/wC3g/q/iCmuqp/j"
        )
        await mqtt_helperbot.Client.publish(
            msg_topic_name, msg_payload.encode(), QOS_0
        )

        expected = (
            "helperbot",
            "DEBUG",
            "Send Command - Topic: iot/p2p/GetWKVer/helperbot/bumper/helperbot/bot_serial/ls1ok3/wC3g/q/iCmuqp/j - Message: {}",
        )
        await wait_logged(l, expected)
        l.check_present(expected)  # Check send command message was logged
        l.clear()
        await mqtt_helperbot.Client.disconnect()

        # Received response to command
        mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
        bumper.mqtt_helperbot = mqtt_helperbot  # the plugin stores responses on it
        await mqtt_helperbot.start_helper_bot()
        assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected
        msg_payload = '{"ret":"ok","ver":"0.13.5"}'
        msg_topic_name = (
            "iot/p2p/GetWKVer/bot_serial/ls1ok3/wC3g/helperbot/bumper/helperbot/p/iCmuqp/j"
        )
        await mqtt_helperbot.Client.publish(
            msg_topic_name, msg_payload.encode(), QOS_0
        )

        expected = (
            "helperbot",
            "DEBUG",
            'Received Response - Topic: iot/p2p/GetWKVer/bot_serial/ls1ok3/wC3g/helperbot/bumper/helperbot/p/iCmuqp/j - Message: {"ret":"ok","ver":"0.13.5"}',
        )
        await wait_logged(l, expected)
        l.check_present(expected)  # Check received response message was logged
        l.clear()
        await mqtt_helperbot.Client.disconnect()

        # Received unknown message
        mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
        await mqtt_helperbot.start_helper_bot()
        assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected
        msg_payload = "test"
        msg_topic_name = (
            "iot/p2p/GetWKVer/bot_serial/ls1ok3/wC3g/TESTBAD/bumper/helperbot/p/iCmuqp/j"
        )
        await mqtt_helperbot.Client.publish(
            msg_topic_name, msg_payload.encode(), QOS_0
        )

        expected = (
            "helperbot",
            "DEBUG",
            "Received Message - Topic: iot/p2p/GetWKVer/bot_serial/ls1ok3/wC3g/TESTBAD/bumper/helperbot/p/iCmuqp/j - Message: test",
        )
        await wait_logged(l, expected)
        l.check_present(expected)  # Check received message was logged
        l.clear()
        await mqtt_helperbot.Client.disconnect()

        # Received error message
        mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
        await mqtt_helperbot.start_helper_bot()
        assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected
        msg_payload = "<ctl ts='1560904925396' td='errors' old='' new='110'/>"
        msg_topic_name = "iot/atr/errors/bot_serial/ls1ok3/wC3g/x"
        await mqtt_helperbot.Client.publish(
            msg_topic_name, msg_payload.encode(), QOS_0
        )

        expected = (
            "boterror",
            "ERROR",
            "Received Error - Topic: iot/atr/errors/bot_serial/ls1ok3/wC3g/x - Message: <ctl ts='1560904925396' td='errors' old='' new='110'/>",
        )
        await wait_logged(l, expected)
        l.check_present(expected)  # Check received message was logged
        l.clear()
        await mqtt_helperbot.Client.disconnect()

    await mqtt_server.broker.shutdown()


async def test_helperbot_expire_message(log_capture, mqtt_address):
    mqtt_server = bumper.MQTTServer(mqtt_address, password_file="tests/passwd")
    await mqtt_server.broker_coro()

    with log_capture("helperbot") as l:

        # Test broadcast message
        mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
        bumper.mqtt_helperbot = mqtt_helperbot
        await mqtt_helperbot.start_helper_bot()
        assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected

        expire_msg_payload = '{"ret":"ok","ver":"0.13.5"}'
        expire_msg_topic_name = "iot/p2p/GetWKVer/bot_serial/ls1ok3/wC3g/helperbot/bumper/helperbot/p/testgood/j"
        currenttime = time.time()
        mqtt_helperbot.command_responses.append(
            {
                "time": currenttime,
                "topic": expire_msg_topic_name,
                "payload": expire_msg_payload,
            }
        )

        assert {
            "time": currenttime,
            "topic": expire_msg_topic_name,
            "payload": expire_msg_payload,
        } in mqtt_helperbot.command_responses  # check message is in command_responses

        await asyncio.sleep(0.1)
        mqtt_helperbot.expire_msg_seconds = (
            0.1
        )  # Set expire message seconds to 0.1 so we don't wait 10 seconds
        msg_payload = "<ctl ts='1547822804960' td='DustCaseST' st='0'/>"
        msg_topic_name = "iot/atr/DustCaseST/bot_serial/ls1ok3/wC3g/x"
        await mqtt_helperbot.Client.publish(
            msg_topic_name, msg_payload.encode(), QOS_0
        )  # Send another message to force get_msg

        expected = (
            "helperbot",
            "DEBUG",
            "Pruning Message Due To Expiration - Message Topic: {}".format(
                expire_msg_topic_name
            ),
        )
        await wait_logged(l, expected)

        assert {
            "time": currenttime,
            "topic": expire_msg_topic_name,
            "payload": expire_msg_payload,
        } not in mqtt_helperbot.command_responses  # check message was expired and removed from command_responses

        l.check_present(expected)  # Check received message was logged
        await mqtt_helperbot.Client.disconnect()

    await mqtt_server.broker.shutdown()


async def test_helperbot_sendcommand(mqtt_address):
    mqtt_server = bumper.MQTTServer(mqtt_address, password_file="tests/passwd")
    await mqtt_server.broker_coro()

    mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
    bumper.mqtt_helperbot = mqtt_helperbot
    await mqtt_helperbot.start_helper_bot()
    assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected

    cmdjson = {
        "toType": "ls1ok3",
        "payloadType": "j",
        "toRes": "wC3g",
        "payload": {},
        "td": "q",
        "toId": "bot_serial",
        "cmdName": "GetWKVer",
        "auth": {
            "token": "us_52cb21fef8e547f38f4ec9a699a5d77e",
            "resource": "IOSF53D07BA",
            "userid": "fuid_tmpuser",
            "with": "users",
            "realm": "ecouser.net",
        },
    }
    mqtt_helperbot.wait_resp_timeout_seconds = (
        0.1
    )  # Override wait_resp_timeout (so we don't wait 10 seconds for timeout)
    commandresult = await mqtt_helperbot.send_command(cmdjson, "testfail")
    # Don't send a response, ensure timeout
    assert commandresult == {
        "debug": "wait for response timed out",
        "errno": 500,
        "id": "testfail",
        "ret": "fail",
    }  # Check timeout

    mqtt_helperbot.wait_resp_timeout_seconds = (
        0.2
    )  # Override wait_resp_timeout (so we don't wait 10 seconds for timeout)
    # Send response beforehand
    msg_payload = '{"ret":"ok","ver":"0.13.5"}'
    msg_topic_name = (
        "iot/p2p/GetWKVer/bot_serial/ls1ok3/wC3g/helperbot/bumper/helperbot/p/testgood/j"
    )
    await mqtt_helperbot.Client.publish(
        msg_topic_name, msg_payload.encode(), QOS_0
    )

    commandresult = await mqtt_helperbot.send_command(cmdjson, "testgood")
    assert commandresult == {
        "id": "testgood",
        "resp": {"ret": "ok", "ver": "0.13.5"},
        "ret": "ok",
    }

    # Test GetLifeSpan (xml command)
    cmdjson = {
        "toType": "ls1ok3",
        "payloadType": "x",
        "toRes": "wC3g",
        "payload": '<ctl type="Brush"/>',
        "td": "q",
        "toId": "bot_serial",
        "cmdName": "GetLifeSpan",
        "auth": {
            "token": "us_52cb21fef8e547f38f4ec9a699a5d77e",
            "resource": "IOSF53D07BA",
            "userid": "fuid_tmpuser",
            "with": "users",
            "realm": "ecouser.net",
        },
    }

    mqtt_helperbot.wait_resp_timeout_seconds = (
        0.2
    )  # Override wait_resp_timeout (so we don't wait 10 seconds for timeout)
    # Send response beforehand
    msg_payload = "<ctl ret='ok' type='Brush' left='4142' total='18000'/>"
    msg_topic_name = (
        "iot/p2p/GetLifeSpan/bot_serial/ls1ok3/wC3g/helperbot/bumper/helperbot/p/testx/q"
    )
    await mqtt_helperbot.Client.publish(
        msg_topic_name, msg_payload.encode(), QOS_0
    )

    commandresult = await mqtt_helperbot.send_command(cmdjson, "testx")
    assert commandresult == {
        "id": "testx",
        "resp": "<ctl ret='ok' type='Brush' left='4142' total='18000'/>",
        "ret": "ok",
    }

    # Test json payload (OZMO950)
    cmdjson = {
        "toType": "ls1ok3",
        "payloadType": "j",
        "toRes": "wC3g",
        "payload": {
            "header": {
            "pri": 1,
            "ts": "1569380075887",
            "tzm": -240,
            "ver": "0.0.50"
        }
        },
        "td": "q",
        "toId": "bot_serial",
        "cmdName": "getStats",
        "auth": {
            "token": "us_52cb21fef8e547f38f4ec9a699a5d77e",
            "resource": "IOSF53D07BA",
            "userid": "fuid_tmpuser",
            "with": "users",
            "realm": "ecouser.net",
        },
    }

    mqtt_helperbot.wait_resp_timeout_seconds = (
        0.2
    )  # Override wait_resp_timeout (so we don't wait 10 seconds for timeout)
    # Send response beforehand
    msg_payload = '{"body":{"code":0,"data":{"area":0,"cid":"111","start":"1569378657","time":6,"type":"auto"},"msg":"ok"},"header":{"fwVer":"1.6.4","hwVer":"0.1.1","pri":1,"ts":"1569380074036","tzm":480,"ver":"0.0.1"}}'

    msg_topic_name = (
        "iot/p2p/getStats/bot_serial/ls1ok3/wC3g/helperbot/bumper/helperbot/p/testj/j"
    )
    await mqtt_helperbot.Client.publish(
        msg_topic_name, msg_payload.encode(), QOS_0
    )

    commandresult = await mqtt_helperbot.send_command(cmdjson, "testj")

    assert commandresult == {
        "id": "testj",
        "resp": {'body':{'code':0,'data':{'area':0,'cid':'111','start':'1569378657','time':6,'type':'auto'},'msg':'ok'},'header':{'fwVer':'1.6.4','hwVer':'0.1.1','pri':1,'ts':'1569380074036','tzm':480,'ver':'0.0.1'}},
        "ret": "ok",
    }

    await mqtt_helperbot.Client.disconnect()

    await mqtt_server.broker.shutdown()



async def test_mqttserver(log_capture, mqtt_address):
    if bumper.db and os.path.exists(bumper.db):
        os.remove(bumper.db)  # Remove existing db

    mqtt_server = bumper.MQTTServer(mqtt_address, password_file="tests/passwd", allow_anonymous=True)

    await mqtt_server.broker_coro()

    # Test helperbot connect
    mqtt_helperbot = bumper.MQTTHelperBot(mqtt_address)
    await mqtt_helperbot.start_helper_bot()
    assert client_is_connected(mqtt_helperbot.Client)  # Check helperbot is connected
    await mqtt_helperbot.Client.disconnect()

    # Test client connect
    bumper.user_add("user_123")  # Add user to db
    bumper.client_add("user_123", "ecouser.net", "resource_123")  # Add client to db
    test_client = bumper.MQTTHelperBot(mqtt_address)
    test_client.client_id = "user_123@ecouser.net/resource_123"
    test_client.Client = MQTTClient(
        client_id=test_client.client_id, config={"check_hostname": False}
    )

    await test_client.Client.connect(
        "mqtts://{}:{}/".format(test_client.address[0], test_client.address[1]),
        cafile=bumper.ca_cert,
    )
    assert client_is_connected(test_client.Client)  # Check client is connected
    await test_client.Client.disconnect()
    assert not client_is_connected(test_client.Client)  # Check client is disconnected

    # Test fake_bot connect
    fake_bot = bumper.MQTTHelperBot(mqtt_address)
    fake_bot.client_id = "bot_serial@ls1ok3/wC3g"
    await fake_bot.start_helper_bot()
    assert client_is_connected(fake_bot.Client)  # Check fake_bot is connected
    await fake_bot.Client.disconnect()

    # Test file auth client connect
    test_client = bumper.MQTTHelperBot(mqtt_address)
    test_client.client_id = "test-file-auth"
    test_client.Client = MQTTClient(
        client_id=test_client.client_id, config={"check_hostname": False, "auto_reconnect": False, "reconnect_retries": 1}
    )

    # good user/pass
    await test_client.Client.connect(
        f"mqtts://test-client:abc123!@{test_client.address[0]}:{test_client.address[1]}/",
        cafile=bumper.ca_cert, cleansession=True
    )

    assert client_is_connected(test_client.Client)  # Check client is connected
    await test_client.Client.disconnect()
    assert not client_is_connected(test_client.Client)  # Check client is disconnected

    # The broker is configured with allow_anonymous=True, so a wrong password
    # still falls through to anonymous auth and is accepted; what matters
    # here is that the file auth failure is logged.
    # bad password
    with log_capture() as l:

        await test_client.Client.connect(
            f"mqtts://test-client:notvalid!@{test_client.address[0]}:{test_client.address[1]}/",
            cafile=bumper.ca_cert, cleansession=True
        )
        await test_client.Client.disconnect()

        l.check_present(
                ("mqttserver", "INFO", "File Authentication Failed - Username: test-client - ClientID: test-file-auth"),
                order_matters=False
            )
    # no username in file
        await test_client.Client.connect(
            f"mqtts://test-client-noexist:notvalid!@{test_client.address[0]}:{test_client.address[1]}/",
            cafile=bumper.ca_cert, cleansession=True
        )
        await test_client.Client.disconnect()


        l.check_present(
            ("mqttserver", "INFO", 'File Authentication Failed - No Entry for Username: test-client-noexist - ClientID: test-file-auth'),
            order_matters=False
        )

    await mqtt_server.broker.shutdown()


async def test_file_auth_refused_without_anonymous(mqtt_address):
    """Without allow_anonymous a wrong password is refused at CONNECT."""
    mqtt_server = bumper.MQTTServer(mqtt_address, password_file="tests/passwd")
    await mqtt_server.broker_coro()
    client = MQTTClient(client_id="test-file-auth", config={"check_hostname": False, "auto_reconnect": False})
    try:
        with pytest.raises(ConnectError):
            await client.connect(
                f"mqtts://test-client:notvalid!@{mqtt_address[0]}:{mqtt_address[1]}/", cafile=bumper.ca_cert
            )
        assert not client_is_connected(client)
    finally:
        await mqtt_server.broker.shutdown()


async def test_nofileauth_mqttserver(log_capture, mqtt_address):
    with log_capture() as l:

        mqtt_server = bumper.MQTTServer(mqtt_address, password_file="tests/passwd-notfound")
        await mqtt_server.broker_coro()
        await mqtt_server.broker.shutdown()

    # amqtt names the plugin logger after the plugin class (was
    # "hbmqtt.broker.plugins.bumper" with the legacy broker)
    l.check_present(
        ("amqtt.broker.plugins.BumperMQTTServer_Plugin", "WARNING", 'Password file tests/passwd-notfound not found'),
        order_matters=False
    )
