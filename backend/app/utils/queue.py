import asyncio
from asyncio import QueueEmpty, QueueFull
from contextlib import suppress
from typing import TypeVar

T = TypeVar("T")


def put_with_overflow(queue: "asyncio.Queue[T]", item: T) -> bool:
    try:
        queue.put_nowait(item)
        return True
    except QueueFull:
        with suppress(QueueEmpty):
            queue.get_nowait()
        try:
            queue.put_nowait(item)
            return True
        except QueueFull:
            return False


async def drain_queue(queue: "asyncio.Queue[T]") -> list[T]:
    first = await queue.get()
    buffer = [first]

    while True:
        try:
            buffer.append(queue.get_nowait())
        except QueueEmpty:
            break

    return buffer
