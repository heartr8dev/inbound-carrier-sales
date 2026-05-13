"""Aggregate dashboard metrics from the call_logs / carrier_verifications tables.

Every section is computed via SQLAlchemy 2.x ``select()`` with ``func`` / ``case``
aggregates — no Python-side iteration over rows. The aggregator is the single
source of truth for the dashboard payload; the route handler is a thin wrapper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, case, desc, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.config import settings
from api.src.models.call_log import CallLog
from api.src.models.carrier import CarrierVerification
from api.src.schemas.enums import CallOutcome, CarrierSentiment, EquipmentType
from api.src.schemas.metrics import (
    EquipmentDemand,
    FunnelSection,
    FunnelStage,
    KPIBar,
    LaneVolume,
    LoadMatchingSection,
    MetricsPeriod,
    MetricsResponse,
    NegotiationRoundBucket,
    NegotiationSection,
    RecentCallItem,
    RevenueSection,
    SentimentDistribution,
    SentimentOutcomeCell,
    SentimentSection,
    TimeseriesPoint,
    TimeseriesSection,
    VettingSection,
)


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------


def _period_window(period: MetricsPeriod, now: datetime | None = None) -> tuple[datetime | None, datetime]:
    """Return ``(start_inclusive, end_exclusive)`` for the given ``period``.

    ``start`` is ``None`` for ``"all"`` so callers know to skip the lower-bound
    filter entirely. ``end`` is always the current instant.
    """
    end = now or datetime.now(timezone.utc)
    if period == "today":
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = end - timedelta(days=7)
    elif period == "30d":
        start = end - timedelta(days=30)
    elif period == "all":
        start = None
    else:  # pragma: no cover — guarded by Literal type
        raise ValueError(f"unknown period: {period}")
    return start, end


def _period_filter(start: datetime | None, end: datetime):
    """SQLAlchemy clause filtering ``CallLog.created_at`` to the window."""
    if start is None:
        return CallLog.created_at <= end
    return and_(CallLog.created_at >= start, CallLog.created_at <= end)


# ---------------------------------------------------------------------------
# Section aggregators — each emits exactly one SQL query
# ---------------------------------------------------------------------------


_MARGIN_DENOM = float(settings.MAX_DISCOUNT_PCT)  # e.g. 0.10
_FLOOR_FACTOR = 1.0 - _MARGIN_DENOM  # e.g. 0.90


async def _kpi_and_revenue(
    session: AsyncSession,
    start: datetime | None,
    end: datetime,
    today_start: datetime,
) -> tuple[KPIBar, RevenueSection]:
    """Single query producing the KPI bar + revenue section.

    ``calls_today`` is always anchored to *today* regardless of the selected
    period (it's the "calls today" KPI). Everything else is scoped to the
    requested window.
    """
    booked = CallLog.outcome == CallOutcome.BOOKED
    has_lb = CallLog.loadboard_rate.is_not(None)
    has_final = CallLog.final_agreed_rate.is_not(None)

    # Margin saved per booked call (in $):
    #   final - floor   where floor = loadboard * (1 - MAX_DISCOUNT_PCT)
    floor_price = CallLog.loadboard_rate * _FLOOR_FACTOR
    margin_saved = CallLog.final_agreed_rate - floor_price

    # Margin preserved pct per booked call:
    #   (final - floor) / (loadboard - floor) = (final - floor) / (loadboard * MAX_DISCOUNT_PCT)
    margin_band = CallLog.loadboard_rate * _MARGIN_DENOM
    margin_preserved_pct = case(
        (margin_band > 0, margin_saved / margin_band),
        else_=None,
    )

    stmt = select(
        func.count().label("total_in_period"),
        func.coalesce(
            func.sum(
                case((CallLog.created_at >= today_start, 1), else_=0)
            ),
            0,
        ).label("calls_today"),
        func.coalesce(func.sum(case((booked, 1), else_=0)), 0).label("booked_count"),
        func.coalesce(
            func.avg(
                case(
                    (
                        and_(booked, has_lb, has_final),
                        margin_saved,
                    ),
                    else_=None,
                )
            ),
            0,
        ).label("avg_margin_saved"),
        func.coalesce(func.avg(CallLog.negotiation_rounds), 0).label("avg_rounds"),
        func.avg(case((has_lb, CallLog.loadboard_rate), else_=None)).label("avg_loadboard"),
        func.avg(case((and_(booked, has_final), CallLog.final_agreed_rate), else_=None)).label("avg_booked"),
        func.avg(case((and_(booked, has_lb, has_final), margin_preserved_pct), else_=None)).label("avg_margin_preserved"),
    ).where(_period_filter(start, end))

    row = (await session.execute(stmt)).one()

    total = int(row.total_in_period)
    booked_count = int(row.booked_count)
    booked_rate_pct = (booked_count / total * 100.0) if total else 0.0

    kpi = KPIBar(
        calls_today=int(row.calls_today),
        booked_rate_pct=round(booked_rate_pct, 2),
        avg_margin_saved_usd=Decimal(str(round(float(row.avg_margin_saved or 0), 2))),
        avg_negotiation_rounds=round(float(row.avg_rounds or 0), 2),
    )

    revenue = RevenueSection(
        avg_loadboard_rate=Decimal(str(round(float(row.avg_loadboard or 0), 2))),
        avg_booked_rate=Decimal(str(round(float(row.avg_booked or 0), 2))),
        avg_margin_preserved_pct=round(float(row.avg_margin_preserved or 0) * 100.0, 2),
    )

    return kpi, revenue


async def _funnel(session: AsyncSession, start: datetime | None, end: datetime) -> FunnelSection:
    """5-stage funnel via 5 conditional aggregates in a single query."""
    qualified_cond = CallLog.outcome != CallOutcome.CARRIER_FAILED_VETTING
    matched_cond = ~CallLog.outcome.in_(
        [CallOutcome.NO_MATCHING_LOADS, CallOutcome.CARRIER_FAILED_VETTING]
    )
    negotiated_cond = CallLog.negotiation_rounds > 0
    booked_cond = CallLog.outcome.in_([CallOutcome.BOOKED, CallOutcome.TRANSFERRED_TO_REP])

    stmt = select(
        func.count().label("total"),
        func.coalesce(func.sum(case((qualified_cond, 1), else_=0)), 0).label("qualified"),
        func.coalesce(func.sum(case((matched_cond, 1), else_=0)), 0).label("matched"),
        func.coalesce(func.sum(case((negotiated_cond, 1), else_=0)), 0).label("negotiated"),
        func.coalesce(func.sum(case((booked_cond, 1), else_=0)), 0).label("booked"),
    ).where(_period_filter(start, end))

    row = (await session.execute(stmt)).one()

    counts = [
        ("Total calls", int(row.total)),
        ("Qualified", int(row.qualified)),
        ("Matched", int(row.matched)),
        ("Negotiated", int(row.negotiated)),
        ("Booked", int(row.booked)),
    ]

    stages: list[FunnelStage] = []
    prev: int | None = None
    for name, count in counts:
        if prev is None or prev == 0:
            drop = 0.0
        else:
            drop = round((prev - count) / prev * 100.0, 2)
        stages.append(FunnelStage(name=name, count=count, drop_off_pct=drop))
        prev = count

    return FunnelSection(stages=stages)


async def _negotiation(
    session: AsyncSession, start: datetime | None, end: datetime
) -> NegotiationSection:
    """Rounds 1..3 → (agreed, walked, avg_discount_pct).

    "agreed" = ``BOOKED`` or ``TRANSFERRED_TO_REP``; "walked" = anything else
    with a non-zero round count (declined, stalled, hangup mid-negotiation).
    """
    booked = CallLog.outcome.in_([CallOutcome.BOOKED, CallOutcome.TRANSFERRED_TO_REP])
    has_lb = CallLog.loadboard_rate.is_not(None)
    has_final = CallLog.final_agreed_rate.is_not(None)
    discount_expr = case(
        (
            and_(booked, has_lb, has_final, CallLog.loadboard_rate > 0),
            (CallLog.loadboard_rate - CallLog.final_agreed_rate) / CallLog.loadboard_rate,
        ),
        else_=None,
    )

    stmt = (
        select(
            CallLog.negotiation_rounds.label("rnd"),
            func.coalesce(func.sum(case((booked, 1), else_=0)), 0).label("agreed"),
            func.coalesce(func.sum(case((~booked, 1), else_=0)), 0).label("walked"),
            func.avg(discount_expr).label("avg_discount"),
        )
        .where(
            and_(
                _period_filter(start, end),
                CallLog.negotiation_rounds.in_([1, 2, 3]),
            )
        )
        .group_by(CallLog.negotiation_rounds)
    )

    rows = (await session.execute(stmt)).all()
    by_round: dict[int, NegotiationRoundBucket] = {
        r: NegotiationRoundBucket(round=r, agreed=0, walked=0, avg_discount_pct=0.0)
        for r in (1, 2, 3)
    }
    for r in rows:
        by_round[int(r.rnd)] = NegotiationRoundBucket(
            round=int(r.rnd),
            agreed=int(r.agreed),
            walked=int(r.walked),
            avg_discount_pct=round(float(r.avg_discount or 0) * 100.0, 2),
        )

    return NegotiationSection(buckets=[by_round[r] for r in (1, 2, 3)])


async def _vetting(session: AsyncSession, start: datetime | None, end: datetime) -> VettingSection:
    """Pass/fail counts from call_logs, plus top rejection reasons from carrier_verifications.

    Two queries here because the reason text lives on ``CarrierVerification``,
    not ``CallLog`` — a single join would force a row-per-call grouping that
    distorts the counts.
    """
    failed = CallLog.outcome == CallOutcome.CARRIER_FAILED_VETTING

    counts_stmt = select(
        func.coalesce(func.sum(case((~failed, 1), else_=0)), 0).label("pass_count"),
        func.coalesce(func.sum(case((failed, 1), else_=0)), 0).label("fail_count"),
    ).where(_period_filter(start, end))
    counts_row = (await session.execute(counts_stmt)).one()

    reasons_stmt = (
        select(
            CarrierVerification.rejection_reason.label("reason"),
            func.count().label("n"),
        )
        .where(
            and_(
                CarrierVerification.is_eligible.is_(False),
                CarrierVerification.rejection_reason.is_not(None),
                # Scope by verification timestamp — best available proxy.
                _verification_period_filter(start, end),
            )
        )
        .group_by(CarrierVerification.rejection_reason)
        .order_by(desc("n"))
        .limit(10)
    )
    reasons_rows = (await session.execute(reasons_stmt)).all()
    top_failure_reasons: list[dict[str, int | str]] = [
        {"reason": r.reason, "count": int(r.n)} for r in reasons_rows
    ]

    return VettingSection(
        pass_count=int(counts_row.pass_count),
        fail_count=int(counts_row.fail_count),
        top_failure_reasons=top_failure_reasons,
    )


def _verification_period_filter(start: datetime | None, end: datetime):
    if start is None:
        return CarrierVerification.verified_at <= end
    return and_(
        CarrierVerification.verified_at >= start,
        CarrierVerification.verified_at <= end,
    )


async def _sentiment(
    session: AsyncSession, start: datetime | None, end: datetime
) -> SentimentSection:
    """One grouped query for the 2-D heatmap; the 1-D distribution is rolled up in SQL."""
    stmt = (
        select(
            CallLog.sentiment.label("sentiment"),
            CallLog.outcome.label("outcome"),
            func.count().label("n"),
        )
        .where(_period_filter(start, end))
        .group_by(CallLog.sentiment, CallLog.outcome)
    )
    rows = (await session.execute(stmt)).all()

    heatmap = [
        SentimentOutcomeCell(
            sentiment=r.sentiment,
            outcome=r.outcome,
            count=int(r.n),
        )
        for r in rows
    ]

    # Distribution: sum over outcomes per sentiment, computed in SQL.
    dist_stmt = (
        select(CallLog.sentiment.label("sentiment"), func.count().label("n"))
        .where(_period_filter(start, end))
        .group_by(CallLog.sentiment)
    )
    dist_rows = (await session.execute(dist_stmt)).all()
    by_sentiment = {s: 0 for s in CarrierSentiment}
    for r in dist_rows:
        by_sentiment[r.sentiment] = int(r.n)
    distribution = [
        SentimentDistribution(sentiment=s, count=by_sentiment[s]) for s in CarrierSentiment
    ]

    return SentimentSection(distribution=distribution, heatmap=heatmap)


async def _load_matching(
    session: AsyncSession, start: datetime | None, end: datetime
) -> LoadMatchingSection:
    """Top 10 lanes + equipment demand counts."""
    lanes_stmt = (
        select(
            CallLog.origin_requested.label("origin"),
            CallLog.destination_requested.label("destination"),
            func.count().label("n"),
        )
        .where(
            and_(
                _period_filter(start, end),
                CallLog.origin_requested.is_not(None),
                CallLog.destination_requested.is_not(None),
            )
        )
        .group_by(CallLog.origin_requested, CallLog.destination_requested)
        .order_by(desc("n"))
        .limit(10)
    )
    lane_rows = (await session.execute(lanes_stmt)).all()
    top_lanes = [
        LaneVolume(origin=r.origin, destination=r.destination, count=int(r.n))
        for r in lane_rows
    ]

    eq_stmt = (
        select(
            CallLog.equipment_type_requested.label("equipment"),
            func.count().label("n"),
        )
        .where(
            and_(
                _period_filter(start, end),
                CallLog.equipment_type_requested.is_not(None),
            )
        )
        .group_by(CallLog.equipment_type_requested)
    )
    eq_rows = (await session.execute(eq_stmt)).all()
    eq_map = {e: 0 for e in EquipmentType}
    for r in eq_rows:
        eq_map[r.equipment] = int(r.n)
    equipment_demand = [
        EquipmentDemand(equipment_type=e, count=eq_map[e]) for e in EquipmentType
    ]

    return LoadMatchingSection(top_lanes=top_lanes, equipment_demand=equipment_demand)


async def _timeseries(
    session: AsyncSession, start: datetime | None, end: datetime
) -> TimeseriesSection:
    """Hourly buckets of (total_calls, booked_calls) over the window.

    Uses Postgres ``date_trunc('hour', ...)`` so the database does the bucketing.
    """
    bucket = func.date_trunc("hour", CallLog.created_at).label("bucket")
    booked = CallLog.outcome.in_([CallOutcome.BOOKED, CallOutcome.TRANSFERRED_TO_REP])
    stmt = (
        select(
            bucket,
            func.count().label("calls"),
            func.coalesce(func.sum(case((booked, 1), else_=0)), 0).label("booked"),
        )
        .where(_period_filter(start, end))
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = (await session.execute(stmt)).all()
    points = [
        TimeseriesPoint(
            bucket_start=r.bucket,
            calls=int(r.calls),
            booked=int(r.booked),
        )
        for r in rows
    ]
    return TimeseriesSection(points=points)


async def _recent_calls(
    session: AsyncSession, start: datetime | None, end: datetime
) -> list[RecentCallItem]:
    stmt = (
        select(CallLog)
        .where(_period_filter(start, end))
        .order_by(CallLog.created_at.desc())
        .limit(25)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [RecentCallItem.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def aggregate_metrics(session: AsyncSession, period: MetricsPeriod) -> MetricsResponse:
    """Compute the full dashboard payload for ``period`` in ~9 SQL queries."""
    now = datetime.now(timezone.utc)
    start, end = _period_window(period, now=now)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    kpi, revenue = await _kpi_and_revenue(session, start, end, today_start)
    funnel = await _funnel(session, start, end)
    negotiation = await _negotiation(session, start, end)
    vetting = await _vetting(session, start, end)
    sentiment = await _sentiment(session, start, end)
    load_matching = await _load_matching(session, start, end)
    timeseries = await _timeseries(session, start, end)
    recent_calls = await _recent_calls(session, start, end)

    return MetricsResponse(
        period=period,
        generated_at=now,
        kpi=kpi,
        funnel=funnel,
        revenue=revenue,
        negotiation=negotiation,
        vetting=vetting,
        sentiment=sentiment,
        load_matching=load_matching,
        timeseries=timeseries,
        recent_calls=recent_calls,
    )


__all__ = ["aggregate_metrics"]


# ``literal_column`` is imported eagerly so static analysis doesn't drop it; it
# remains available for future ad-hoc projections (e.g. percentiles) without
# re-editing the import block.
_ = literal_column  # noqa: F841
