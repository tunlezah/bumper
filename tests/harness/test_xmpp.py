"""XMPP server (5223, STARTTLS) driven over a raw socket.

The stanza strings are the ones asserted in tests/test_xmppserver.py. Each
test records a transcript (what was sent, what came back) as a golden.
"""

from harnesslib import golden, httpclient
from harnesslib.mqttclient import wait_until
from harnesslib.xmppclient import STARTTLS, STREAM_OPEN_CLIENT, XmppConn, stream_open_bot

# "\x00fuid_tmpuser\x000/IOSF53D07BA/us_898802fdbc4441b0bc815b1d1c68302e"
CLIENT_AUTH = (
    '<auth xmlns="urn:ietf:params:xml:ns:xmpp-sasl" mechanism="PLAIN">'
    "AGZ1aWRfdG1wdXNlcgAwL0lPU0Y1M0QwN0JBL3VzXzg5ODgwMmZkYmM0NDQxYjBiYzgxNWIxZDFjNjgzMDJl</auth>"
)
CLIENT_BIND = (
    '<iq type="set" id="5E9872D5-547E-49AF-AE51-9EFAA282F952"><bind xmlns="urn:ietf:params:xml:ns:xmpp-bind">'
    "<resource>IOSF53D07BA</resource></bind></iq>"
)
CLIENT_SESSION = '<iq type="set" id="FA1041E7-AA27-43DD-BAA3-64DE2DE56AA3"><session xmlns="urn:ietf:params:xml:ns:xmpp-session"/></iq>'

# "\x00E0000000000000001234\x00encrypted_pass"
BOT_AUTH = "<auth xmlns='urn:ietf:params:xml:ns:xmpp-sasl' mechanism='PLAIN'>AEUwMDAwMDAwMDAwMDAwMDAxMjM0AGVuY3J5cHRlZF9wYXNz</auth>"
BOT_BIND = "<iq type='set' id='2521'><bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'><resource>atom</resource></bind></iq>"
BOT_SESSION = "<iq type='set' id='2522'><session xmlns='urn:ietf:params:xml:ns:xmpp-session'/></iq>"
BOT_DID = "E0000000000000001234"


def negotiate(conn, stream_open, auth, bind, session, use_starttls=True):
    conn.exchange("stream open", stream_open)
    if use_starttls:
        conn.exchange("starttls", STARTTLS, until="proceed")
        conn.transcript.append({"step": "tls handshake", "tls_version": conn.starttls()})
        conn.exchange("stream open after TLS", stream_open)
    conn.exchange("sasl auth", auth)
    conn.exchange("stream open after auth", stream_open)
    conn.exchange("bind", bind)
    conn.exchange("session", session)


def bot_devices(target):
    body, headers = httpclient.encode_body({"json": {"todo": "GetDeviceList"}})
    out = httpclient.request(target, "https", "POST", "/api/users/user.do", body=body, headers=headers)
    return [d for d in out.json()["devices"] if d.get("did") == BOT_DID]


def test_app_client_session(target):
    c = XmppConn(target)
    try:
        negotiate(c, STREAM_OPEN_CLIENT, CLIENT_AUTH, CLIENT_BIND, CLIENT_SESSION)
        c.exchange("presence available", '<presence type="available"/>')
        c.exchange("ping server", '<iq type="get" id="ping-1" to="ecouser.net"><ping xmlns="urn:xmpp:ping"/></iq>')
        c.exchange("roster query (not implemented)", '<iq id="EE0XQ-2" type="get"><query xmlns="jabber:iq:roster" ></query></iq>')
        c.exchange("disco#info query (not implemented)", '<iq id="EE0XQ-3" type="get" to="ecouser.net"><query xmlns="http://jabber.org/protocol/disco#info"/></iq>')
        c.exchange("unknown element", "<badstr />")
        c.exchange("close stream", "</stream:stream>")
    finally:
        c.close()
    golden.check("xmpp/app_client_session", c.transcript)


def test_auth_without_starttls_is_accepted(target):
    """STARTTLS is advertised as <required/> but not enforced: SASL PLAIN over
    the plain connection succeeds. Recorded because it is security-relevant."""
    c = XmppConn(target)
    try:
        c.exchange("stream open", STREAM_OPEN_CLIENT)
        c.exchange("sasl auth over plain TCP", CLIENT_AUTH)
        c.exchange("close stream", "</stream:stream>")
    finally:
        c.close()
    golden.check("xmpp/auth_without_starttls", c.transcript)


def test_bot_and_app_routing(target):
    bot = XmppConn(target)
    app = XmppConn(target)
    record = {}
    try:
        negotiate(bot, stream_open_bot("159"), BOT_AUTH, BOT_BIND, BOT_SESSION)
        bot.exchange("presence with status", "<presence><status>hello world</status></presence>")
        negotiate(app, STREAM_OPEN_CLIENT, CLIENT_AUTH, CLIENT_BIND, CLIENT_SESSION)
        app.exchange("presence available", '<presence type="available"/>')
        record["bot_in_device_list"] = bot_devices(target)

        # app -> bot command, routed by the "to" jid
        app.exchange(
            "app sends GetCleanState to bot",
            '<iq id="7" to="E0000000000000001234@159.ecorobot.net/atom" type="set"><query xmlns="com:ctl"><ctl id="72107787" td="GetCleanState" /></query></iq>',
        )
        bot.note("bot receives", bot.read_quiet())

        # bot -> app event
        bot.exchange(
            "bot sends BatteryInfo to app",
            "<iq to='fuid_tmpuser@ecouser.net/IOSF53D07BA' type='set' id='2700'><query xmlns='com:ctl'><ctl td='BatteryInfo'><battery power='100'/></ctl></query></iq>",
        )
        app.note("app receives", app.read_quiet())

        # app -> bot ping, forwarded with a from attribute
        app.exchange(
            "app pings bot",
            '<iq id="104934615" to="E0000000000000001234@159.ecorobot.net/atom" type="get"><ping xmlns="urn:xmpp:ping" /></iq>',
        )
        bot.note("bot receives ping", bot.read_quiet())

        # bot answers the server ping
        bot.exchange("bot answers server ping", "<iq type='result' from='E0000000000000001234@159.ecorobot.net/atom' to='ecouser.net' id='s2c1'/>")
        app.note("app receives", app.read_quiet())

        # bot reports errno 103 (no permission): Bumper should add the user
        bot.exchange(
            "bot reports errno 103",
            "<iq to='fuid_tmpuser@ecouser.net/IOSF53D07BA' type='result' id='103'><query xmlns='com:ctl'>"
            "<ctl ret='fail' errno='103' error='permission denied, please contact someone@example.com'/></query></iq>",
        )
        app.note("app receives", app.read_quiet())

        bot.exchange("bot closes stream", "</stream:stream>")
        bot.close()
        record["bot_after_close"] = wait_until(
            lambda: [d for d in bot_devices(target) if d["xmpp_connection"] is False], timeout=10
        )
        app.exchange("app closes stream", "</stream:stream>")
    finally:
        bot.close()
        app.close()
    record["bot_transcript"] = bot.transcript
    record["app_transcript"] = app.transcript
    golden.check("xmpp/bot_and_app_routing", record)
