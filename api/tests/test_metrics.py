"""Tests for the metrics aggregator + ``GET /api/v1/metrics`` route.

Each test seeds its own rows in a tight time window with unique ``call_id``s
and cleans them up on teardown — safe to re-run against a shared Postgres.

All async fixtures use ``loop_scope="session"`` so they share the event loop
that the global ``AsyncSessionLocal`` engine first bound to (the same pattern
used by :file:`api/tests/test_load_matcher.py`). Without that, the engine's
connection pool ends up bound to a torn-down loop on the second test.

Most tests call :func:`aggregate_metrics` directly with a fresh
``AsyncSession`` rather than hitting the route via httpx. The route handler is
a one-line delegation; behavior lives in the aggregator. The end-to-end test
that runs the mock generator does call the aggregator (not httpx) for the
same reason.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete

from api.src.db import AsyncSessionLocal
from api.src.models.call_log import CallLog
from api.src.schemas.enums import CallOutcome, CarrierSentiment, EquipmentType
from api.src.services.metrics_aggregator import aggregate_metrics

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture(loop_scope="session")
async def cleanup_call_ids() -> AsyncIterator[list[str]]:
    ids: list[str] = []
    yield ids
    if ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(CallLog).where(CallLog.call_id.in_(ids)))
            await session.commit()


def _ts(*, minutes_ago: int = 0, days_ago: int = 0) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=days_ago, minutes=minutes_ago)


async def _insert(rows: list[dict[str, object]]) -> None:
    async with AsyncSessionLocal() as session:
        for r in rows:
            session.add(CallLog(**r))
        await session.commit()


# --------------------------------------------------------------------------- #
# 1. Empty slice → all metrics zeroed without errors.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_empty_slice_returns_zeroed_metrics() -> None:
    """Probe a 1-minute window 5 years in the past — guaranteed empty.

    This exercises every aggregator branch with zero rows: division-by-zero
    guards, empty group_by results, sentinel-zero defaults for absent enums.
    The window is far enough in the past that even the most aggressive
    mock-data seeders won't populate it.
    """
    from api.src.services import metrics_aggregator as agg

    far_past_end = datetime(2020, 1, 1, 0, 1, tzinfo=timezone.utc)
    far_past_start = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)

    orig_window = agg._period_window
    try:
        agg._period_window = lambda period, now=None: (far_past_start, far_past_end)  # type: ignore[assignment]
        async with AsyncSessionLocal() as session:
            result = await aggregate_metrics(session, "7d")
    finally:
        agg._period_window = orig_window

    assert result.kpi.calls_today == 0
    assert result.kpi.booked_rate_pct == 0.0
    assert result.kpi.avg_margin_saved_usd == Decimal("0.00")
    assert result.kpi.avg_negotiation_rounds == 0.0

    assert len(result.funnel.stages) == 5
    for stage in result.funnel.stages:
        assert stage.count == 0
        assert stage.drop_off_pct == 0.0

    assert result.revenue.avg_loadboard_rate == Decimal("0.00")
    assert result.revenue.avg_booked_rate == Decimal("0.00")
    assert result.revenue.avg_margin_preserved_pct == 0.0

    assert [b.round for b in result.negotiation.buckets] == [1, 2, 3]
    for b in result.negotiation.buckets:
        assert b.agreed == 0
        assert b.walked == 0

    assert result.vetting.pass_count == 0
    assert result.vetting.fail_count == 0
    assert result.vetting.top_failure_reasons == []

    assert {d.sentiment for d in result.sentiment.distribution} == set(CarrierSentiment)
    assert all(d.count == 0 for d in result.sentiment.distribution)
    assert result.sentiment.heatmap == []

    assert result.load_matching.top_lanes == []
    assert {e.equipment_type for e in result.load_matching.equipment_demand} == set(
        EquipmentType
    )
    assert all(e.count == 0 for e in result.load_matching.equipment_demand)

    assert result.timeseries.points == []
    assert result.recent_calls == []


# --------------------------------------------------------------------------- #
# 2. One booked call → funnel.booked == 1, revenue avg matches.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_one_booked_call_funnel_and_revenue(
    cleanup_call_ids: list[str],
) -> None:
    """Insert a single booked call in a tight 60-second window; narrow the
    aggregator window via monkeypatch to just that 60s slice so unrelated rows
    in the shared DB don't pollute the assertions."""
    from api.src.services import metrics_aggregator as agg

    tag = f"metrics-one-{uuid.uuid4().hex[:8]}"
    call_id = f"{tag}-booked"
    cleanup_call_ids.append(call_id)
    now = datetime.now(tz=timezone.utc)
    created_at = now - timedelta(minutes=2)

    await _insert(
        [
            {
                "call_id": call_id,
                "carrier_mc": "1234567",
                "carrier_company": "TestCo",
                "loadboard_rate": Decimal("2000.00"),
                "initial_carrier_ask": Decimal("1700.00"),
                "final_agreed_rate": Decimal("1900.00"),
                "negotiation_rounds": 2,
                "outcome": CallOutcome.BOOKED,
                "sentiment": CarrierSentiment.POSITIVE,
                "equipment_type_requested": EquipmentType.DRY_VAN,
                "origin_requested": "Dallas, TX",
                "destination_requested": "Atlanta, GA",
                "created_at": created_at,
            }
        ]
    )

    window_start = created_at - timedelta(seconds=30)
    window_end = created_at + timedelta(seconds=30)
    orig_window = agg._period_window
    try:
        agg._period_window = lambda period, now=None: (window_start, window_end)  # type: ignore[assignment]
        async with AsyncSessionLocal() as session:
            result = await aggregate_metrics(session, "7d")
    finally:
        agg._period_window = orig_window

    counts = {s.name: s.count for s in result.funnel.stages}
    assert counts["Total calls"] == 1
    assert counts["Qualified"] == 1
    assert counts["Matched"] == 1
    assert counts["Negotiated"] == 1
    assert counts["Booked"] == 1

    # Revenue: avg_loadboard=2000, avg_booked=1900.
    assert result.revenue.avg_loadboard_rate == Decimal("2000.00")
    assert result.revenue.avg_booked_rate == Decimal("1900.00")
    # Margin preserved pct: (1900 - 1800) / (2000 - 1800) = 100/200 = 50%.
    assert result.revenue.avg_margin_preserved_pct == pytest.approx(50.0, abs=0.01)

    # KPI: avg margin saved = 1900 - 1800 = 100.
    assert result.kpi.avg_margin_saved_usd == Decimal("100.00")
    assert result.kpi.booked_rate_pct == 100.0
    assert result.kpi.avg_negotiation_rounds == 2.0


