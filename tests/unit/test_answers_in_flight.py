"""
Unit tests: showing results waits for answers that already passed submit_answer's
phase check, so a last-moment answer can't be scored yet missing from the results.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_answers_in_flight.py -v
"""

from __future__ import annotations

import asyncio

from app.websocket import gateway


async def test_nothing_in_flight_returns_immediately():
    await asyncio.wait_for(gateway._wait_for_answers_in_flight("s-idle"), 0.1)


async def test_waits_until_every_answer_in_flight_finishes():
    first, second = asyncio.Event(), asyncio.Event()

    async def submit(release: asyncio.Event):
        async with gateway._answer_in_flight("s1"):
            await release.wait()

    answers = [asyncio.create_task(submit(first)), asyncio.create_task(submit(second))]
    await asyncio.sleep(0)
    waiter = asyncio.create_task(gateway._wait_for_answers_in_flight("s1"))

    first.set()
    await asyncio.sleep(0.01)
    assert not waiter.done(), "one answer is still in flight"

    second.set()
    await asyncio.wait_for(waiter, 0.5)
    await asyncio.gather(*answers)
    assert "s1" not in gateway._answers_in_flight
    assert "s1" not in gateway._answers_settled


async def test_failed_answer_still_counts_as_finished():
    async def failing_submit():
        async with gateway._answer_in_flight("s2"):
            raise RuntimeError("db down")

    try:
        await failing_submit()
    except RuntimeError:
        pass
    await asyncio.wait_for(gateway._wait_for_answers_in_flight("s2"), 0.1)


async def test_gives_up_after_timeout():
    release = asyncio.Event()

    async def stuck():
        async with gateway._answer_in_flight("s3"):
            await release.wait()

    task = asyncio.create_task(stuck())
    await asyncio.sleep(0)
    await gateway._wait_for_answers_in_flight("s3", timeout=0.05)  # no exception
    release.set()
    await task
