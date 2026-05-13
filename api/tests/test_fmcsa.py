"""Tests for the FMCSA service (Workstream A).

Exercises ``api.src.services.fmcsa`` and the ``POST /api/v1/carrier/verify``
route against the real Postgres (same pattern as ``test_calls.py``) with
``respx`` patching the FMCSA HTTP calls. Each test uses a unique MC prefix
and cleans up its rows on teardown.

Real FMCSA payload field names are pinned from
``docs/fmcsa_response_schema.md`` — see the ``_carrier_payload`` helper.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from api.src.config import settings
from api.src.db import AsyncSessionLocal
from api.src.main import app
from api.src.models.carrier import CarrierVerification
from api.src.services.fmcsa import (
    FMCSAClient,
    FMCSANotFound,
    FMCSAUnavailable,
    _CircuitBreaker,
    evaluate_eligibility,
    get_circuit_breaker,
)

API_PREFIX = "/api/v1"
FMCSA_HOST = "https://mobile.fmcsa.dot.gov"
FMCSA_PATH = "/qc/services/carriers/docket-number"

# All MCs used by this test module live in the 99_000_000+ range so they cannot
# collide with real-world docket numbers or with rows other tests might insert.
TEST_MC_BASE = 99_000_000


def _next_mc(counter: list[int]) -> str:
    counter[0] += 1
    return str(TEST_MC_BASE + counter[0])


def _carrier_payload(
    *,
    legal_name: str = "TEST CARRIER INC",
    dba_name: str | None = None,
    allowed: str = "Y",
    status_code: str = "A",
    safety_rating: str | None = "S",
    oos_date: str | None = None,
    common_authority: str = "A",
    bipd_on_file: str = "1000",
    cargo_on_file: str = "0",
    operation_desc: str = "Interstate",
    dot_number: int = 100001,
) -> dict[str, Any]:
    """Build a FMCSA envelope identical in shape to the real
    ``/qc/services/carriers/docket-number`` response (see
    ``docs/fmcsa_response_schema.md``).
    """
    return {
        "content": [
            {
                "_links": {
                    "self": {"href": f"{FMCSA_HOST}/qc/services/carriers/{dot_number}"}
                },
                "carrier": {
                    "allowedToOperate": allowed,
                    "bipdInsuranceOnFile": bipd_on_file,
                    "bipdInsuranceRequired": "Y",
                    "bipdRequiredAmount": "750",
                    "bondInsuranceOnFile": "0",
                    "bondInsuranceRequired": "u",
                    "brokerAuthorityStatus": "N",
                    "cargoInsuranceOnFile": cargo_on_file,
                    "cargoInsuranceRequired": "u",
                    "carrierOperation": {
                        "carrierOperationCode": "A",
                        "carrierOperationDesc": operation_desc,
                    },
                    "censusTypeId": {
                        "censusType": "C",
                        "censusTypeDesc": "CARRIER",
                        "censusTypeId": 1,
                    },
                    "commonAuthorityStatus": common_authority,
                    "contractAuthorityStatus": "A",
                    "crashTotal": 0,
                    "dbaName": dba_name,
                    "dotNumber": dot_number,
                    "ein": 391474414,
                    "isPassengerCarrier": "N",
                    "issScore": None,
                    "legalName": legal_name,
                    "mcs150Outdated": "N",
                    "oosDate": oos_date,
                    "phyCity": "MARINETTE",
                    "phyCountry": "US",
                    "phyState": "WI",
                    "phyStreet": "2830 CLEVELAND AVE",
                    "phyZipcode": "54143",
                    "reviewDate": "1996-04-22",
                    "reviewType": "C",
                    "safetyRating": safety_rating,
                    "safetyRatingDate": "1996-04-25" if safety_rating else None,
                    "safetyReviewDate": "1996-04-22",
                    "safetyReviewType": "C",
                    "snapshotDate": None,
                    "statusCode": status_code,
                    "totalDrivers": 213,
                    "totalPowerUnits": 213,
                },
            }
        ],
        "retrievalDate": "2026-05-13T02:00:00.000+0000",
    }


def _empty_payload() -> dict[str, Any]:
    return {"content": [], "retrievalDate": "2026-05-13T02:00:00.000+0000"}


# --------------------------------------------------------------------------- #
# Fixtures
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


@pytest_asyncio.fixture(loop_scope="session")
async def cleanup_mcs() -> AsyncIterator[list[str]]:
    """Collects MCs created by a test and deletes the rows on teardown."""
    ids: list[str] = []
    yield ids
    if ids:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(CarrierVerification).where(
                    CarrierVerification.mc_number.in_(ids)
                )
            )
            await session.commit()


@pytest.fixture
def mc_counter() -> list[int]:
    """Per-test counter so each test gets fresh unique MCs."""
    return [0]


@pytest.fixture(autouse=True)
def reset_circuit() -> None:
    """Reset the module-level circuit breaker before every test."""
    get_circuit_breaker().reset()


# --------------------------------------------------------------------------- #
# 1. evaluate_eligibility — pure-function policy tests
# --------------------------------------------------------------------------- #


def test_evaluate_authorized_satisfactory_passes() -> None:
    carrier = _carrier_payload()["content"][0]["carrier"]
    eligible, reason = evaluate_eligibility(carrier)
    assert eligible is True
    assert reason is None


def test_evaluate_not_allowed_to_operate_rejects() -> None:
    carrier = _carrier_payload(allowed="N")["content"][0]["carrier"]
    eligible, reason = evaluate_eligibility(carrier)
    assert eligible is False
    assert reason == "not_allowed_to_operate"


def test_evaluate_inactive_status_rejects() -> None:
    carrier = _carrier_payload(status_code="I")["content"][0]["carrier"]
    eligible, reason = evaluate_eligibility(carrier)
    assert eligible is False
    assert reason == "inactive_or_not_authorized"


def test_evaluate_unsatisfactory_rejects() -> None:
    carrier = _carrier_payload(safety_rating="U")["content"][0]["carrier"]
    eligible, reason = evaluate_eligibility(carrier)
    assert eligible is False
    assert reason == "unsatisfactory_safety_rating"


def test_evaluate_conditional_passes_with_warning() -> None:
    carrier = _carrier_payload(safety_rating="C")["content"][0]["carrier"]
    eligible, reason = evaluate_eligibility(carrier)
    assert eligible is True
    assert reason == "conditional_safety_rating"


def test_evaluate_oos_in_past_rejects() -> None:
    past = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    carrier = _carrier_payload(oos_date=past)["content"][0]["carrier"]
    eligible, reason = evaluate_eligibility(carrier)
    assert eligible is False
    assert reason == "out_of_service"


# --------------------------------------------------------------------------- #
# 2. Route — authorized carrier passes (is_eligible=true)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_authorized_carrier_passes(
    client: AsyncClient, cleanup_mcs: list[str], mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)
    cleanup_mcs.append(mc)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(200, json=_carrier_payload())
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mc_number"] == mc
    assert body["is_eligible"] is True
    assert body["rejection_reason"] is None
    assert body["allowed_to_operate"] is True
    assert body["safety_rating"] == "Satisfactory"
    assert body["cached"] is False


# --------------------------------------------------------------------------- #
# 3. Route — inactive carrier fails
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_inactive_carrier_fails(
    client: AsyncClient, cleanup_mcs: list[str], mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)
    cleanup_mcs.append(mc)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(
                200, json=_carrier_payload(status_code="I", allowed="N")
            )
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_eligible"] is False
    # When allowed=N the operating_status is "NOT AUTHORIZED" and the rule
    # that fires first is the not_allowed gate.
    assert body["rejection_reason"] == "not_allowed_to_operate"


# --------------------------------------------------------------------------- #
# 4. Route — unsatisfactory safety rating fails
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_unsatisfactory_safety_fails(
    client: AsyncClient, cleanup_mcs: list[str], mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)
    cleanup_mcs.append(mc)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(200, json=_carrier_payload(safety_rating="U"))
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_eligible"] is False
    assert body["rejection_reason"] == "unsatisfactory_safety_rating"
    assert body["safety_rating"] == "Unsatisfactory"


# --------------------------------------------------------------------------- #
# 5. Route — conditional safety warns but passes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_conditional_safety_warns_but_passes(
    client: AsyncClient, cleanup_mcs: list[str], mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)
    cleanup_mcs.append(mc)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(200, json=_carrier_payload(safety_rating="C"))
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_eligible"] is True
    assert body["rejection_reason"] == "conditional_safety_rating"
    assert body["safety_rating"] == "Conditional"


# --------------------------------------------------------------------------- #
# 6. Route — FMCSA 404 (no such MC) returns mc_not_found
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_fmcsa_404_returns_mc_not_found(
    client: AsyncClient, mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)
    # Note: no DB row is written for not-found, so no cleanup needed.

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        # FMCSA returns 200 with empty content for unknown docket numbers;
        # we still cover the literal 404 path below in a separate test.
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(200, json=_empty_payload())
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_eligible"] is False
    assert body["rejection_reason"] == "mc_not_found"
    assert body["mc_number"] == mc

    # Confirm no row was persisted.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CarrierVerification).where(CarrierVerification.mc_number == mc)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
async def test_fmcsa_literal_404_also_returns_mc_not_found(
    client: AsyncClient, mc_counter: list[int]
) -> None:
    """Some MCs return an HTTP 404 directly (with non-string content) — same outcome."""
    mc = _next_mc(mc_counter)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(404, json={"content": [], "retrievalDate": "x"})
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_eligible"] is False
    assert body["rejection_reason"] == "mc_not_found"


# --------------------------------------------------------------------------- #
# 7. Route — FMCSA timeout returns 503 + Retry-After
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_fmcsa_timeout_returns_503(
    client: AsyncClient, mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            side_effect=httpx.TimeoutException("simulated timeout")
        )
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})

    assert res.status_code == 503, res.text
    assert res.headers.get("Retry-After") == "60"
    detail = res.json()["detail"]
    assert detail["reason"] == "fmcsa_unavailable"


# --------------------------------------------------------------------------- #
# 8. Cache hit doesn't call FMCSA twice
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_cache_hit_does_not_call_fmcsa_twice(
    client: AsyncClient, cleanup_mcs: list[str], mc_counter: list[int]
) -> None:
    mc = _next_mc(mc_counter)
    cleanup_mcs.append(mc)

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        route = router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(200, json=_carrier_payload())
        )

        # First call — cache miss, FMCSA hit.
        res1 = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})
        assert res1.status_code == 200
        assert res1.json()["cached"] is False

        # Second call — within 24h window, should be served from DB cache.
        res2 = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})
        assert res2.status_code == 200
        assert res2.json()["cached"] is True

        assert route.call_count == 1, (
            f"Expected exactly 1 FMCSA call, got {route.call_count}"
        )


# --------------------------------------------------------------------------- #
# 9. Circuit breaker opens after 5 consecutive failures
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_circuit_breaker_opens_after_threshold_failures(
    client: AsyncClient, mc_counter: list[int]
) -> None:
    breaker = get_circuit_breaker()
    breaker.reset()

    threshold = settings.FMCSA_CIRCUIT_FAIL_THRESHOLD
    assert threshold == 5  # sanity — matches plan

    mcs = [_next_mc(mc_counter) for _ in range(threshold)]

    with respx.mock(base_url=FMCSA_HOST, assert_all_called=False) as router:
        # All FMCSA calls fail with a timeout.
        for mc in mcs:
            router.get(f"{FMCSA_PATH}/{mc}").mock(
                side_effect=httpx.TimeoutException("simulated timeout")
            )

        # Hit the failure threshold — each returns 503.
        for mc in mcs:
            res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": mc})
            assert res.status_code == 503, res.text

        assert breaker.is_open, "circuit should be open after threshold failures"

        # Next request should short-circuit (no FMCSA call), returning 200 +
        # is_eligible=null + reason="fmcsa_unavailable".
        next_mc = _next_mc(mc_counter)
        # We do NOT add a respx route for this MC, and assert_all_mocked is
        # left at its default (True) — which means any actual HTTP would
        # raise. The route should bypass HTTP entirely.
        res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": next_mc})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["is_eligible"] is None
        assert body["rejection_reason"] == "fmcsa_unavailable"


# --------------------------------------------------------------------------- #
# 10. Route — invalid MC format returns 422
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_invalid_mc_format_returns_422(client: AsyncClient) -> None:
    res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": "ABC123"})
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert detail["reason"] == "invalid_mc_format"


@pytest.mark.asyncio(loop_scope="session")
async def test_too_long_mc_returns_422(client: AsyncClient) -> None:
    """9+ digits is also rejected; the regex bound is ``^\\d{1,8}$``."""
    # Pydantic's max_length=8 on the request schema fires first — that path
    # surfaces as 422 from FastAPI's request validation layer with a different
    # detail shape. Either path is acceptable; we just assert 422.
    res = await client.post(f"{API_PREFIX}/carrier/verify", json={"mc": "123456789"})
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------- #
# Extra: circuit-breaker unit test (no DB / no HTTP)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_circuit_breaker_unit_window_pruning() -> None:
    cb = _CircuitBreaker(fail_threshold=3, window_seconds=60.0, open_seconds=60.0)
    for _ in range(2):
        await cb.record_failure()
    assert not cb.is_open

    await cb.record_success()
    # success resets the failure log
    for _ in range(2):
        await cb.record_failure()
    assert not cb.is_open
    await cb.record_failure()
    assert cb.is_open


# --------------------------------------------------------------------------- #
# Extra: FMCSAClient.lookup_by_mc raises FMCSANotFound for empty content
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio(loop_scope="session")
async def test_client_raises_not_found_directly(mc_counter: list[int]) -> None:
    mc = _next_mc(mc_counter)
    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(200, json=_empty_payload())
        )
        async with FMCSAClient() as fmcsa_client:
            async with AsyncSessionLocal() as session:
                with pytest.raises(FMCSANotFound):
                    await fmcsa_client.lookup_by_mc(mc, session)


@pytest.mark.asyncio(loop_scope="session")
async def test_client_raises_unavailable_on_5xx(mc_counter: list[int]) -> None:
    mc = _next_mc(mc_counter)
    with respx.mock(base_url=FMCSA_HOST, assert_all_called=True) as router:
        router.get(f"{FMCSA_PATH}/{mc}").mock(
            return_value=httpx.Response(500, text="boom")
        )
        async with FMCSAClient() as fmcsa_client:
            async with AsyncSessionLocal() as session:
                with pytest.raises(FMCSAUnavailable):
                    await fmcsa_client.lookup_by_mc(mc, session)