# --------------------------------------------------------------------------- #
# 3. Period filtering — old rows excluded from "today".
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_period_today_excludes_old_rows(cleanup_call_ids: list[str]) -> None:
    """Insert one old row (2 days ago) and one fresh row (1 minute ago); the
    real period='today' boundary should exclude the old row from recent_calls.
    """
    tag = f"metrics-period-{uuid.uuid4().hex[:8]}"
    old_id = f"{tag}-old"
    new_id = f"{tag}-new"
    cleanup_call_ids.extend([old_id, new_id])

    await _insert(
        [
            {
                "call_id": old_id,
                "outcome": CallOutcome.BOOKED,
                "sentiment": CarrierSentiment.POSITIVE,
                "negotiation_rounds": 1,
                "loadboard_rate": Decimal("1000"),
                "final_agreed_rate": Decimal("980"),
                "created_at": _ts(days_ago=2),
            },
            {
                "call_id": new_id,
                "outcome": CallOutcome.BOOKED,
                "sentiment": CarrierSentiment.POSITIVE,
                "negotiation_rounds": 1,
                "loadboard_rate": Decimal("1000"),
                "final_agreed_rate": Decimal("980"),
                "created_at": _ts(minutes_ago=1),
            },
        ]
    )

    async with AsyncSessionLocal() as session:
        result_today = await aggregate_metrics(session, "today")
        result_7d = await aggregate_metrics(session, "7d")

    today_ids = {c.call_id for c in result_today.recent_calls}
    sevend_ids = {c.call_id for c in result_7d.recent_calls}

    assert new_id in today_ids, "fresh row must be present in 'today' window"
    assert old_id not in today_ids, "2-day-old row must NOT be in 'today' window"
    # The fresh row is also in the 7d window. The 2-day-old row would also be
    # present unless something else flushed it past the 25-row cap — we only
    # assert about *today*'s exclusion here to avoid coupling to DB noise.
    assert new_id in sevend_ids


