"""Normalisation of volatile values in recorded responses.

Rules
-----
Every rule is keyed by an exact field path into the JSON body (or, for XMPP,
an attribute name). No rule rewrites a whole payload with a regex.

Each rule also checks the *shape* of the value before replacing it. If a value
at a normalised path does not have the expected shape (for example a token that
is suddenly ``None``, or a random id that changed length), it is left untouched
so that it shows up as a golden diff. Over-normalising would hide regressions.

Values that a scenario captured earlier (``capture`` in http_cases.json) are
replaced by ``<var:NAME>`` instead of a generic placeholder, which also proves
that, for example, ``checkLogin`` echoes exactly the token ``login`` issued.
"""

import re
import time

HEX32 = re.compile(r"^[0-9a-f]{32}$")
AUTHCODE = re.compile(r"^([a-z]{2})_([0-9a-f]{32})$")
ALPHA = re.compile(r"^[A-Za-z]+$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Tolerance when classifying a millisecond timestamp relative to "now". Two
# minutes covers request latency and slow CI machines; the offsets we care
# about (time zone offset, +12h, +15 days) are hours apart.
MS_EPOCH_TOLERANCE_MS = 120 * 1000


def ms_epoch(value, ctx):
    """Millisecond Unix timestamp -> offset from the time the response arrived.

    The result is rounded to half hours, e.g. ``<ms-epoch now-3h>``. Keeping the
    offset (instead of a bare ``<timestamp>``) matters: the legacy code computes
    several of these with ``datetime.utcnow().timestamp()``, which is off by
    the server's UTC offset (the harness runs Bumper in UTC+3, see
    config.SERVER_TZ). The port must reproduce that exactly.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return value
    delta = value - ctx["now_ms"]
    half_hours = round(delta / 1800000.0)
    if abs(delta - half_hours * 1800000) > MS_EPOCH_TOLERANCE_MS:
        return "<ms-epoch UNALIGNED now{:+d}ms>".format(delta)
    hours = half_hours / 2.0
    return "<ms-epoch now{}h>".format("{:+g}".format(hours))


def _var(value, ctx):
    for name, captured in sorted(ctx.get("vars", {}).items()):
        if captured == value:
            return "<var:{}>".format(name)
    return None


def hex32(value, ctx):
    """uuid4().hex: access tokens, OAuth access/refresh tokens."""
    if not isinstance(value, str):
        return value
    var = _var(value, ctx)
    if var:
        return var
    if HEX32.match(value):
        return "<hex32>"
    return value


def authcode(value, ctx):
    """'<country>_' + uuid4().hex. The country prefix is kept, it is input-driven."""
    if not isinstance(value, str):
        return value
    var = _var(value, ctx)
    if var:
        return var
    m = AUTHCODE.match(value)
    if m:
        return "{}_<hex32>".format(m.group(1))
    return value


def token_or_authcode(value, ctx):
    """users.do loginByItToken returns either the auth code or the access token."""
    if not isinstance(value, str):
        return value
    var = _var(value, ctx)
    if var:
        return var
    if HEX32.match(value):
        return "<hex32>"
    return authcode(value, ctx)


def random_alpha(value, ctx):
    """Random request ids (random.sample of ascii_letters) of 4 or 6 letters.

    The length is kept in the placeholder because it differs per endpoint
    (iot: 4, dim/lg: 6) and is part of the observable behaviour.
    """
    if isinstance(value, str) and ALPHA.match(value) and len(value) in (4, 6):
        return "<random-alpha-{}>".format(len(value))
    return value


# (field path, rule). A path is a tuple of dict keys; "*" matches every element
# of a list. Paths are relative to the top level of a JSON response body.
JSON_RULES = [
    # "time": every v1/v2 API envelope (utcnow-based, see ms_epoch).
    (("time",), ms_epoch),
    # common/getTimestamp
    (("data", "timestamp"), ms_epoch),
    # campaign/homePageAlert: serverTime is utcnow-based, nextAlertTime is
    # (local now + 12h).timestamp()
    (("data", "serverTime"), ms_epoch),
    (("data", "nextAlertTime"), ms_epoch),
    # appsvr/oauth_callback: utcnow + 15 days, converted as if it were local
    (("data", "expire_at"), ms_epoch),
    # user/login, checkLogin: uuid4().hex access token
    (("data", "accessToken"), hex32),
    # appsvr/oauth_callback
    (("data", "access_token"), hex32),
    (("data", "refresh_token"), hex32),
    # user/getAuthCode, global/auth/getAuthCode: "<cc>_" + uuid4().hex
    (("data", "authCode"), authcode),
    # newauth.do echoes the posted itToken
    (("authCode",), authcode),
    # users.do loginByItToken
    (("token",), token_or_authcode),
    # iot/dim/lg devmanager request ids, also echoed by the helperbot
    (("id",), random_alpha),
]


def _apply(node, path, rule, ctx):
    if not path:
        return rule(node, ctx)
    head, rest = path[0], path[1:]
    if head == "*":
        if isinstance(node, list):
            return [_apply(item, rest, rule, ctx) for item in node]
        return node
    if isinstance(node, dict) and head in node:
        node = dict(node)
        node[head] = _apply(node[head], rest, rule, ctx)
    return node


def normalise_json(body, now_ms=None, variables=None, rules=None):
    ctx = {"now_ms": now_ms if now_ms is not None else int(time.time() * 1000), "vars": variables or {}}
    for path, rule in rules if rules is not None else JSON_RULES:
        body = _apply(body, path, rule, ctx)
    return body


# XMPP: Bumper generates uuid4() stanza ids for the iq stanzas it sends to a bot
# that reports errno 103. Only the value of attributes named "id", and only
# when it is a uuid, is replaced. Client-chosen ids are echoed and stay as-is.
XMPP_ID_ATTR = re.compile(r"""\bid=(["'])([^"']*)\1""")


def normalise_xmpp(text):
    def repl(m):
        if UUID.match(m.group(2)):
            return "id={0}<uuid>{0}".format(m.group(1))
        return m.group(0)

    return XMPP_ID_ATTR.sub(repl, text)
