#!/usr/bin/env python3
"""Time helpers."""

from datetime import datetime, timezone


def utcnow_naive():
    """Exact replacement for the deprecated ``utcnow()`` classmethod of
    ``datetime``.

    Returns a *naive* datetime holding the current UTC wall-clock time, i.e.
    the same value it returned, so replacing it changes nothing.

    Beware: calling ``.timestamp()`` on the result interprets it as *local*
    time, so the value is off by the server's UTC offset whenever TZ is not
    UTC. Several API responses ("time", "serverTime", getTimestamp) and the
    OAuth expiry have always been computed that way; the harness pins it
    (``<ms-epoch now-3h>`` in UTC+3). Fixing it is a follow-up in
    docs/modernisation/CHANGES.md, not part of the port.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