# --------------------------------------------------------------------------- #
# 4. Outcome-by-round counts correctly.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_outcome_by_round_counts(cleanup_call_ids: list[str]) -> None:
    """Known mix:
        - 2 booked  @ round 1
        - 1 booked  @ round 3
        - 1 declined @ round 2
        - 1 stalled @ round 3
    Buckets must reflect agreed/walked counts per round.
    """
    from api.src.services import metrics_aggregator as agg

    tag = f"metrics-rnd-{uuid.uuid4().hex[:8]}"
    now = datetime.now(tz=timezone.utc)
    base_time = now - timedelta(minutes=5)
    window_start = base_time - timedelta(seconds=30)
    window_end = base_time + timedelta(minutes=10)

    rows = []
    for i in range(2):
        cid = f"{tag}-b1-{i}"
        cleanup_call_ids.append(cid)
        rows.append(
            {
                "call_id": cid,
                "outcome": CallOutcome.BOOKED,
                "sentiment": CarrierSentiment.POSITIVE,
                "negotiation_rounds": 1,
                "loadboard_rate": Decimal("1000"),
                "final_agreed_rate": Decimal("970"),
                "created_at": base_time + timedelta(seconds=i),
            }
        )
    cid = f"{tag}-b3-0"
    cleanup_call_ids.append(cid)
    rows.append(
        {
            "call_id": cid,
            "outcome": CallOutcome.BOOKED,
            "sentiment": CarrierSentiment.NEUTRAL,
            "negotiation_rounds": 3,
            "loadboard_rate": Decimal("1000"),
            "final_agreed_rate": Decimal("920"),
            "created_at": base_time + timedelta(seconds=10),
        }
    )
    cid = f"{tag}-d2-0"
    cleanup_call_ids.append(cid)
    rows.append(
        {
            "call_id": cid,
            "outcome": CallOutcome.CARRIER_DECLINED_RATE,
            "sentiment": CarrierSentiment.FRUSTRATED,
            "negotiation_rounds": 2,
            "loadboard_rate": Decimal("1000"),
            "created_at": base_time + timedelta(seconds=20),
        }
    )
    cid = f"{tag}-s3-0"
    cleanup_call_ids.append(cid)
    rows.append(
        {
            "call_id": cid,
            "outcome": CallOutcome.NEGOTIATION_STALLED,
            "sentiment": CarrierSentiment.HOSTILE,
            "negotiation_rounds": 3,
            "loadboard_rate": Decimal("1000"),
            "created_at": base_time + timedelta(seconds=30),
        }
    )
    await _insert(rows)

    orig_window = agg._period_window
    try:
        agg._period_window = lambda period, now=None: (window_start, window_end)  # type: ignore[assignment]
        async with AsyncSessionLocal() as session:
            result = await aggregate_metrics(session, "7d")
    finally:
        agg._period_window = orig_window

    by_round = {b.round: b for b in result.negotiation.buckets}
    assert by_round[1].agreed == 2
    assert by_round[1].walked == 0
    assert by_round[2].agreed == 0
    assert by_round[2].walked == 1
    assert by_round[3].agreed == 1
    assert by_round[3].walked == 1


# --------------------------------------------------------------------------- #
# 5. End-to-end: mock generator → aggregator returns plausible numbers.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_aggregator_returns_plausible_numbers_with_mock_data() -> None:
    """Run the mock-call generator (--reset, count=80, --seed 42) out-of-
    process, then call the aggregator. We assert:
      - funnel total == 80
      - booked count > 0
      - sentiment distribution sums to 80
      - recent_calls capped at 25
      - kpi values are in their natural ranges
    """
    script = REPO_ROOT / "scripts" / "generate_mock_calls.py"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        "--reset",
        "--count",
        "80",
        "--seed",
        "42",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    stdout_b, stderr_b = await proc.communicate()
    assert proc.returncode == 0, f"generator failed: {stderr_b.decode()}"
    assert b"call_logs inserted: 80" in stdout_b

    try:
        async with AsyncSessionLocal() as session:
            result = await aggregate_metrics(session, "7d")

        funnel = {s.name: s.count for s in result.funnel.stages}
        assert funnel["Total calls"] == 80

        assert funnel["Booked"] > 0, (
            "with 80 calls at 35% booked weight, we expect some bookings"
        )

        dist_sum = sum(d.count for d in result.sentiment.distribution)
        assert dist_sum == 80

        assert len(result.recent_calls) == 25

        assert 0.0 <= result.kpi.booked_rate_pct <= 100.0
        assert result.kpi.avg_negotiation_rounds >= 0.0
    finally:
        # Clean up so subsequent dev/test work isn't affected.
        async with AsyncSessionLocal() as session:
            await session.execute(delete(CallLog).where(CallLog.call_id.like("mock-%")))
            await session.commit()
