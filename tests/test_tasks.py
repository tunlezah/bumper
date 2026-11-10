"""bumper.tasks.spawn keeps fire-and-forget tasks alive until they finish."""

import asyncio
import gc

from bumper import tasks


async def test_spawned_task_survives_garbage_collection():
    finished = asyncio.Event()

    async def work():
        await asyncio.sleep(0.05)
        finished.set()

    tasks.spawn(work())  # no reference kept by the caller
    gc.collect()
    assert any(not t.done() for t in tasks.pending())
    await asyncio.wait_for(finished.wait(), timeout=2)
    await asyncio.sleep(0)  # let the done-callback run
    assert not any(t.done() for t in tasks.pending())  # finished tasks were dropped


async def test_spawn_returns_the_task_and_forgets_it_when_done():
    task = tasks.spawn(asyncio.sleep(0))
    assert task in tasks.pending()
    await task
    await asyncio.sleep(0)
    assert task not in tasks.pending()
