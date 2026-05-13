"""Tests for the SSE event stream endpoint.

httpx's ``ASGITransport`` (which the rest of the suite uses) buffers the
entire response body before returning the ``Response`` object — see
``httpx/_transports/asgi.py``: it only resolves once ``response_complete``
fires, which never happens for a long-lived SSE stream.

For the streaming assertions we sidestep httpx entirely and speak raw HTTP/1.1
over an ``asyncio.open_connection`` socket. That keeps the test on whatever
event loop pytest-asyncio gives us with no extra abstractions in the way.
The auth-rejection tests still use the in-process ``ASGITransport`` since a
401 short-response isn't affected by the buffering issue.

The streaming tests require the live API to be reachable on
``http://localhost:8080`` — i.e. they have to run inside the docker-compose
``api`` container (the default for ``docker compose exec -T api pytest``).
They ``pytest.skip`` if no API is listening, so they're inert in environments
where only the in-process app is available.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.src.config import settings
from api.src.main import app

STREAM_PATH = "/api/v1/calls/stream"
LIVE_HOST = os.environ.get("LIVE_API_HOST", "localhost")
LIVE_PORT = int(os.environ.get("LIVE_API_PORT", "8080"))


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncIterator[AsyncClient]:
    """In-process ASGI client — used for 401 short-response assertions."""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _parse_sse_frame(chunk: str) -> tuple[str | None, str | None]:
    """Return (event, data) for an SSE frame string. Comment lines return (None, None)."""

    event: str | None = None
    data: str | None = None
    for line in chunk.splitlines():
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data = line[len("data:") :].strip()
    return event, data


async def _open_sse(
    path: str, *, api_key: str | None = None
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, dict[str, str], int]:
    """Open a raw HTTP/1.1 GET to the live API and return (reader, writer, headers, status).

    The body is left on the reader for the caller to consume frame-by-frame.
    Raises ``ConnectionRefusedError`` if the API isn't running locally.
    """

    query = f"?api_key={quote(api_key)}" if api_key is not None else ""
    request = (
        f"GET {path}{query} HTTP/1.1\r\n"
        f"Host: {LIVE_HOST}:{LIVE_PORT}\r\n"
        f"Accept: text/event-stream\r\n"
        f"Connection: close\r\n\r\n"
    )
    reader, writer = await asyncio.open_connection(LIVE_HOST, LIVE_PORT)
    writer.write(request.encode("ascii"))
    await writer.drain()

    # Status line.
    status_line = (await reader.readline()).decode("ascii", errors="replace")
    parts = status_line.split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 else 0

    # Headers until blank line.
    headers: dict[str, str] = {}
    while True:
        line = (await reader.readline()).decode("ascii", errors="replace")
        if line in ("\r\n", "\n", ""):
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    return reader, writer, headers, status


async def _read_chunked_frame(
    reader: asyncio.StreamReader, timeout: float = 2.0
) -> str:
    """Read enough chunked-transfer-encoded bytes to produce one SSE frame (``\\n\\n``)."""

    buffer = ""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for SSE frame")
        # Read the chunk size line.
        size_line = await asyncio.wait_for(reader.readline(), timeout=remaining)
        if not size_line:
            raise ConnectionError("connection closed before frame arrived")
        try:
            chunk_size = int(size_line.strip().split(b";", 1)[0], 16)
        except ValueError:
            continue
        if chunk_size == 0:
            raise ConnectionError("server closed the stream")
        chunk = await asyncio.wait_for(
            reader.readexactly(chunk_size), timeout=remaining
        )
        # Trailing CRLF after chunk.
        await asyncio.wait_for(reader.readexactly(2), timeout=remaining)
        buffer += chunk.decode("utf-8", errors="replace")
        if "\n\n" in buffer:
            return buffer


async def _post_call_log(api_key: str, call_id: str) -> int:
    """POST a minimal valid call log via a raw HTTP/1.1 socket; return status."""

    body = json.dumps(
        {
            "call_id": call_id,
            "carrier_name": "SSE Unit Test",
            "final_agreed_rate": "1500",
            "transferred": True,
            "negotiation_rounds": 1,
        }
    )
    request = (
        f"POST /api/v1/calls/log HTTP/1.1\r\n"
        f"Host: {LIVE_HOST}:{LIVE_PORT}\r\n"
        f"X-API-Key: {api_key}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
        f"{body}"
    )
    reader, writer = await asyncio.open_connection(LIVE_HOST, LIVE_PORT)
    try:
        writer.write(request.encode("utf-8"))
        await writer.drain()
        status_line = (await reader.readline()).decode("ascii", errors="replace")
        parts = status_line.split(" ", 2)
        status = int(parts[1]) if len(parts) >= 2 else 0
        return status
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def _live_api_reachable() -> bool:
    """Quick TCP probe — skip streaming tests if the live API isn't up."""

    try:
        with socket.create_connection((LIVE_HOST, LIVE_PORT), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.asyncio(loop_scope="session")
async def test_stream_requires_api_key(client: AsyncClient) -> None:
    """Missing api_key → 401."""

    res = await client.get(STREAM_PATH)
    assert res.status_code == 401, res.text


@pytest.mark.asyncio(loop_scope="session")
async def test_stream_rejects_wrong_api_key(client: AsyncClient) -> None:
    """Wrong api_key → 401."""

    res = await client.get(STREAM_PATH, params={"api_key": "definitely-wrong"})
    assert res.status_code == 401, res.text


@pytest.mark.asyncio
async def test_stream_yields_hello() -> None:
    """First chunk on the wire is the ``hello`` event."""

    if not _live_api_reachable():
        pytest.skip(f"Live API not reachable at {LIVE_HOST}:{LIVE_PORT}")

    reader, writer, headers, status = await _open_sse(
        STREAM_PATH, api_key=settings.API_KEY
    )
    try:
        assert status == 200, status
        assert headers.get("content-type", "").startswith("text/event-stream")
        assert headers.get("transfer-encoding") == "chunked"

        frame = await _read_chunked_frame(reader, timeout=2.0)
        event, data = _parse_sse_frame(frame)
        assert event == "hello"
        assert data is not None
        assert json.loads(data) == {"ok": True}
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_publish_reaches_subscriber() -> None:
    """A POST /calls/log event lands on a connected SSE stream within ~1s."""

    if not _live_api_reachable():
        pytest.skip(f"Live API not reachable at {LIVE_HOST}:{LIVE_PORT}")

    api_key = settings.API_KEY
    call_id = f"sse-test-{asyncio.get_event_loop().time():.6f}"

    reader, writer, _headers, status = await _open_sse(STREAM_PATH, api_key=api_key)
    try:
        assert status == 200, status

        # Drain the hello frame.
        hello = await _read_chunked_frame(reader, timeout=2.0)
        assert "hello" in hello, hello

        # Brief gate so the subscriber is definitely registered before POST.
        await asyncio.sleep(0.05)
        post_status = await _post_call_log(api_key, call_id)
        assert post_status == 200, post_status

        # Wait up to ~1.5s for the call.created event.
        frame = await _read_chunked_frame(reader, timeout=1.5)
        event, data = _parse_sse_frame(frame)
        if event is None:
            # Could be a heartbeat — drain one more.
            frame = await _read_chunked_frame(reader, timeout=1.5)
            event, data = _parse_sse_frame(frame)

        assert event == "call.created", (event, frame)
        assert data is not None
        envelope = json.loads(data)
        assert envelope["type"] == "call.created"
        assert envelope["data"]["call_id"] == call_id
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        # Best-effort cleanup of the test row.
        try:
            import psycopg2  # type: ignore

            url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)
            if "+asyncpg" in url:
                url = url.replace("+asyncpg", "")
            with psycopg2.connect(url) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM call_logs WHERE call_id = %s", (call_id,))
                conn.commit()
        except Exception:
            pass
