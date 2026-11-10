"""bumper.timeutil.utcnow_naive is an exact stand-in for datetime.utcnow()."""

import time
import warnings
from datetime import datetime, timedelta

import pytest

from bumper.timeutil import utcnow_naive


@pytest.fixture
def utc_plus_3(monkeypatch):
    monkeypatch.setenv("TZ", "BHT-3")  # POSIX notation for UTC+3, no DST
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_same_value_as_utcnow():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = datetime.utcnow()
    new = utcnow_naive()
    assert new.tzinfo is None
    assert abs(new - legacy) < timedelta(seconds=1)


def test_timestamp_keeps_the_legacy_offset(utc_plus_3):
    """The legacy API timestamps are off by the UTC offset; the port keeps that."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = datetime.utcnow().timestamp()
    new = utcnow_naive().timestamp()
    assert abs(new - legacy) < 1
    assert abs((time.time() - new) - 3 * 3600) < 5
