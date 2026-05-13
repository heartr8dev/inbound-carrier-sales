"""Behavioural tests for :func:`api.src.services.load_matcher.match_loads`.

Each test inserts a small, deterministic set of loads with a unique ``test-``
prefix on ``load_id`` so the suite is safe to re-run against the shared
Postgres seeded with developer data. A session-scoped cleanup fixture wipes
every row whose ``load_id`` starts with the test prefix at the end of the run.

This mirrors the isolation pattern already used in :file:`api/tests/test_calls.py`.

The matcher itself is exercised end-to-end (no mocks) — it runs real
SQLAlchemy queries against Postgres using the same enum types and indexes as
production.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete

from api.src.db import AsyncSessionLocal
from api.src.models.load import Load
from api.src.schemas.enums import EquipmentType
from api.src.schemas.load import LoadSearchRequest
from api.src.services.load_matcher import match_loads


# Every load_id used by this test module is prefixed so we can clean up at the
# end without disturbing the developer seed (which uses ``LD-NNN``).
TEST_PREFIX = "test-lm-"

BASE_PICKUP = datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture(loop_scope="session")
async def inserted_load_ids() -> AsyncIterator[list[str]]:
    """Collect inserted ``load_id``s and delete them on teardown."""
    ids: list[str] = []
    yield ids
    if ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Load).where(Load.load_id.in_(ids)))
            await session.commit()


def _tid(suffix: str) -> str:
    """Return a unique load_id with the module prefix to keep tests isolated."""
    return f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}-{suffix}"


def _make_load(
    *,
    load_id: str,
    origin: str,
    destination: str,
    equipment_type: EquipmentType = EquipmentType.DRY_VAN,
    pickup: datetime | None = None,
    rate: float = 1000.0,
    miles: int = 500,
    is_available: bool = True,
) -> Load:
    pickup_dt = pickup or BASE_PICKUP
    return Load(
        id=uuid.uuid4(),
        load_id=load_id,
        origin=origin,
        destination=destination,
        pickup_datetime=pickup_dt,
        delivery_datetime=pickup_dt + timedelta(days=1),
        equipment_type=equipment_type,
        loadboard_rate=Decimal(str(rate)),
        notes=None,
        weight=40_000,
        commodity_type="Test Goods",
        num_of_pieces=10,
        miles=miles,
        dimensions="53L x 102W x 110H",
        is_available=is_available,
    )


async def _insert(loads: list[Load], registry: list[str]) -> None:
    """Persist the loads and register their ids for teardown cleanup."""
    async with AsyncSessionLocal() as session:
        for load in loads:
            session.add(load)
            registry.append(load.load_id)
        await session.commit()


def _matcher_request(
    *,
    origin: str | None = None,
    destination: str | None = None,
    equipment_type: EquipmentType | None = EquipmentType.DRY_VAN,
    pickup_date: datetime | None = None,
    max_results: int = 3,
) -> LoadSearchRequest:
    return LoadSearchRequest(
        origin=origin,
        destination=destination,
        equipment_type=equipment_type,
        pickup_date=pickup_date or BASE_PICKUP,
        max_results=max_results,
    )


def _filter_to_test_rows(matches: list, prefix: str) -> list:
    """Return only matches inserted by this test (drops any developer-seeded rows)."""
    return [m for m in matches if m.load_id.startswith(prefix)]


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_match_returns_ranked_top_three(
    inserted_load_ids: list[str],
) -> None:
    """Exact-lane requests should produce up to 3 matches ranked by score then rate/mile.

    Uses a fictional state ("ZZ") so the developer seed (real US lanes) can't
    appear in the candidate set and steal a slot.
    """
    suite_prefix = f"{TEST_PREFIX}{uuid.uuid4().hex[:6]}-"
    pickup_anchor = datetime(2027, 4, 1, 8, 0, tzinfo=timezone.utc)

    # Fictional cities + state so no real seed row can match.
    # B is the third exact-exact match (same origin AND same destination).
    # F has matching origin only — exists to prove it doesn't sneak past D/A/B
    # when there are already three exact matches on the primary path.
    loads = [
        _make_load(
            load_id=f"{suite_prefix}A",
            origin="Alphaville, ZZ",
            destination="Betaberg, ZZ",
            rate=1000.0,
            miles=500,
            pickup=pickup_anchor,
        ),
        _make_load(
            load_id=f"{suite_prefix}B",
            origin="Alphaville, ZZ",
            destination="Betaberg, ZZ",
            rate=500.0,
            miles=500,
            pickup=pickup_anchor,
        ),
        _make_load(
            load_id=f"{suite_prefix}D",
            origin="Alphaville, ZZ",
            destination="Betaberg, ZZ",
            rate=2500.0,
            miles=500,
            pickup=pickup_anchor,
        ),
        _make_load(
            load_id=f"{suite_prefix}F",
            origin="Alphaville, ZZ",
            destination="Otherville, YY",  # destination doesn't match the query
            rate=2000.0,
            miles=500,
            pickup=pickup_anchor,
        ),
    ]
    await _insert(loads, inserted_load_ids)

    async with AsyncSessionLocal() as session:
        response = await match_loads(
            session,
            _matcher_request(
                origin="Alphaville, ZZ",
                destination="Betaberg, ZZ",
                pickup_date=pickup_anchor,
                max_results=3,
            ),
        )

    matches = _filter_to_test_rows(response.matches, suite_prefix)
    assert len(matches) == 3
    # All three slots are filled by exact-exact matches on the primary path,
    # ordered by rate_per_mile descending: D (5.0), A (2.0), B (1.0).
    assert matches[0].load_id == f"{suite_prefix}D"
    assert matches[0].match_score == 100
    assert matches[1].load_id == f"{suite_prefix}A"
    assert matches[1].match_score == 100
    assert matches[2].load_id == f"{suite_prefix}B"
    assert matches[2].match_score == 100
    # F (origin-only match) must not appear — primary path was satisfied.
    assert f"{suite_prefix}F" not in {m.load_id for m in matches}
    # None of the test rows should be tagged partial on the primary path.
    assert all(m.partial_match is False for m in matches)


@pytest.mark.asyncio(loop_scope="session")
async def test_city_alias_dfw_matches_dallas(inserted_load_ids: list[str]) -> None:
    """The alias table should let "DFW" find loads stored as "Dallas, TX"."""
    suite_prefix = f"{TEST_PREFIX}{uuid.uuid4().hex[:6]}-"

    loads = [
        _make_load(
            load_id=f"{suite_prefix}DAL", origin="Dallas, TX", destination="Atlanta, GA"
        ),
        _make_load(
            load_id=f"{suite_prefix}HOU",
            origin="Houston, TX",
            destination="Atlanta, GA",
        ),
    ]
    await _insert(loads, inserted_load_ids)

    async with AsyncSessionLocal() as session:
        response = await match_loads(
            session,
            _matcher_request(origin="DFW", destination="ATL"),
        )

    matches = _filter_to_test_rows(response.matches, suite_prefix)
    by_id = {m.load_id: m for m in matches}
    assert f"{suite_prefix}DAL" in by_id
    dal = by_id[f"{suite_prefix}DAL"]
    assert dal.match_score == 100  # exact alias hit on both origin and destination
    assert dal.partial_match is False


@pytest.mark.asyncio(loop_scope="session")
async def test_equipment_mismatch_returns_zero_matches(
    inserted_load_ids: list[str],
) -> None:
    """Equipment type is a hard filter — when no candidates exist we report 0 matches and partial=False."""
    suite_prefix = f"{TEST_PREFIX}{uuid.uuid4().hex[:6]}-"

    # Insert only dry van + flatbed; query for reefer.
    loads = [
        _make_load(
            load_id=f"{suite_prefix}DV",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            equipment_type=EquipmentType.DRY_VAN,
            # Push pickup far outside the developer seed window so we don't
            # accidentally match a seeded reefer load on origin/destination.
            pickup=datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc),
        ),
        _make_load(
            load_id=f"{suite_prefix}FB",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            equipment_type=EquipmentType.FLATBED,
            pickup=datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc),
        ),
    ]
    await _insert(loads, inserted_load_ids)

    async with AsyncSessionLocal() as session:
        response = await match_loads(
            session,
            _matcher_request(
                origin="Mars City, ZZ",
                destination="Pluto Town, ZZ",
                equipment_type=EquipmentType.REEFER,
                # Pickup far from any seeded reefer load so the +/- 2 day window
                # excludes them too.
                pickup_date=datetime(2030, 6, 15, 8, 0, tzinfo=timezone.utc),
            ),
        )

    # No candidates pass the pickup window AND the equipment filter, so no
    # matches at all — primary or fallback — should come back.
    assert response.matches == []
    assert response.total_found == 0
    assert response.partial is False


@pytest.mark.asyncio(loop_scope="session")
async def test_origin_only_fallback_marks_partial(inserted_load_ids: list[str]) -> None:
    """When destination doesn't match anything, fall back to origin-only and tag results partial.

    Uses fictional states ("ZZ"/"YY") for both query destination and load
    destinations so the primary-path destination score is 0 for every fixture
    row, forcing the fallback codepath to kick in.
    """
    suite_prefix = f"{TEST_PREFIX}{uuid.uuid4().hex[:6]}-"
    pickup_anchor = datetime(2027, 2, 1, 8, 0, tzinfo=timezone.utc)

    fictional_origin = "Zzyzx Springs, ZZ"
    # All destinations are fictional cities in a fictional state, so the
    # primary-path destination score is always 0 (no state match, no
    # adjacency) regardless of what the carrier asks for.
    loads = [
        _make_load(
            load_id=f"{suite_prefix}OK1",
            origin=fictional_origin,
            destination="Faraway One, YY",
            pickup=pickup_anchor,
        ),
        _make_load(
            load_id=f"{suite_prefix}OK2",
            origin=fictional_origin,
            destination="Faraway Two, YY",
            pickup=pickup_anchor,
        ),
        # Origin doesn't match the carrier's origin — should never appear,
        # not even via fallback.
        _make_load(
            load_id=f"{suite_prefix}NOPE",
            origin="Quux Harbor, ZZ",
            destination="Faraway Three, YY",
            pickup=pickup_anchor,
        ),
    ]
    await _insert(loads, inserted_load_ids)

    async with AsyncSessionLocal() as session:
        response = await match_loads(
            session,
            _matcher_request(
                origin=fictional_origin,
                # Carrier wants this destination, but nothing in our fixture
                # set has anything resembling it — and the developer seed is
                # filtered out by the pickup window (Feb 2027).
                destination="Nonexistent City, XX",
                pickup_date=pickup_anchor,
            ),
        )

    matches = _filter_to_test_rows(response.matches, suite_prefix)
    returned_ids = {m.load_id for m in matches}

    # Both same-origin loads come back via the origin-only fallback.
    assert {f"{suite_prefix}OK1", f"{suite_prefix}OK2"} <= returned_ids
    assert f"{suite_prefix}NOPE" not in returned_ids
    # Those fallback matches must be flagged partial.
    for m in matches:
        if m.load_id in {f"{suite_prefix}OK1", f"{suite_prefix}OK2"}:
            assert m.partial_match is True
    assert response.partial is True


@pytest.mark.asyncio(loop_scope="session")
async def test_pickup_date_outside_window_excluded(
    inserted_load_ids: list[str],
) -> None:
    """Loads picking up more than +/- 2 days from the requested date must be filtered out."""
    suite_prefix = f"{TEST_PREFIX}{uuid.uuid4().hex[:6]}-"

    # Park all fixtures in 2029 so the developer seed (May 2026) can't pollute.
    pickup_anchor = datetime(2029, 7, 10, 8, 0, tzinfo=timezone.utc)

    loads = [
        _make_load(
            load_id=f"{suite_prefix}IN",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            pickup=pickup_anchor,
        ),
        _make_load(
            load_id=f"{suite_prefix}EDGE",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            pickup=pickup_anchor + timedelta(days=2),
        ),
        _make_load(
            load_id=f"{suite_prefix}LATE",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            pickup=pickup_anchor + timedelta(days=3),
        ),
        _make_load(
            load_id=f"{suite_prefix}EARLY",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            pickup=pickup_anchor - timedelta(days=3),
        ),
    ]
    await _insert(loads, inserted_load_ids)

    async with AsyncSessionLocal() as session:
        response = await match_loads(
            session,
            _matcher_request(
                origin="Dallas, TX",
                destination="Atlanta, GA",
                pickup_date=pickup_anchor,
                max_results=10,
            ),
        )

    matches = _filter_to_test_rows(response.matches, suite_prefix)
    returned_ids = {m.load_id for m in matches}
    assert returned_ids == {f"{suite_prefix}IN", f"{suite_prefix}EDGE"}


@pytest.mark.asyncio(loop_scope="session")
async def test_tiebreak_by_rate_per_mile(inserted_load_ids: list[str]) -> None:
    """Two loads with equal match score should rank by ``rate_per_mile`` descending."""
    suite_prefix = f"{TEST_PREFIX}{uuid.uuid4().hex[:6]}-"

    # 2028 pickups keep these clear of the developer seed.
    pickup_anchor = datetime(2028, 3, 15, 8, 0, tzinfo=timezone.utc)
    loads = [
        _make_load(
            load_id=f"{suite_prefix}LOW",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            rate=1000.0,
            miles=1000,
            pickup=pickup_anchor,
        ),  # rpm 1.00
        _make_load(
            load_id=f"{suite_prefix}HIGH",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            rate=3000.0,
            miles=1000,
            pickup=pickup_anchor,
        ),  # rpm 3.00
        _make_load(
            load_id=f"{suite_prefix}MID",
            origin="Dallas, TX",
            destination="Atlanta, GA",
            rate=2000.0,
            miles=1000,
            pickup=pickup_anchor,
        ),  # rpm 2.00
    ]
    await _insert(loads, inserted_load_ids)

    async with AsyncSessionLocal() as session:
        response = await match_loads(
            session,
            _matcher_request(
                origin="Dallas, TX",
                destination="Atlanta, GA",
                pickup_date=pickup_anchor,
                max_results=3,
            ),
        )

    matches = _filter_to_test_rows(response.matches, suite_prefix)
    ordered_ids = [m.load_id for m in matches]
    assert ordered_ids == [
        f"{suite_prefix}HIGH",
        f"{suite_prefix}MID",
        f"{suite_prefix}LOW",
    ]
    # Sanity check on the rate_per_mile values.
    rpms = [m.rate_per_mile for m in matches]
    assert rpms == sorted(rpms, reverse=True)
