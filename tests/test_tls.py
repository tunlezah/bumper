"""bumper.tls: the shared server-side TLS policy."""

import logging
import os
import socket
import ssl
import threading
import warnings

import pytest

from bumper import tls

CERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_certs")
CERT = os.path.join(CERTS, "bumper.crt")
KEY = os.path.join(CERTS, "bumper.key")
CA = os.path.join(CERTS, "ca.crt")


def client_for(version):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.load_verify_locations(CA)
    if version < ssl.TLSVersion.TLSv1_2:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        ctx.minimum_version = version
        ctx.maximum_version = version
    return ctx


def handshake(server_ctx, client_ctx):
    """Negotiated version, or None if the handshake failed."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        try:
            conn, _ = listener.accept()
            with server_ctx.wrap_socket(conn, server_side=True) as s:
                s.recv(1)
        except (OSError, ssl.SSLError):
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    try:
        with socket.create_connection(listener.getsockname(), timeout=5) as raw:
            with client_ctx.wrap_socket(raw) as s:
                version = s.version()
                s.sendall(b"x")
                return version
    except (OSError, ssl.SSLError):
        return None
    finally:
        t.join(5)
        listener.close()


def openssl_can(version):
    """This OpenSSL build can do ``version`` at all (with itself)."""
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(CERT, KEY)
    server.set_ciphers("DEFAULT:@SECLEVEL=0")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        server.minimum_version = version
    return handshake(server, client_for(version)) is not None


def test_min_version_default_and_env(monkeypatch):
    monkeypatch.delenv("BUMPER_TLS_MIN_VERSION", raising=False)
    assert tls.min_version_name() == "TLSv1"
    monkeypatch.setenv("BUMPER_TLS_MIN_VERSION", "TLSv1_2")
    assert tls.min_version_name() == "TLSv1_2"
    assert tls.min_version_name("TLSv1_3") == "TLSv1_3"


def test_invalid_min_version_is_rejected(monkeypatch):
    monkeypatch.setenv("BUMPER_TLS_MIN_VERSION", "SSLv3")
    with pytest.raises(ValueError, match="BUMPER_TLS_MIN_VERSION"):
        tls.server_context(CERT, KEY)


def test_default_context_allows_tls1_without_warnings(monkeypatch):
    monkeypatch.delenv("BUMPER_TLS_MIN_VERSION", raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ctx = tls.server_context(CERT, KEY)
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1
    assert ctx.verify_mode == ssl.CERT_NONE


def test_tightened_context_keeps_python_defaults():
    ctx = tls.server_context(CERT, KEY, min_version="TLSv1_2")
    default = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2
    assert [c["name"] for c in ctx.get_ciphers()] == [c["name"] for c in default.get_ciphers()]


def test_mqtt_flavour_requests_optional_client_cert():
    assert tls.server_context(CERT, KEY, request_client_cert=True).verify_mode == ssl.CERT_OPTIONAL


@pytest.mark.parametrize("name", ["TLSv1", "TLSv1_1", "TLSv1_2", "TLSv1_3"])
def test_default_policy_accepts_every_version(monkeypatch, name):
    version = tls.MIN_VERSIONS[name]
    if not openssl_can(version):
        pytest.skip("this OpenSSL cannot negotiate {} at all".format(name))
    monkeypatch.delenv("BUMPER_TLS_MIN_VERSION", raising=False)
    assert handshake(tls.server_context(CERT, KEY), client_for(version)) == name.replace("_", ".")


def test_tightened_policy_refuses_tls1():
    if not openssl_can(ssl.TLSVersion.TLSv1):
        pytest.skip("this OpenSSL cannot negotiate TLSv1 at all")
    ctx = tls.server_context(CERT, KEY, min_version="TLSv1_2")
    assert handshake(ctx, client_for(ssl.TLSVersion.TLSv1)) is None
    assert handshake(ctx, client_for(ssl.TLSVersion.TLSv1_2)) == "TLSv1.2"


def test_log_connection(caplog):
    class FakeSSLObject:
        def version(self):
            return "TLSv1"

        def cipher(self):
            return ("ECDHE-RSA-AES256-SHA", "TLSv1.0", 256)

    with caplog.at_level(logging.INFO, logger="bumper.tls"):
        tls.log_connection("XMPP", ("192.0.2.7", 40000), FakeSSLObject())
        tls.log_connection("XMPP", ("192.0.2.7", 40001), None)  # plain connection: nothing
    assert caplog.messages == ["TLS XMPP connection from 192.0.2.7:40000: TLSv1 ECDHE-RSA-AES256-SHA"]
