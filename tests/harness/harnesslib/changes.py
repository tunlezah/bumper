"""Machine-checkable descriptions of the deliberate behaviour changes.

Every file in golden_changes/ names the change(s) it implements. The static
test test_golden_changes.py diffs its ``expected`` block against the legacy
golden and requires **every** differing node to be explained by one of those
changes' predicates below. An override can therefore not silently absorb an
unrelated regression. Each change id must also have a section in
docs/modernisation/CHANGES.md.

A predicate is called as ``predicate(name, path, old, new)`` for one minimal
differing node (``path`` is a tuple of keys/indices into the golden) and
returns True if the change explains it.
"""

import json
import os
import re

from . import config

INTERNAL_SERVER_ERROR = {
    "status": 500,
    "content_type": "text/plain; charset=utf-8",
    "body_text": "500: Internal Server Error",
}


def c001_handler_errors_are_500(name, path, old, new):
    """aiohttp 3.6 dropped the connection when a handler returned None (an
    internal AttributeError); current aiohttp answers 500."""
    return old == {"error": "connection closed without response"} and new == INTERNAL_SERVER_ERROR


def c002_mqtt_auth_failure_connack(name, path, old, new):
    """hbmqtt closed refused connections without CONNACK; amqtt sends CONNACK
    0x05 (Not authorized) first."""
    return bool(path) and path[-1] == "connack" and old == "connection closed without CONNACK" and new == "Not authorized"


# One iteration of the session-table loop in home.jinja2 for a session whose
# state is "disconnected", with the template's exact whitespace.
_DISCONNECTED_ROW = re.compile(
    r"\n        <TR>\n            <TD>[^<]*</TD>\n            <TD>[^<]*</TD>       \n"
    r"            <TD > disconnected </TD>\n        </TR>\n        "
)
_SESSION_COUNT = re.compile(r"Sessions: (\d+)")


_SESSION_ROW_STATE = re.compile(r"<TD[^>]*> (\w+) </TD>\s*</TR>$")


def c003_no_disconnected_mqtt_sessions(name, path, old, new):
    """The status page lists only connected MQTT sessions. Legacy kept
    disconnected sessions ("disconnected") and refused logins ("new") forever.

    Either a list of selected status-page rows became empty and every old row
    was in one of those states, or (full page) old minus its "disconnected"
    session rows, with the count adjusted, equals new."""
    if bool(path) and path[-1] == "status_rows" and isinstance(old, list) and new == []:
        states = [_SESSION_ROW_STATE.search(row) for row in old]
        return bool(old) and all(m and m.group(1) in ("new", "disconnected") for m in states)
    if not (bool(path) and path[-1] == "body_text" and isinstance(old, str) and isinstance(new, str)):
        return False
    removed = len(_DISCONNECTED_ROW.findall(old))
    if not removed:
        return False
    stripped = _DISCONNECTED_ROW.sub("", old)
    m = _SESSION_COUNT.search(stripped)
    if not m:
        return False
    stripped = stripped[: m.start(1)] + str(int(m.group(1)) - removed) + stripped[m.end(1) :]
    return stripped == new


def c004_tls_policy(name, path, old, new):
    """TLS 1.0 and 1.1 accepted on every TLS endpoint (behaviour of the 2021
    image on OpenSSL 1.1.1; see BASELINE.md)."""
    return (
        name == "tls_matrix"
        and len(path) == 1
        and path[0].split(" ")[1] in ("TLSv1", "TLSv1_1")
        and old == "rejected"
        and new == "accepted"
    )


REFERENCE_DIR = os.path.join(config.HARNESS_DIR, "golden_reference", "py37")


def _reference(name):
    path = os.path.join(REFERENCE_DIR, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _at(obj, path):
    for key in path:
        obj = obj[key]
    return obj


def c005_getchildren(name, path, old, new):
    """Element.getchildren() was removed in Python 3.9. With the fix, the node
    must equal what the *unmodified* legacy code produced on Python 3.7, where
    getchildren() still existed (golden_reference/py37/, see its README)."""
    ref = _reference(name)
    if ref is None:
        return False
    try:
        return _at(ref, path) == new
    except (KeyError, IndexError, TypeError):
        return False


PREDICATES = {
    "C-001": c001_handler_errors_are_500,
    "C-002": c002_mqtt_auth_failure_connack,
    "C-003": c003_no_disconnected_mqtt_sessions,
    "C-004": c004_tls_policy,
    "C-005": c005_getchildren,
}


def minimal_diffs(old, new, path=()):
    """Smallest differing nodes between two JSON trees. Dicts with the same
    keys and lists of the same length are descended into; anything else that
    differs is reported as one node."""
    if old == new:
        return []
    if isinstance(old, dict) and isinstance(new, dict) and set(old) == set(new):
        out = []
        for key in sorted(old):
            out.extend(minimal_diffs(old[key], new[key], path + (key,)))
        return out
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        out = []
        for i, (o, n) in enumerate(zip(old, new)):
            out.extend(minimal_diffs(o, n, path + (i,)))
        return out
    return [(path, old, new)]
