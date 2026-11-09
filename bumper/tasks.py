#!/usr/bin/env python3
"""Fire-and-forget background tasks.

The event loop keeps only weak references to tasks, so a task created with
``asyncio.create_task()`` and not stored anywhere can be garbage-collected
before it finishes (see the note on ``asyncio.create_task`` in the Python
docs). ``spawn()`` keeps a strong reference until the task is done.
"""

import asyncio

_background_tasks = set()


def spawn(coro):
    """Schedule ``coro`` on the running loop and keep it alive until it finishes."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def pending():
    """Background tasks that have not finished yet (for tests and shutdown)."""
    return set(_background_tasks)
