"""Shared MQTT-side helpers: the fake bot and JSON POSTs to the HTTP API."""

from . import httpclient, normalise
from .mqttclient import MqttConn

AUTH = {"realm": "ecouser.net", "resource": "ECOGLOBLEac5ae987", "token": "token_1234", "userid": "testuser", "with": "users"}


def post_json(target, path, obj, port="https"):
    body, headers = httpclient.encode_body({"json": obj})
    return httpclient.request(target, port, "POST", path, body=body, headers=headers)


def normalise_topic(topic):
    """iot/p2p command/response topics carry the helperbot request id in
    segment 10 (a random 4 or 6 letter id). Only that segment is replaced."""
    parts = topic.split("/")
    if len(parts) == 12 and parts[0] == "iot" and parts[1] == "p2p":
        parts[10] = normalise.random_alpha(parts[10], {})
    return "/".join(parts)


class FakeBot(object):
    """An MQTT bot that subscribes to its command topic and answers each
    command with a fixed payload on the matching response topic."""

    def __init__(self, target, did, devclass="ls1ok3", resource="wC3g"):
        self.did, self.devclass, self.resource = did, devclass, resource
        self.conn = MqttConn(target, "{}@{}/{}".format(did, devclass, resource), "botsn_" + did, "botpassword")
        self.received = []
        self.reply = None

    def start(self):
        connack = self.conn.connect()
        assert connack == "Success", connack
        self.conn.respond_with(self._respond)
        self.conn.subscribe("iot/p2p/+/+/+/+/{}/{}/{}/q/+/+".format(self.did, self.devclass, self.resource))
        return self

    def _respond(self, topic, payload):
        parts = topic.split("/")
        self.received.append({"topic": normalise_topic(topic), "payload": payload.decode("utf-8")})
        if self.reply is None or len(parts) != 12 or parts[9] != "q":
            return None
        # iot/p2p/<cmd>/helperbot/bumper/helperbot/<did>/<class>/<res>/q/<reqid>/<type>
        cmd, reqid, ptype = parts[2], parts[10], parts[11]
        reply_topic = "iot/p2p/{}/{}/{}/{}/helperbot/bumper/helperbot/p/{}/{}".format(
            cmd, self.did, self.devclass, self.resource, reqid, ptype
        )
        return reply_topic, self.reply.encode("utf-8")

    def stop(self):
        self.conn.disconnect()
