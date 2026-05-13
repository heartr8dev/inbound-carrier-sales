"""Server-Sent Events endpoint for live dashboard updates.

``GET /api/v1/calls/stream`` is a long-lived ``text/event-stream`` connection.
The dashboard's ``EventSource`` attaches to it and receives push events
(``call.created`` for now) within ~100ms of a ``POST /calls/log``. The
existing TanStack Query polling stays in place as a recovery mechanism if the
SSE connection drops or the subscriber is on a different worker than the
publisher.

Auth
----
``EventSource`` does not let JavaScript attach custom headers, so the standard
``X-API-Key`` header dependency does not work here. Instead, this route
accepts the key as a query parameter (``?api_key=...``) and validates it with
``secrets.compare_digest`` so the comparison is constant-time. The route is
not wrapped in the ``calls`` router (which auto-requires X-API-Key) — it is
registered separately for that reason.

Process-locality caveat
-----------------------
The ``event_bus`` is in-process. If the API runs with multiple Uvicorn
workers, a subscriber connected to worker A will miss events published on
worker B. See ``api/src/services/events.py`` for details. For the single-
worker compose/dev/Fly setup this is fine; the dashboard's polling fallback
covers the gap for the multi-worker case.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger

from api.src.config import settings
from api.src.services.events import event_bus

router = APIRouter(prefix="/calls", tags=["calls-stream"])

# Heartbeat cadence (seconds). SSE comment lines keep proxies / load balancers
# from idling out the connection. 15s is comfortably below the typical 60s
# nginx ``proxy_read_timeout`` we configure for the stream location.
HEARTBEAT_INTERVAL = 15.0


def _sse_event(event_type: str, data: object) -> str:
    """Format a single SSE message frame.

    The blank line is the message terminator that triggers the browser's
    EventSource dispatch.
    """

    payload = json.dumps(data, default=str, separators=(",", ":"))
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _event_generator(request: Request) -> AsyncIterator[str]:
    """Yield SSE frames to a single connected client until they disconnect.

    Multiplexes two streams:

    * Events from the in-process bus.
    * A periodic heartbeat (SSE comment, doesn't fire onmessage on the
      client) so idle connections don't get reaped by proxies.

    Uses ``event_bus.register``/``unregister`` rather than the async-generator
    helper because we drive the queue with ``asyncio.wait`` so we can also
    block on a heartbeat timer. Mixing ``aclose()`` of a generator with a
    pending ``__anext__`` task triggers "aclose(): asynchronous generator is
    already running" — register/unregister avoids that entirely.
    """

    # Initial frame — handy for clients that want to know the stream is alive
    # before any real events fire.
    yield _sse_event("hello", {"ok": True})

    queue = await event_bus.register()
    get_task: asyncio.Task[dict[str, object]] | None = None
    try:
        while True:
            # Bail out promptly if the client has gone away.
            if await request.is_disconnected():
                break

            if get_task is None:
                get_task = asyncio.create_task(queue.get())

            done, _pending = await asyncio.wait(
                {get_task},
                timeout=HEARTBEAT_INTERVAL,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if get_task in done:
                try:
                    envelope = get_task.result()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("sse_bus_error", error=str(exc))
                    break
                finally:
                    get_task = None
                yield _sse_event(envelope["type"], envelope)  # type: ignore[index]
            else:
                # Heartbeat: SSE comment line. Doesn't dispatch a client
                # event but keeps the TCP / nginx connection warm.
                yield ": keep-alive\n\n"
    finally:
        if get_task is not None and not get_task.done():
            get_task.cancel()
            try:
                await get_task
            except (asyncio.CancelledError, Exception):
                pass
        await event_bus.unregister(queue)


@router.get("/stream")
async def stream_calls(
    request: Request,
    api_key: str = Query(default="", description="API key (EventSource can't send headers)"),
) -> StreamingResponse:
    """SSE stream of call lifecycle events.

    Authenticated via ``?api_key=...`` (constant-time compared). Returns 401
    if the key is missing or wrong. The response uses ``text/event-stream``
    with no caching and the ``X-Accel-Buffering: no`` hint so nginx doesn't
    buffer the chunked body.
    """

    if not api_key or not secrets.compare_digest(api_key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        # Tells nginx not to buffer this response — chunks are flushed to the
        # client as they're generated. Without it, the stream sits in nginx's
        # output buffer until ``proxy_buffer_size`` fills up.
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers=headers,
    )
