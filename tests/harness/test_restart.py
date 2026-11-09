"""The status page's restart buttons: GET /restart_{Helperbot,XMPPServer,MQTTServer}.

Each restart is followed by a functional check (a helperbot round trip, a new
XMPP stream), so the module leaves the instance working for whatever runs
next. Timings follow the legacy implementation: the MQTT broker stops after
0.1 s and starts again after 1.5 s; the helperbot reconnects after 5 s.
"""

import time

from harnesslib import golden, httpclient
from harnesslib.xmppclient import STREAM_OPEN_CLIENT, XmppConn
from harnesslib.bots import AUTH, FakeBot, post_json


def round_trip(target, did, attempts=4):
    """Send one command through the helperbot to a fresh fake bot.

    Retried a few times, because right after a restart the helperbot may
    still be reconnecting; only the final outcome is recorded.
    """
    cmd = {"auth": AUTH, "cmdName": "GetChargeState", "payload": "<ctl td='GetChargeState'/>", "payloadType": "x",
           "td": "q", "toId": did, "toRes": "wC3g", "toType": "ls1ok3"}
    bot = FakeBot(target, did).start()
    bot.reply = "<ctl ret='ok'><charge type='Idle'/></ctl>"
    try:
        for _ in range(attempts):
            out = post_json(target, "/api/iot/devmanager.do", cmd)
            record = httpclient.describe(out)
            if record.get("body", {}).get("ret") == "ok":
                break
            time.sleep(2)
        return record
    finally:
        bot.stop()


def test_restart_services(target):
    record = {"round_trip_before": round_trip(target, "R3001")}

    record["restart_helperbot"] = httpclient.describe(httpclient.request(target, "http", "GET", "/restart_Helperbot"))
    time.sleep(2)
    record["round_trip_after_helperbot_restart"] = round_trip(target, "R3002")

    xmpp_before = XmppConn(target)
    xmpp_before.exchange("stream open", STREAM_OPEN_CLIENT)
    record["restart_xmpp"] = httpclient.describe(httpclient.request(target, "http", "GET", "/restart_XMPPServer"))
    xmpp_before.read_quiet(total=3)
    record["xmpp_connection_dropped_by_restart"] = xmpp_before.closed_by_server
    xmpp_before.close()
    xmpp_after = XmppConn(target)
    try:
        record["xmpp_stream_after_restart"] = xmpp_after.exchange("stream open", STREAM_OPEN_CLIENT)
    finally:
        xmpp_after.close()

    bot = FakeBot(target, "R3003").start()
    record["restart_mqtt"] = httpclient.describe(httpclient.request(target, "http", "GET", "/restart_MQTTServer"))
    time.sleep(1)
    record["mqtt_bot_dropped_by_restart"] = not bot.conn.connected
    bot.stop()
    time.sleep(7)  # broker back after 1.5 s, helperbot after 5 s
    record["round_trip_after_mqtt_restart"] = round_trip(target, "R3004")

    golden.check("restart/services", record)
