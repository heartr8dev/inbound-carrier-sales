"""In-process publish/subscribe event bus for SSE fan-out.

The bus is a singleton instantiated at module import (``event_bus``). Routes
that want to push state changes to connected dashboards call
``await event_bus.publish(...)`` and any active subscriber generator
(typically the SSE stream route) receives the envelope on its private queue.

Caveats
-------
This bus is **in-process only**. There is no Redis, no pub/sub fan-out across
workers, no cross-machine replication. Two important consequences:

1. A multi-worker Uvicorn deployment (``--workers 4``) will only deliver an
   event to subscribers attached to the *same* worker that handled the
   ``POST /calls/log``. The dashboard's SSE connection may land on a different
   worker and miss the event.

2. A multi-machine Fly deployment (more than one ``app`` machine) will not
   share state at all. Each machine has its own ``event_bus``.

Both cases are acceptable for the demo because:

* The TanStack Query polling fallback (30s) still recovers state on
  subscribers that miss a push.
* The dev/prod compose stack runs a single Uvicorn worker.

If we ever scale beyond one process we replace this with a Redis pub/sub
backend behind the same ``publish``/``subscribe`` API.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from loguru import logger

QUEUE_MAXSIZE = 100


class EventBus:
    """Multi-subscriber asyncio fan-out bus.

    Each subscriber owns a bounded ``asyncio.Queue``. Publishers push the same
    envelope onto every subscriber's queue without blocking — if a queue is
    full (a slow subscriber), the event is dropped for that subscriber and a
    warning is logged. The bus never applies backpressure to the producer.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    async def register(self) -> asyncio.Queue[dict[str, Any]]:
        """Allocate and register a new subscriber queue.

        The caller is responsible for ``await self.unregister(queue)`` in a
        ``finally`` so the bus does not accumulate dead queues. We use an
        explicit register/unregister pair rather than an async generator
        because the SSE route multiplexes the queue with a heartbeat timer,
        and Python's generator protocol does not allow ``aclose()`` while a
        task is awaiting the generator's next item (RuntimeError: aclose():
        asynchronous generator is already running).
        """

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers.append(queue)
        return queue

    async def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Drop ``queue`` from the subscriber list. Safe to call twice."""

        async with self._lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                pass

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Async-generator convenience wrapper around ``register``.

        Suitable for simple ``async for event in bus.subscribe():`` loops. The
        SSE route uses ``register``/``unregister`` directly because it needs
        to multiplex the queue with a heartbeat timer.
        """

        queue = await self.register()
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            await self.unregister(queue)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Fan out an event envelope to all current subscribers.

        ``put_nowait`` is used so a slow subscriber can never stall the
        producer. A full queue means the subscriber's stream is lagging — we
        drop the event for them and emit a warning rather than block the
        request that triggered the publish.
        """

        envelope = {
            "type": event_type,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        # Snapshot the subscriber list under the lock so a concurrent
        # subscribe/unsubscribe can't race us. We then release the lock before
        # touching the queues — put_nowait is itself non-blocking.
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                logger.warning(
                    "event_bus_drop",
                    event_type=event_type,
                    qsize=queue.qsize(),
                    maxsize=QUEUE_MAXSIZE,
                )

    @property
    def subscriber_count(self) -> int:
        """Diagnostic helper — number of currently attached subscribers."""

        return len(self._subscribers)


event_bus = EventBus()
