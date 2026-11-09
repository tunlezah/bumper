"""Raw-socket XMPP client: send exact stanza strings, record exact replies."""

import socket
import ssl
import time

from . import normalise, tlsutil

STREAM_OPEN_CLIENT = (
    "<stream:stream xmlns='jabber:client' xmlns:stream='http://etherx.jabber.org/streams' "
    "version='1.0' to='ecouser.net'>"
)
STARTTLS = "<starttls xmlns='urn:ietf:params:xml:ns:xmpp-tls'/>"


def stream_open_bot(devclass):
    # As sent by bots in tests/test_xmppserver.py: to='<class>.ecorobot.net'
    return (
        "<stream:stream xmlns:stream='http://etherx.jabber.org/streams' xmlns='jabber:client' "
        "to='{}.ecorobot.net' version='1.0'>".format(devclass)
    )


class XmppConn(object):
    """One XMPP connection. ``exchange`` sends a stanza and returns everything
    the server sent back until the line goes quiet."""

    def __init__(self, target, timeout=10):
        self.target = target
        self.sock = socket.create_connection((target.host, target.port("xmpp")), timeout=timeout)
        self.transcript = []
        self.closed_by_server = False

    def send(self, text):
        self.sock.sendall(text.encode("utf-8"))

    def read_quiet(self, idle=0.4, total=5.0, until=None):
        """Read until nothing arrives for ``idle`` seconds (or ``until`` is in
        the data), at most ``total`` seconds. Returns the decoded text."""
        chunks = []
        deadline = time.time() + total
        while time.time() < deadline:
            self.sock.settimeout(idle)
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                if until is None:
                    break
                continue
            except (ConnectionResetError, ssl.SSLError):
                self.closed_by_server = True
                break
            if not data:
                self.closed_by_server = True
                break
            chunks.append(data)
            if until is not None and until in b"".join(chunks).decode("utf-8", "replace"):
                # keep reading briefly in case more follows in the same burst
                until = None
        return b"".join(chunks).decode("utf-8", "replace")

    def exchange(self, label, text, **kw):
        self.send(text)
        received = self.read_quiet(**kw)
        step = {"step": label, "sent": text, "received": normalise.normalise_xmpp(received)}
        if self.closed_by_server:
            step["closed_by_server"] = True
        self.transcript.append(step)
        return received

    def note(self, label, received):
        step = {"step": label, "received": normalise.normalise_xmpp(received)}
        if self.closed_by_server:
            step["closed_by_server"] = True
        self.transcript.append(step)

    def starttls(self, context=None):
        """Wrap the socket after the server has sent <proceed/>."""
        ctx = context or tlsutil.client_context(self.target.ca_file)
        self.sock.settimeout(10)
        self.sock = ctx.wrap_socket(self.sock)
        return self.sock.version()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
