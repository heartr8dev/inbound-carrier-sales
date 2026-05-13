"""Top-3 load matcher used by :mod:`api.src.routes.loads`.

Strategy
--------
1. Hard filters in SQL: ``equipment_type`` exact match, ``is_available = true``,
   pickup window of +/- 2 days around ``criteria.pickup_date`` (when supplied).
2. Pull the small candidate set into Python (the table is ~45 rows in this
   prototype) and score each row against the carrier's normalised origin /
   destination using :mod:`api.src.services.city_aliases`.
3. Sort by ``(score desc, rate_per_mile desc)`` and take the top N.
4. If we end up with fewer than ``criteria.max_results`` (default 3) matches,
   run an origin-only fallback (drop the destination from scoring, ignore
   destination state) and tag each fallback result ``partial_match=True``.

Per-side scoring (spec):

* Exact city + state match: 100
* City matches, state differs:  70
* Same state (no city):         50
* Neighboring states:           30
* Otherwise:                     0

A load has two sides — origin and destination — so the final composite is the
average of the two side scores (rounded). When the request omits a side, that
side defaults to 100 so it doesn't drag the average down.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.load import Load
from api.src.schemas.load import LoadMatch, LoadSearchRequest, LoadSearchResponse
from api.src.services.city_aliases import (
    CanonicalLocation,
    normalize_location,
    states_are_adjacent,
)

# Side-score buckets. Composite = round((origin + destination) / 2).
SCORE_EXACT = 100
SCORE_CITY_MATCH_DIFFERENT_STATE = 70
SCORE_SAME_STATE = 50
SCORE_NEIGHBORING_STATE = 30
SCORE_NO_MATCH = 0

PICKUP_WINDOW_DAYS = 2


def _score_side(query: CanonicalLocation, load_loc: CanonicalLocation) -> int:
    """Score a single origin or destination pair against the spec rubric."""
    # No constraint supplied — neutral max so it doesn't lower the composite.
    if query.city is None and query.state is None:
        return SCORE_EXACT

    q_city = query.city.lower() if query.city else None
    q_state = query.state.upper() if query.state else None
    l_city = load_loc.city.lower() if load_loc.city else None
    l_state = load_loc.state.upper() if load_loc.state else None

    # Exact city + state — only meaningful when the carrier gave us a city.
    if q_city and l_city and q_city == l_city and q_state == l_state:
        return SCORE_EXACT

    # City matches but states differ (or carrier omitted state).
    if q_city and l_city and q_city == l_city:
        return SCORE_CITY_MATCH_DIFFERENT_STATE

    # Same state (carrier may have given only a state, or a different city).
    if q_state and l_state and q_state == l_state:
        return SCORE_SAME_STATE

    # Neighboring state (per the hand-coded adjacency map).
    if states_are_adjacent(q_state, l_state):
        return SCORE_NEIGHBORING_STATE

    return SCORE_NO_MATCH


def _composite_score(
    q_origin: CanonicalLocation,
    q_destination: CanonicalLocation,
    load: Load,
    *,
    origin_only: bool = False,
) -> int | None:
    """Combine origin and destination side scores into one 0-100 composite.

    Returns ``None`` to mean "this load doesn't belong in this ranking pass at
    all" — used by the primary path to reject loads where either side scored
    zero (so a Dallas->Houston load doesn't sneak into a Dallas->Atlanta
    search just because the origin half matched). The fallback path with
    ``origin_only=True`` ignores the destination side entirely.
    """
    load_origin = normalize_location(load.origin)
    origin_score = _score_side(q_origin, load_origin)

    if origin_only:
        # Fallback path — destination is intentionally not considered. An
        # origin score of 0 means the load isn't in the carrier's lane at all.
        if origin_score <= 0:
            return None
        return origin_score

    load_destination = normalize_location(load.destination)
    destination_score = _score_side(q_destination, load_destination)

    # Primary path requires *both* sides to have at least some signal. If
    # the carrier supplied that side as a constraint and the load doesn't
    # match it, fall through to the fallback rather than awarding a half-score.
    if q_origin.city or q_origin.state:
        if origin_score <= 0:
            return None
    if q_destination.city or q_destination.state:
        if destination_score <= 0:
            return None

    return round((origin_score + destination_score) / 2)


def _rate_per_mile(load: Load) -> Decimal:
    """Loadboard rate divided by miles, guarded against zero-mile rows."""
    if load.miles and load.miles > 0:
        return (load.loadboard_rate / Decimal(load.miles)).quantize(Decimal("0.01"))
    return Decimal("0.00")


def _to_load_match(load: Load, score: int, *, partial: bool) -> LoadMatch:
    rate_per_mile = _rate_per_mile(load)
    return LoadMatch(
        load_id=load.load_id,
        origin=load.origin,
        destination=load.destination,
        pickup_datetime=load.pickup_datetime,
        delivery_datetime=load.delivery_datetime,
        equipment_type=load.equipment_type,
        loadboard_rate=load.loadboard_rate,
        notes=load.notes,
        weight=load.weight,
        commodity_type=load.commodity_type,
        num_of_pieces=load.num_of_pieces,
        miles=load.miles,
        dimensions=load.dimensions,
        score=score,
        rate_per_mile=rate_per_mile,
        match_score=score,
        partial_match=partial,
    )


async def _fetch_candidates(
    session: AsyncSession,
    criteria: LoadSearchRequest,
) -> list[Load]:
    """Apply hard filters in SQL and return the (small) candidate set."""
    stmt = select(Load).where(Load.is_available.is_(True))

    if criteria.equipment_type is not None:
        stmt = stmt.where(Load.equipment_type == criteria.equipment_type)

    if criteria.pickup_date is not None:
        lower = criteria.pickup_date - timedelta(days=PICKUP_WINDOW_DAYS)
        upper = criteria.pickup_date + timedelta(days=PICKUP_WINDOW_DAYS)
        stmt = stmt.where(Load.pickup_datetime >= lower, Load.pickup_datetime <= upper)

    result = await session.execute(stmt)
    return list(result.scalars().all())


def _rank(
    candidates: list[Load],
    q_origin: CanonicalLocation,
    q_destination: CanonicalLocation,
    *,
    limit: int,
    origin_only: bool = False,
) -> list[tuple[Load, int]]:
    """Score, filter out ``None`` scores, sort, and truncate."""
    scored: list[tuple[Load, int]] = []
    for load in candidates:
        score = _composite_score(q_origin, q_destination, load, origin_only=origin_only)
        if score is None:
            continue
        scored.append((load, score))

    # Tiebreak: higher rate_per_mile wins on equal score.
    scored.sort(key=lambda pair: (pair[1], _rate_per_mile(pair[0])), reverse=True)
    return scored[:limit]


async def match_loads(
    session: AsyncSession,
    criteria: LoadSearchRequest,
) -> LoadSearchResponse:
    """Return the top ``criteria.max_results`` loads matching the carrier's pitch.

    See module docstring for the full algorithm. Returns an empty response
    (200, not 404) when no candidates exist — callers should still get a
    well-formed payload so the agent can say "nothing in your lane" cleanly.
    """
    limit = criteria.max_results

    q_origin = normalize_location(criteria.origin)
    q_destination = normalize_location(criteria.destination)

    candidates = await _fetch_candidates(session, criteria)

    primary = _rank(candidates, q_origin, q_destination, limit=limit)

    matches: list[LoadMatch] = [
        _to_load_match(load, score, partial=False) for load, score in primary
    ]

    partial_used = False
    if len(matches) < limit:
        # Origin-only fallback: score by origin alone, drop destination from
        # the composite so a non-matching destination doesn't get a free 50.
        fallback = _rank(
            candidates,
            q_origin,
            CanonicalLocation(city=None, state=None),
            limit=limit,
            origin_only=True,
        )
        seen_load_ids = {m.load_id for m in matches}
        for load, score in fallback:
            if len(matches) >= limit:
                break
            if load.load_id in seen_load_ids:
                continue
            matches.append(_to_load_match(load, score, partial=True))
            partial_used = True

    logger.bind(
        equipment_type=criteria.equipment_type.value
        if criteria.equipment_type
        else None,
        origin=criteria.origin,
        destination=criteria.destination,
        pickup_date=criteria.pickup_date.isoformat() if criteria.pickup_date else None,
        candidate_count=len(candidates),
        match_count=len(matches),
        partial=partial_used,
    ).info("load_match")

    return LoadSearchResponse(
        matches=matches,
        total_found=len(matches),
        partial=partial_used,
    )
