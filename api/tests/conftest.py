"""Pytest configuration shared by the api/tests suite.

The async tests share the global ``AsyncSessionLocal`` engine, which binds its
connection pool to whichever event loop first touches it. pytest-asyncio's
default function-scoped loop would tear that loop down between tests, leaving
the pool's asyncpg connections orphaned. Each async test in this suite is
explicitly marked with ``@pytest.mark.asyncio(loop_scope="session")``, and the
``client`` fixture uses ``loop_scope="session"`` too — so the engine, the test
client, and all DB sessions live on the same loop for the entire run.

We also dispose the engine on that same loop in a session-scoped autouse
fixture, otherwise pool cleanup at process exit hits a closed-loop error.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from api.src.db import engine


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _dispose_engine_on_session_end() -> AsyncIterator[None]:
    """Dispose the shared async engine on the session loop before it closes."""

    yield
    await engine.dispose()
