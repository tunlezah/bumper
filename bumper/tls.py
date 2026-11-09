#!/usr/bin/env python3
"""Server-side TLS for all of Bumper's TLS listeners.

The HTTPS config server (443), the MQTT broker (8883) and XMPP STARTTLS (5223)
all get their SSLContext from ``server_context()``.

Policy
------
Legacy Bumper accepted TLS 1.0 and newer: before Python 3.10
``ssl.create_default_context()`` set no minimum version, and the 2021 Docker
image ran OpenSSL 1.1.1, which allows TLS 1.0/1.1 at its default security
level (see docs/modernisation/BASELINE.md). Older robots, in particular the
XMPP models, may only speak TLS 1.0, so the default here is the same:
``BUMPER_TLS_MIN_VERSION=TLSv1``.

On current Python and OpenSSL 3 that takes two explicit settings:
``minimum_version = TLSv1`` (Python >= 3.10 defaults to TLS 1.2) and a cipher
string with ``@SECLEVEL=0`` (OpenSSL 3 refuses TLS 1.0/1.1 at any higher
security level). Both are only applied when the configured minimum is below
TLS 1.2; set ``BUMPER_TLS_MIN_VERSION`` to ``TLSv1_2`` or ``TLSv1_3`` to get
Python's default ciphers and security level back.

Every accepted TLS connection is logged at INFO with the negotiated version
and cipher (``log_connection``), so users can see what their robots use.
"""

import logging
import os
import ssl
import warnings

tlslog = logging.getLogger("bumper.tls")

MIN_VERSIONS = {
    "TLSv1": ssl.TLSVersion.TLSv1,
    "TLSv1_1": ssl.TLSVersion.TLSv1_1,
    "TLSv1_2": ssl.TLSVersion.TLSv1_2,
    "TLSv1_3": ssl.TLSVersion.TLSv1_3,
}
DEFAULT_MIN_VERSION = "TLSv1"

# Python 3.8/3.9's default cipher string (what the legacy code ran with on
# those versions), plus @SECLEVEL=0. Only used when TLS < 1.2 is allowed.
LEGACY_CIPHERS = "DEFAULT:!aNULL:!eNULL:!MD5:!3DES:!DES:!RC4:!IDEA:!SEED:!aDSS:!SRP:!PSK:@SECLEVEL=0"


def min_version_name(value=None):
    """Validated minimum TLS version name, from ``value`` or the environment."""
    name = value if value is not None else os.environ.get("BUMPER_TLS_MIN_VERSION")
    name = (name or DEFAULT_MIN_VERSION).strip()
    if name not in MIN_VERSIONS:
        raise ValueError(
            "BUMPER_TLS_MIN_VERSION must be one of {}, not {!r}".format(", ".join(MIN_VERSIONS), name)
        )
    return name


def server_context(certfile, keyfile, min_version=None, request_client_cert=False):
    """SSLContext for a Bumper TLS server.

    ``request_client_cert`` keeps the MQTT broker's legacy behaviour of asking
    for (but not requiring) a client certificate (``CERT_OPTIONAL``, verified
    against the system CAs, as before). HTTPS and XMPP never asked.
    """
    name = min_version_name(min_version)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile, keyfile)
    if MIN_VERSIONS[name] < ssl.TLSVersion.TLSv1_2:
        ctx.set_ciphers(LEGACY_CIPHERS)
    with warnings.catch_warnings():
        # Python >= 3.12 emits a DeprecationWarning for TLSv1/TLSv1_1.
        # Accepting them is the deliberate, documented default (see above).
        warnings.simplefilter("ignore", DeprecationWarning)
        ctx.minimum_version = MIN_VERSIONS[name]
    if request_client_cert:
        ctx.verify_mode = ssl.CERT_OPTIONAL
    return ctx


def describe_policy(min_version=None):
    name = min_version_name(min_version)
    if MIN_VERSIONS[name] < ssl.TLSVersion.TLSv1_2:
        return "minimum {} (OpenSSL security level 0; set BUMPER_TLS_MIN_VERSION=TLSv1_2 to tighten)".format(name)
    return "minimum {}".format(name)


def log_connection(service, peername, ssl_object):
    """One INFO line per accepted TLS connection."""
    if ssl_object is None:
        return
    cipher = ssl_object.cipher()
    peer = "{}:{}".format(peername[0], peername[1]) if peername else "unknown peer"
    tlslog.info(
        "TLS {} connection from {}: {} {}".format(
            service, peer, ssl_object.version(), cipher[0] if cipher else "unknown cipher"
        )
    )
