"""Which TLS protocol versions each TLS endpoint accepts.

For 443 (HTTPS), 8883 (MQTT) and 5223 (XMPP, after STARTTLS) the harness
offers exactly one protocol version per handshake and records whether the
server completes it. The client side allows TLS 1.0/1.1 explicitly
(``@SECLEVEL=0``, min=max=version). If this interpreter's OpenSSL cannot
negotiate a version with itself at all, that probe is xfailed: a "rejected"
would describe the client, not the server.
"""

import socket
import ssl

import pytest

from harnesslib import golden, tlsutil
from harnesslib.xmppclient import STARTTLS, STREAM_OPEN_CLIENT, XmppConn

ENDPOINTS = ["https", "mqtt", "xmpp"]


def _probe(target, endpoint, version):
    ctx = tlsutil.pinned_context(target.ca_file, version)
    expected = version.replace("_", ".")
    try:
        if endpoint == "xmpp":
            conn = XmppConn(target)
            try:
                conn.send(STREAM_OPEN_CLIENT)
                conn.read_quiet(until="</stream:features>")
                conn.send(STARTTLS)
                conn.read_quiet(until="proceed")
                negotiated = conn.starttls(ctx)
            finally:
                conn.close()
        else:
            with socket.create_connection((target.host, target.port(endpoint)), timeout=10) as raw:
                with ctx.wrap_socket(raw) as tls:
                    negotiated = tls.version()
    except (ssl.SSLError, OSError):
        return "rejected"
    return "accepted" if negotiated == expected else "negotiated {}".format(negotiated)


@pytest.mark.parametrize("version", tlsutil.VERSIONS)
@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_tls_version(target, endpoint, version):
    if not tlsutil.local_openssl_supports(version):
        pytest.xfail("this interpreter's OpenSSL cannot negotiate {} even with itself".format(version))
    golden.check_cell("tls_matrix", "{} {}".format(endpoint, version), _probe(target, endpoint, version))
