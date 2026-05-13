"""Structured request logging + request ID injection via loguru."""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _serialize(record: dict[str, Any]) -> str:
    payload: dict[str, Any] = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "msg": record["message"],
    }
    payload.update(record["extra"])
    return json.dumps(payload, default=str)


def _sink(message: Any) -> None:
    record = message.record
    sys.stdout.write(_serialize(record) + "\n")
    sys.stdout.flush()


def configure_logging() -> None:
    logger.remove()
    logger.add(_sink, level="INFO")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id

        call_id: str | None = None
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
            if body:
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        candidate = parsed.get("call_id")
                        if isinstance(candidate, str):
                            call_id = candidate
                except (ValueError, json.JSONDecodeError):
                    pass

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["x-request-id"] = request_id

        logger.bind(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            status=response.status_code,
            duration_ms=duration_ms,
            call_id=call_id,
        ).info("request")
        return response
