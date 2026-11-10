"""Minimal stdlib HTTP client that records exactly what the server did."""

import hashlib
import http.client
import json
import time
from urllib.parse import urlencode

from . import normalise, tlsutil


class Outcome(object):
    def __init__(self, status=None, content_type=None, raw=b"", error=None, received_ms=None):
        self.status = status
        self.content_type = content_type
        self.raw = raw
        self.error = error
        self.received_ms = received_ms

    def json(self):
        return json.loads(self.raw.decode("utf-8"))


def request(target, port_name, method, path, body=None, headers=None, timeout=30):
    """Send one request on a fresh connection and return an Outcome.

    A server that closes the connection without answering (legacy aiohttp
    does that when a handler returns ``None``) is recorded as
    ``error="connection closed without response"`` rather than raising.
    """
    host = target.host
    port = target.port(port_name)
    if port_name == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=tlsutil.client_context(target.ca_file))
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    hdrs = {"Connection": "close"}
    hdrs.update(headers or {})
    try:
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        received = int(time.time() * 1000)
        return Outcome(resp.status, resp.getheader("Content-Type"), raw, received_ms=received)
    except http.client.RemoteDisconnected:
        return Outcome(error="connection closed without response", received_ms=int(time.time() * 1000))
    except ConnectionResetError:
        return Outcome(error="connection reset", received_ms=int(time.time() * 1000))
    finally:
        conn.close()


def encode_body(spec):
    """Build (body bytes, headers) from a case's body spec.

    ``{"json": obj}``            application/json
    ``{"form": {k: v}}``         application/x-www-form-urlencoded
    ``{"raw": str, "content_type": str}``  sent verbatim (malformed bodies)
    """
    if not spec:
        return None, {}
    if "json" in spec:
        return json.dumps(spec["json"]).encode("utf-8"), {"Content-Type": "application/json"}
    if "form" in spec:
        return urlencode(spec["form"]).encode("utf-8"), {"Content-Type": "application/x-www-form-urlencoded"}
    if "raw" in spec:
        headers = {}
        if spec.get("content_type"):
            headers["Content-Type"] = spec["content_type"]
        return spec["raw"].encode("utf-8"), headers
    raise ValueError("unknown body spec {!r}".format(spec))


def describe(outcome, variables=None):
    """Turn an Outcome into the normalised, JSON-serialisable golden record."""
    if outcome.error:
        return {"error": outcome.error}
    record = {"status": outcome.status, "content_type": outcome.content_type}
    ctype = (outcome.content_type or "").split(";")[0].strip()
    if ctype == "application/json":
        try:
            body = outcome.json()
        except ValueError:
            record["body_text"] = outcome.raw.decode("utf-8", "replace")
        else:
            record["body"] = normalise.normalise_json(body, now_ms=outcome.received_ms, variables=variables)
    elif ctype.startswith("text/") or ctype == "":
        record["body_text"] = outcome.raw.decode("utf-8", "replace")
    else:
        record["body_bytes"] = {"length": len(outcome.raw), "sha256": hashlib.sha256(outcome.raw).hexdigest()}
    return record
