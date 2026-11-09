from unittest import mock
from unittest.mock import patch
import pytest
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, Query
import bumper
import os
import platform
import json
import asyncio


def test_strtobool():
    assert bumper.strtobool("t") == True
    assert bumper.strtobool("f") == False
    assert bumper.strtobool(0) == False


@pytest.fixture
def ephemeral_ports(free_port, monkeypatch):
    for name in ("mqtt_listen_port", "conf1_listen_port", "conf2_listen_port", "xmpp_listen_port"):
        monkeypatch.setattr(bumper, name, free_port())


async def stop_everything(start_task):
    """start() loops until shutting_down; stop it and the helperbot client
    (shutdown() leaves the helperbot reconnecting, as it always did)."""
    start_task.cancel()
    await asyncio.gather(start_task, return_exceptions=True)
    if bumper.mqtt_helperbot is not None and bumper.mqtt_helperbot.Client is not None:
        await bumper.mqtt_helperbot.Client.cancel_tasks()
    await asyncio.gather(*bumper.tasks.pending(), return_exceptions=True)
    # shutdown() does not stop the web sites started by start_site()
    # (legacy, CHANGES.md F-04); close their sockets here.
    if bumper.conf_server is not None:
        for runner in bumper.conf_server.runners:
            await runner.cleanup()


async def test_start_stop(log_capture, ephemeral_ports):
    with log_capture() as l:
        if bumper.db and os.path.exists(bumper.db):
            os.remove(bumper.db)  # Remove existing db

        b = bumper
        b.conf1_listen_address = "127.0.0.1"
        start_task = asyncio.create_task(b.start())
        await asyncio.sleep(0.1)
        l.check_present(("bumper", "INFO", "Starting Bumper"))
        l.clear()

        await asyncio.create_task(b.shutdown())
        await asyncio.sleep(0.1)
        l.check_present(
            ("bumper", "INFO", "Shutting down"), ("bumper", "INFO", "Shutdown complete")
        )
        assert b.shutting_down == True
        await stop_everything(start_task)


async def test_start_stop_debug(log_capture, ephemeral_ports):
    with log_capture() as l:
        if bumper.db and os.path.exists(bumper.db):
            os.remove(bumper.db)  # Remove existing db

        b = bumper
        b.bumper_listen = "0.0.0.0"
        b.bumper_debug = True
        start_task = asyncio.create_task(b.start())

        await asyncio.sleep(0.1)
        shutdown_task = asyncio.create_task(b.shutdown())
        l.check_present(("bumper", "INFO", "Starting Bumper"))
        l.clear()
        await shutdown_task
        await asyncio.sleep(0.1)
        l.check_present(
            ("bumper", "INFO", "Shutting down"), ("bumper", "INFO", "Shutdown complete")
        )
        assert b.shutting_down == True
        await stop_everything(start_task)
