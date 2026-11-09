"""MQTT broker (8883, TLS) and helperbot behaviour, driven with paho-mqtt.

Each test uses its own device ids and only records rows that belong to them,
so the module does not depend on what other modules did to the instance.
"""

import json
import re
import time

import pytest

from harnesslib import golden, httpclient
from harnesslib.bots import AUTH, FakeBot, post_json
from harnesslib.mqttclient import MqttConn, wait_until


def devices(target, dids):
    """users.do GetDeviceList, restricted to the given DIDs."""
    out = post_json(target, "/api/users/user.do", {"auth": AUTH, "todo": "GetDeviceList", "userid": "testuser"})
    return [d for d in out.json()["devices"] if d.get("did") in dids]


def status_rows(target, needle):
    """<TR> rows of the status page that mention ``needle`` (selection, not normalisation)."""
    out = httpclient.request(target, "http", "GET", "/")
    html = out.raw.decode("utf-8")
    return [row for row in re.findall(r"<TR>.*?</TR>", html, flags=re.S) if needle in row]


def test_bot_connect_and_disconnect(target):
    did = "E2001"
    bot = MqttConn(target, "E2001@ls1ok3/wC3g", "botsn_E2001", "botpassword")
    record = {"connack": bot.connect()}
    try:
        record["device_list_connected"] = devices(target, [did])
        record["status_rows_connected"] = status_rows(target, "E2001")
    finally:
        bot.disconnect()
    record["device_list_after_disconnect"] = wait_until(
        lambda: [d for d in devices(target, [did]) if d["mqtt_connection"] is False], timeout=10
    )
    golden.check("mqtt/bot_connect_disconnect", record)


def test_app_client_connect_with_auth_code(target):
    login = httpclient.request(target, "https", "GET", "/v1/private/us/en/dev_mqtt_app/global_e/1.6.3/c_Android/1/user/login")
    token = login.json()["data"]["accessToken"]
    code = httpclient.request(
        target,
        "https",
        "GET",
        "/v1/global/auth/getAuthCode?uid=fuid_tmpuser&deviceId=dev_mqtt_app&accessToken={}".format(token),
    ).json()["data"]["authCode"]

    app = MqttConn(target, "fuid_tmpuser@ecouser/IOSMQTT01", "fuid_tmpuser", code)
    record = {"connack_with_auth_code": app.connect()}
    try:
        record["status_rows_connected"] = status_rows(target, "IOSMQTT01")
    finally:
        app.disconnect()
    time.sleep(1)
    # Clients table only: it is backed by the DB (mqtt_connection flag).
    record["client_rows_after_disconnect"] = [r for r in status_rows(target, "IOSMQTT01") if "removeClient" in r]

    # Auth is not enforced (bumper.use_auth is False), so a wrong code is
    # accepted as well. Recorded because it is security-relevant behaviour.
    other = MqttConn(target, "fuid_tmpuser@ecouser/IOSMQTT02", "fuid_tmpuser", "us_wrongcode")
    record["connack_with_wrong_code"] = other.connect()
    other.disconnect()
    golden.check("mqtt/app_client_connect", record)


@pytest.mark.parametrize(
    "case,client_id,username,password",
    [
        ("valid", "test-file-auth", "test-client", "abc123!"),
        ("bad_password", "test-file-auth-bad", "test-client", "wrong"),
        ("unknown_user", "test-file-auth-unknown", "nobody", "abc123!"),
        ("anonymous", "anonymous-client", None, None),
    ],
)
def test_file_auth_and_anonymous(target, case, client_id, username, password):
    conn = MqttConn(target, client_id, username, password)
    connack = conn.connect()
    conn.disconnect()
    golden.check("mqtt/file_auth_" + case, {"client_id": client_id, "username": username, "connack": connack})


