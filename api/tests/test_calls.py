"""Tests for the call classification service and the /api/v1/calls routes.

The HTTP layer is exercised through ``httpx.ASGITransport`` against the live
FastAPI app, which means the async ``AsyncSessionLocal`` engine is touched on
whatever loop pytest-asyncio gives us. To avoid event-loop reuse issues, all
direct DB seeding + teardown in this file is done via a synchronous psycopg2
connection — that path doesn't share the engine pool and is immune to loop
churn. Each test uses a unique ``call_id`` tag so the suite is safe to re-run
against a shared DB.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.src.config import settings
from api.src.main import app
from api.src.schemas.call import CallLogRequest
from api.src.schemas.enums import CallOutcome, CarrierSentiment
from api.src.services.call_classifier import classify_outcome, classify_sentiment

API_PREFIX = "/api/v1"


# --------------------------------------------------------------------------- #
# Shared helpers.
# --------------------------------------------------------------------------- #


def _sync_dsn() -> str:
    """Build a psycopg2-compatible DSN from settings.DATABASE_URL.

    The async URL uses ``postgresql+asyncpg://``; psycopg2 wants plain
    ``postgresql://``.
    """

    url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return url


def _make_request(**overrides: object) -> CallLogRequest:
    """Build a ``CallLogRequest`` with sane defaults, overridable per-test."""

    base: dict[str, object] = {
        "call_id": f"test-{uuid.uuid4()}",
        "carrier_mc": "123456",
        "carrier_name": "Test Driver",
        "carrier_company": "Test Carrier LLC",
        "final_agreed_rate": None,
        "transferred": False,
        "vetting_passed": None,
        "loads_searched": False,
        "matches_returned": 0,
        "negotiation_rounds": 0,
    }
    base.update(overrides)
    return CallLogRequest(**base)


def _insert_call_log(
    cur: "psycopg2.extensions.cursor",
    *,
    call_id: str,
    outcome: CallOutcome,
    sentiment: CarrierSentiment,
    created_at: datetime,
    negotiation_rounds: int = 0,
    final_agreed_rate: Decimal | None = None,
    carrier_name: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO call_logs (
            id, call_id, outcome, sentiment, negotiation_rounds,
            final_agreed_rate, carrier_name, created_at
        )
        VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            call_id,
            outcome.value,
            sentiment.value,
            negotiation_rounds,
            final_agreed_rate,
            carrier_name,
            created_at,
        ),
    )


# --------------------------------------------------------------------------- #
# 1. Outcome classification — one fixture per branch (7 total).
# --------------------------------------------------------------------------- #


def test_classify_transferred_to_rep() -> None:
    req = _make_request(final_agreed_rate=Decimal("2500"), transferred=True)
    assert classify_outcome(req) is CallOutcome.TRANSFERRED_TO_REP


def test_classify_booked() -> None:
    req = _make_request(final_agreed_rate=Decimal("2500"), transferred=False)
    assert classify_outcome(req) is CallOutcome.BOOKED


def test_classify_carrier_failed_vetting() -> None:
    req = _make_request(vetting_passed=False)
    assert classify_outcome(req) is CallOutcome.CARRIER_FAILED_VETTING


def test_classify_no_matching_loads() -> None:
    req = _make_request(loads_searched=True, matches_returned=0, vetting_passed=True)
    assert classify_outcome(req) is CallOutcome.NO_MATCHING_LOADS


def test_classify_negotiation_stalled() -> None:
    req = _make_request(
        loads_searched=True,
        matches_returned=2,
        negotiation_rounds=3,
        final_agreed_rate=None,
    )
    assert classify_outcome(req) is CallOutcome.NEGOTIATION_STALLED


def test_classify_carrier_declined_rate() -> None:
    req = _make_request(
        loads_searched=True,
        matches_returned=2,
        negotiation_rounds=1,
        final_agreed_rate=None,
    )
    assert classify_outcome(req) is CallOutcome.CARRIER_DECLINED_RATE


def test_classify_carrier_hung_up_default() -> None:
    req = _make_request()  # no rate, no vetting fail, no search, no rounds
    assert classify_outcome(req) is CallOutcome.CARRIER_HUNG_UP


# --------------------------------------------------------------------------- #
# 2/3. Sentiment classification.
# --------------------------------------------------------------------------- #


def test_sentiment_from_request_overrides_heuristic() -> None:
    """Agent-provided sentiment wins even when transcript would suggest otherwise."""

    req = _make_request(
        sentiment=CarrierSentiment.POSITIVE,
        transcript_summary="this is bullshit and a fuck up",
    )
    assert classify_sentiment(req) is CarrierSentiment.POSITIVE


def test_sentiment_heuristic_detects_hostile_keywords() -> None:
    req = _make_request(
        sentiment=None,
        transcript_summary="What a ridiculous rate, no way I'm taking that bullshit.",
    )
    assert classify_sentiment(req) is CarrierSentiment.HOSTILE


def test_sentiment_heuristic_detects_positive_keywords() -> None:
    req = _make_request(
        sentiment=None,
        transcript_summary="Thanks, that's a great rate, perfect.",
    )
    assert classify_sentiment(req) is CarrierSentiment.POSITIVE


def test_sentiment_heuristic_defaults_to_neutral() -> None:
    req = _make_request(sentiment=None, transcript_summary=None)
    assert classify_sentiment(req) is CarrierSentiment.NEUTRAL


# --------------------------------------------------------------------------- #
# Route fixtures — async httpx client + sync DB cleanup.
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": settings.API_KEY},
    ) as ac:
        yield ac


@pytest.fixture
def cleanup_call_ids() -> Iterator[list[str]]:
    """Collects call_ids created by a test and deletes them on teardown via psycopg2.

    Using a sync DB connection in the fixture avoids any pytest-asyncio
    event-loop interaction in teardown.
    """

    ids: list[str] = []
    yield ids
    if ids:
        with psycopg2.connect(_sync_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM call_logs WHERE call_id = ANY(%s)", (ids,))
            conn.commit()


# --------------------------------------------------------------------------- #
# 4. POST /calls/log — happy path + duplicate.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_post_log_inserts_row_and_duplicate_returns_409(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    call_id = f"test-{uuid.uuid4()}"
    cleanup_call_ids.append(call_id)

    body = {
        "call_id": call_id,
        "carrier_mc": "654321",
        "carrier_name": "Alice Trucker",
        "final_agreed_rate": "2500.00",
        "transferred": True,
        "negotiation_rounds": 2,
        "loadboard_rate": "2400.00",
        "initial_carrier_ask": "2700.00",
        "transcript_summary": "Perfect, thanks for the great rate.",
    }
    res = await client.post(f"{API_PREFIX}/calls/log", json=body)
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["call_id"] == call_id
    assert payload["outcome"] == CallOutcome.TRANSFERRED_TO_REP.value
    assert payload["sentiment"] == CarrierSentiment.POSITIVE.value

    # Verify the row landed in the DB with the classified columns (sync read).
    with psycopg2.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT outcome, sentiment, carrier_name FROM call_logs WHERE call_id = %s",
            (call_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == CallOutcome.TRANSFERRED_TO_REP.value
    assert row[1] == CarrierSentiment.POSITIVE.value
    assert row[2] == "Alice Trucker"

    # Duplicate POST → 409.
    res2 = await client.post(f"{API_PREFIX}/calls/log", json=body)
    assert res2.status_code == 409, res2.text


# --------------------------------------------------------------------------- #
# 5. GET /calls — pagination.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_get_calls_pagination_returns_correct_slice(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    """Insert 50 rows in a unique narrow time window, paginate page 2 of size 20.

    We scope the GET query by a tight date range so other rows in the DB don't
    pollute the total/order assertions.
    """

    tag = f"page-{uuid.uuid4().hex[:8]}"
    # A narrow 60-second window placed well in the past so concurrent test
    # rows from other tests can't fall inside it.
    base_time = datetime.now(tz=timezone.utc) - timedelta(hours=2)

    with psycopg2.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        for i in range(50):
            cid = f"{tag}-{i:02d}"
            cleanup_call_ids.append(cid)
            _insert_call_log(
                cur,
                call_id=cid,
                outcome=CallOutcome.CARRIER_HUNG_UP,
                sentiment=CarrierSentiment.NEUTRAL,
                created_at=base_time + timedelta(seconds=i),
                negotiation_rounds=0,
                carrier_name=tag,
            )
        conn.commit()

    params = {
        "from": (base_time - timedelta(seconds=1)).isoformat(),
        "to": (base_time + timedelta(seconds=60)).isoformat(),
        "page": 2,
        "page_size": 20,
    }
    res = await client.get(f"{API_PREFIX}/calls", params=params)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] == 50
    assert data["page"] == 2
    assert data["page_size"] == 20
    assert len(data["items"]) == 20

    # Order is created_at DESC. page 1 covers i=49..30, page 2 covers i=29..10.
    first_call_id = data["items"][0]["call_id"]
    last_call_id = data["items"][-1]["call_id"]
    assert first_call_id == f"{tag}-29"
    assert last_call_id == f"{tag}-10"


# --------------------------------------------------------------------------- #
# 6. GET /calls — outcome filter.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_get_calls_filter_by_outcome(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    tag = f"outcome-{uuid.uuid4().hex[:8]}"
    # Use a tight time window per-test so we can scope the filter to just our rows.
    base_time = datetime.now(tz=timezone.utc) - timedelta(hours=3)

    with psycopg2.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        for i in range(3):
            cid = f"{tag}-booked-{i}"
            cleanup_call_ids.append(cid)
            _insert_call_log(
                cur,
                call_id=cid,
                outcome=CallOutcome.BOOKED,
                sentiment=CarrierSentiment.POSITIVE,
                created_at=base_time + timedelta(seconds=i),
                negotiation_rounds=1,
                final_agreed_rate=Decimal("2500"),
            )
        for i in range(2):
            cid = f"{tag}-hung-{i}"
            cleanup_call_ids.append(cid)
            _insert_call_log(
                cur,
                call_id=cid,
                outcome=CallOutcome.CARRIER_HUNG_UP,
                sentiment=CarrierSentiment.NEUTRAL,
                created_at=base_time + timedelta(seconds=10 + i),
                negotiation_rounds=0,
            )
        conn.commit()

    params = {
        "from": (base_time - timedelta(seconds=1)).isoformat(),
        "to": (base_time + timedelta(seconds=60)).isoformat(),
        "outcome": "booked",
        "page_size": 50,
    }
    res = await client.get(f"{API_PREFIX}/calls", params=params)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    for item in data["items"]:
        assert item["outcome"] == "booked"


# --------------------------------------------------------------------------- #
# 7. GET /calls — date range filter.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_get_calls_filter_by_date_range(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    tag = f"date-{uuid.uuid4().hex[:8]}"
    # Place two rows: one very old (outside any reasonable window) and one in a
    # narrow recent window that we'll filter to.
    very_old = datetime.now(tz=timezone.utc) - timedelta(days=30)
    recent = datetime.now(tz=timezone.utc) - timedelta(hours=4)

    with psycopg2.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        for label, ts in (("old", very_old), ("new", recent)):
            cid = f"{tag}-{label}"
            cleanup_call_ids.append(cid)
            _insert_call_log(
                cur,
                call_id=cid,
                outcome=CallOutcome.CARRIER_HUNG_UP,
                sentiment=CarrierSentiment.NEUTRAL,
                created_at=ts,
                negotiation_rounds=0,
                carrier_name=tag,
            )
        conn.commit()

    # Window catches only the "new" row.
    params = {
        "from": (recent - timedelta(seconds=1)).isoformat(),
        "to": (recent + timedelta(seconds=1)).isoformat(),
        "page_size": 50,
    }
    res = await client.get(f"{API_PREFIX}/calls", params=params)
    assert res.status_code == 200, res.text
    data = res.json()
    new_items = [item for item in data["items"] if item["call_id"].startswith(tag)]
    assert len(new_items) == 1
    assert new_items[0]["call_id"] == f"{tag}-new"


# --------------------------------------------------------------------------- #
# 8. POST /calls/log — integration coverage for every remaining CallOutcome.
#
# TRANSFERRED_TO_REP is already exercised end-to-end above. The other 6 outcomes
# only had unit-level coverage on classify_outcome. These fixtures POST the rich
# payload that the HappyRobot AI Extract node sends and assert that the route
# returns the right outcome AND persists it — locking the wire-level contract.
# --------------------------------------------------------------------------- #


async def _post_and_assert_outcome(
    client: AsyncClient,
    cleanup_call_ids: list[str],
    *,
    body_overrides: dict[str, object],
    expected_outcome: CallOutcome,
) -> None:
    call_id = f"test-{uuid.uuid4()}"
    cleanup_call_ids.append(call_id)
    body: dict[str, object] = {"call_id": call_id, **body_overrides}
    res = await client.post(f"{API_PREFIX}/calls/log", json=body)
    assert res.status_code == 200, res.text
    assert res.json()["outcome"] == expected_outcome.value

    with psycopg2.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT outcome FROM call_logs WHERE call_id = %s", (call_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == expected_outcome.value


@pytest.mark.asyncio(loop_scope="session")
async def test_post_log_classifies_booked(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    await _post_and_assert_outcome(
        client,
        cleanup_call_ids,
        body_overrides={
            "final_agreed_rate": "2500.00",
            "transferred": False,
            "negotiation_rounds": 2,
            "loadboard_rate": "2400.00",
        },
        expected_outcome=CallOutcome.BOOKED,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_post_log_classifies_carrier_failed_vetting(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    await _post_and_assert_outcome(
        client,
        cleanup_call_ids,
        body_overrides={
            "vetting_passed": False,
            "carrier_mc": "999000",
            "transcript_summary": "MC not in FMCSA records.",
        },
        expected_outcome=CallOutcome.CARRIER_FAILED_VETTING,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_post_log_classifies_no_matching_loads(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    await _post_and_assert_outcome(
        client,
        cleanup_call_ids,
        body_overrides={
            "vetting_passed": True,
            "loads_searched": True,
            "matches_returned": 0,
            "origin_requested": "Detroit, MI",
            "destination_requested": "Toledo, OH",
        },
        expected_outcome=CallOutcome.NO_MATCHING_LOADS,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_post_log_classifies_negotiation_stalled(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    await _post_and_assert_outcome(
        client,
        cleanup_call_ids,
        body_overrides={
            "vetting_passed": True,
            "loads_searched": True,
            "matches_returned": 2,
            "negotiation_rounds": 3,
            "final_agreed_rate": None,
            "loadboard_rate": "2690.00",
            "initial_carrier_ask": "2300.00",
        },
        expected_outcome=CallOutcome.NEGOTIATION_STALLED,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_post_log_classifies_carrier_hung_up(
    client: AsyncClient, cleanup_call_ids: list[str]
) -> None:
    # Minimal payload: no rate, no vetting outcome, no search, no rounds.
    # Falls through to the default branch.
    await _post_and_assert_outcome(
        client,
        cleanup_call_ids,
        body_overrides={
            "carrier_mc": "123456",
            "transcript_summary": "Carrier said hold on then dropped.",
        },
        expected_outcome=CallOutcome.CARRIER_HUNG_UP,
    )
