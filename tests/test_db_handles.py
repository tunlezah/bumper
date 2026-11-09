"""bumper.db keeps one TinyDB open instead of leaking a handle per call."""

import os

import pytest

import bumper
# Not "from bumper import db": bumper.db is the legacy DB *path* override
# global, which shadows the submodule as an attribute.
from bumper.db import db_close, db_get


def open_fds():
    return len(os.listdir("/proc/self/fd"))


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    db_close()
    monkeypatch.setattr(bumper, "db", str(tmp_path / "bumper.db"))
    yield tmp_path / "bumper.db"
    db_close()


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="needs /proc/self/fd")
def test_no_file_handle_leak(tmp_db):
    bumper.user_add("someone")
    before = open_fds()
    for i in range(200):
        bumper.bot_add("sn_{}".format(i), "did_{}".format(i), "ls1ok3", "wC3g", "eco-ng")
        bumper.bot_get("did_{}".format(i))
        bumper.user_add_token("someone", "token_{}".format(i))
    assert open_fds() == before
    assert len(db_get().table("bots").all()) == 200


def test_one_shared_instance(tmp_db):
    assert db_get() is db_get()


def test_path_override_reopens(tmp_db, monkeypatch, tmp_path):
    first = db_get()
    bumper.bot_add("sn", "did_a", "ls1ok3", "wC3g", "eco-ng")
    monkeypatch.setattr(bumper, "db", str(tmp_path / "other.db"))
    second = db_get()
    assert second is not first
    assert bumper.bot_get("did_a") is None
    monkeypatch.setattr(bumper, "db", str(tmp_db))
    assert bumper.bot_get("did_a")["did"] == "did_a"


def test_deleted_file_is_recreated(tmp_db):
    bumper.bot_add("sn", "did_a", "ls1ok3", "wC3g", "eco-ng")
    os.remove(str(tmp_db))
    assert bumper.bot_get("did_a") is None
    bumper.bot_add("sn", "did_b", "ls1ok3", "wC3g", "eco-ng")
    assert tmp_db.exists()
    assert bumper.bot_get("did_b")["did"] == "did_b"


def test_close_is_idempotent(tmp_db):
    db_get()
    db_close()
    db_close()
    assert db_get() is not None