def test_helperbot_round_trips(target):
    bot = FakeBot(target, "E2002").start()
    record = {}
    try:
        # iot/devmanager.do, JSON payload
        bot.reply = json.dumps({"body": {"code": 0, "data": {"ver": "0.13.5"}, "msg": "ok"}, "header": {"pri": 1, "ts": 1600000000000, "tzm": 480, "ver": "0.0.50"}})
        cmd = {
            "auth": AUTH,
            "cmdName": "getWKVer",
            "payload": {"header": {"pri": "1", "ts": 1600000000000, "tzm": 480, "ver": "0.0.50"}},
            "payloadType": "j",
            "td": "q",
            "toId": "E2002",
            "toRes": "wC3g",
            "toType": "ls1ok3",
        }
        record["iot_json"] = {"response": httpclient.describe(post_json(target, "/api/iot/devmanager.do", cmd)), "bot_received": bot.received[-1:]}

        # iot/devmanager.do, XML payload
        bot.reply = "<ctl ret='ok'><charge type='SlotCharging' h='' r='a' s='' g='0'/></ctl>"
        cmd = dict(cmd, cmdName="GetChargeState", payload="<ctl td='GetChargeState'/>", payloadType="x")
        record["iot_xml"] = {"response": httpclient.describe(post_json(target, "/api/iot/devmanager.do", cmd)), "bot_received": bot.received[-1:]}

        # dim/devmanager.do (Ecovacs Home), needs the bot to be MQTT connected
        bot.reply = "<ctl ret='ok' status='idle'/>"
        cmd = dict(cmd, cmdName="GetCleanState", payload="<ctl td='GetCleanState'/>", payloadType="x")
        record["dim_xml"] = {"response": httpclient.describe(post_json(target, "/api/dim/devmanager.do", cmd)), "bot_received": bot.received[-1:]}

        # lg/log.do GetCleanLogs: Bumper sends <ctl count="30"/> and parses the
        # bot's XML answer into a list of logs.
        bot.reply = "<ctl ret='ok'><CleanSt a='10' s='1600000000' l='600' t='a'/><CleanSt a='4' s='1600100000' l='300' t='s'/></ctl>"
        lg = {"auth": AUTH, "did": "E2002", "resource": "wC3g", "td": "GetCleanLogs"}
        record["lg_logs"] = {"response": httpclient.describe(post_json(target, "/api/lg/log.do", lg)), "bot_received": bot.received[-1:]}
    finally:
        bot.stop()
    golden.check("mqtt/helperbot_round_trips", record)


def test_helperbot_timeout(target):
    bot = FakeBot(target, "E2003").start()  # subscribed, but never answers
    try:
        cmd = {"auth": AUTH, "cmdName": "GetChargeState", "payload": "<ctl td='GetChargeState'/>", "payloadType": "x",
               "td": "q", "toId": "E2003", "toRes": "wC3g", "toType": "ls1ok3"}
        started = time.time()
        out = post_json(target, "/api/iot/devmanager.do", cmd)
        elapsed = time.time() - started
    finally:
        bot.stop()
    record = {"response": httpclient.describe(out), "bot_received": bot.received, "waited_at_least_9s": elapsed >= 9}
    golden.check("mqtt/helperbot_timeout", record)


def test_atr_error_broadcast(target):
    bot = FakeBot(target, "E2004").start()
    watcher = MqttConn(target, "fuid_tmpuser@ecouser/ATRWATCH", "fuid_tmpuser", "x")
    assert watcher.connect() == "Success"
    try:
        watcher.subscribe("iot/atr/+/E2004/ls1ok3/wC3g/+")
        payload = json.dumps({"code": 102, "ts": 1600000000000})
        bot.conn.publish("iot/atr/errors/E2004/ls1ok3/wC3g/j", payload.encode())
        received = watcher.next_message(timeout=10)
        still_connected = bot.conn.connected
    finally:
        watcher.disconnect()
        bot.stop()
    record = {
        "watcher_received": None if received is None else {"topic": received[0], "payload": received[1].decode()},
        "bot_still_connected": still_connected,
    }
    golden.check("mqtt/atr_error_broadcast", record)
