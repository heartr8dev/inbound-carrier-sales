"""Unit tests for the stateless negotiation engine.

These tests exercise the pricing math and decision tree in
``api.src.services.negotiation_engine`` directly — no HTTP layer — so
they're fast and don't need the database container.

All scenarios use a loadboard rate of $1000.00 with the default
``MAX_DISCOUNT_PCT = 0.10`` so the arithmetic is easy to follow:

* floor_price            = 1000 * 0.90 = 900.00
* round 1 max-concession = 1000 * 0.97 = 970.00 (3% off)
* round 2 max-concession = 1000 * 0.93 = 930.00 (7% off)
* round 3 max-concession = 1000 * 0.90 = 900.00 (10% off, == floor)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.src.config import settings
from api.src.schemas.enums import CarrierSentiment
from api.src.schemas.negotiation import NegotiateRequest, NegotiationState
from api.src.services.negotiation_engine import negotiate


# Sanity check: tests assume the default 10% discount cap. If an operator
# overrides MAX_DISCOUNT_PCT via env, that's a deployment choice — fail
# loudly here rather than produce confusing test failures downstream.
@pytest.fixture(autouse=True)
def _assert_default_discount() -> None:
    assert settings.MAX_DISCOUNT_PCT == pytest.approx(0.10), (
        "test suite is calibrated for MAX_DISCOUNT_PCT=0.10; "
        f"got {settings.MAX_DISCOUNT_PCT}"
    )


def _initial_state(loadboard: str = "1000.00", load_id: str = "LD-TEST") -> NegotiationState:
    return NegotiationState(
        load_id=load_id,
        loadboard_rate=Decimal(loadboard),
        round=0,
        agent_last_offer=None,
        carrier_last_offer=None,
        final_rate=None,
        status="pending",
    )


# ---------------------------------------------------------------------------
# 1. Accept on round 1 when carrier offers >= loadboard
# ---------------------------------------------------------------------------
def test_accept_round_one_when_carrier_meets_loadboard() -> None:
    state = _initial_state()
    req = NegotiateRequest(state=state, carrier_offer=Decimal("1000.00"))

    res = negotiate(req)

    assert res.state.status == "agreed"
    assert res.state.final_rate == Decimal("1000.00")
    assert res.state.round == 1
    assert res.counter_offer is None
    assert "1,000.00" in res.suggested_response


# ---------------------------------------------------------------------------
# 2. Counter on round 1 when carrier offers below first-round max-concession
# ---------------------------------------------------------------------------
def test_counter_round_one_when_offer_below_round_floor() -> None:
    state = _initial_state()
    # 800 is below the round-1 max concession (970) and below the hard
    # floor (900) — engine must counter rather than accept.
    req = NegotiateRequest(state=state, carrier_offer=Decimal("800.00"))

    res = negotiate(req)

    assert res.state.status == "pending"
    assert res.state.round == 1
    # Midpoint of agent_first_offer (1000) and round 1 floor (970) = 985
    assert res.state.agent_last_offer == Decimal("985.00")
    assert res.counter_offer == Decimal("985.00")
    assert res.state.carrier_last_offer == Decimal("800.00")


def test_counter_round_one_uses_origin_destination_in_phrase() -> None:
    state = _initial_state()
    req = NegotiateRequest(
        state=state,
        carrier_offer=Decimal("800.00"),
        origin="Dallas, TX",
        destination="Atlanta, GA",
    )

    res = negotiate(req)

    assert "Dallas, TX" in res.suggested_response
    assert "Atlanta, GA" in res.suggested_response


# ---------------------------------------------------------------------------
# 3. Full three-round walk to agreement
# ---------------------------------------------------------------------------
def test_full_three_round_walk_to_agreement() -> None:
    # Round 1: carrier opens at 800, engine counters to 985.
    state = _initial_state()
    r1 = negotiate(NegotiateRequest(state=state, carrier_offer=Decimal("800.00")))
    assert r1.state.status == "pending"
    assert r1.state.round == 1
    assert r1.state.agent_last_offer == Decimal("985.00")

    # Round 2: carrier moves up to 900, still below round-2 floor (930),
    # so engine counters again to midpoint(985, 930) = 957.50.
    r2 = negotiate(NegotiateRequest(state=r1.state, carrier_offer=Decimal("900.00")))
    assert r2.state.status == "pending"
    assert r2.state.round == 2
    assert r2.state.agent_last_offer == Decimal("957.50")

    # Round 3: carrier offers 900, which equals both floor and round-3
    # max-concession floor — engine agrees at carrier's number.
    r3 = negotiate(NegotiateRequest(state=r2.state, carrier_offer=Decimal("900.00")))
    assert r3.state.status == "agreed"
    assert r3.state.round == 3
    assert r3.state.final_rate == Decimal("900.00")
    assert "900" in r3.suggested_response


# ---------------------------------------------------------------------------
# 4. Walk-away on round 3 when offer is below floor
# ---------------------------------------------------------------------------
def test_walk_away_on_round_three_below_floor() -> None:
    # Hand-craft a round-2 state so we can drive round 3 directly.
    state_after_round_2 = NegotiationState(
        load_id="LD-WALK",
        loadboard_rate=Decimal("1000.00"),
        round=2,
        agent_last_offer=Decimal("957.50"),
        carrier_last_offer=Decimal("900.00"),
        final_rate=None,
        status="pending",
    )
    # Carrier digs in at 850 — below the 900 floor.  Engine walks.
    req = NegotiateRequest(state=state_after_round_2, carrier_offer=Decimal("850.00"))

    res = negotiate(req)

    assert res.state.status == "walked_away"
    assert res.state.round == 3
    assert res.state.final_rate is None
    assert "doesn't work" in res.suggested_response.lower() or "appreciate" in res.suggested_response.lower()


# ---------------------------------------------------------------------------
# 5. Floor is never crossed even when sentiment bump would push past it
# ---------------------------------------------------------------------------
def test_sentiment_bump_never_breaches_floor() -> None:
    # Round 3 hostile would naively give 10% + 1.5% = 11.5% off => 885,
    # but floor_price is 900 so the engine must clamp.
    state_after_round_2 = NegotiationState(
        load_id="LD-CLAMP",
        loadboard_rate=Decimal("1000.00"),
        round=2,
        agent_last_offer=Decimal("957.50"),
        carrier_last_offer=Decimal("900.00"),
        final_rate=None,
        status="pending",
    )
    # Carrier offers 890 on round 3 — below the 900 floor.
    # With hostile sentiment, naive math would lower round floor to 885,
    # which would falsely accept the 890.  Engine must clamp at 900 and
    # therefore walk away.
    req = NegotiateRequest(
        state=state_after_round_2,
        carrier_offer=Decimal("890.00"),
        carrier_sentiment=CarrierSentiment.HOSTILE,
    )

    res = negotiate(req)

    assert res.state.status == "walked_away"
    assert res.state.final_rate is None


# ---------------------------------------------------------------------------
# 6. Frustrated sentiment on round 2 adds 1.5% concession
# ---------------------------------------------------------------------------
def test_frustrated_sentiment_round_two_adds_concession() -> None:
    # State after round 1 with agent at 985.
    state_after_round_1 = NegotiationState(
        load_id="LD-FRUSTRATED",
        loadboard_rate=Decimal("1000.00"),
        round=1,
        agent_last_offer=Decimal("985.00"),
        carrier_last_offer=Decimal("800.00"),
        final_rate=None,
        status="pending",
    )
    # Round 2 base floor = 930.  With frustrated bump (+1.5%) it becomes 915.
    # Carrier offers 920 — would be REJECTED at 930 base, but ACCEPTED at 915.
    req = NegotiateRequest(
        state=state_after_round_1,
        carrier_offer=Decimal("920.00"),
        carrier_sentiment=CarrierSentiment.FRUSTRATED,
    )

    res = negotiate(req)

    assert res.state.status == "agreed"
    assert res.state.round == 2
    assert res.state.final_rate == Decimal("920.00")


def test_neutral_sentiment_round_two_uses_base_concession() -> None:
    """Control case: same round-2 offer without sentiment bump is rejected."""

    state_after_round_1 = NegotiationState(
        load_id="LD-CONTROL",
        loadboard_rate=Decimal("1000.00"),
        round=1,
        agent_last_offer=Decimal("985.00"),
        carrier_last_offer=Decimal("800.00"),
        final_rate=None,
        status="pending",
    )
    # 920 < 930 base round-2 floor — without bump, engine must counter, not agree.
    req = NegotiateRequest(
        state=state_after_round_1,
        carrier_offer=Decimal("920.00"),
        carrier_sentiment=CarrierSentiment.NEUTRAL,
    )

    res = negotiate(req)

    assert res.state.status == "pending"
    assert res.state.final_rate is None
    # Midpoint of 985 and 930 = 957.50
    assert res.state.agent_last_offer == Decimal("957.50")


# ---------------------------------------------------------------------------
# 7. Round counter increments correctly across successive calls
# ---------------------------------------------------------------------------
def test_round_counter_increments_each_turn() -> None:
    state = _initial_state()

    r1 = negotiate(NegotiateRequest(state=state, carrier_offer=Decimal("800.00")))
    assert r1.state.round == 1

    r2 = negotiate(NegotiateRequest(state=r1.state, carrier_offer=Decimal("850.00")))
    assert r2.state.round == 2

    r3 = negotiate(NegotiateRequest(state=r2.state, carrier_offer=Decimal("880.00")))
    assert r3.state.round == 3


# ---------------------------------------------------------------------------
# 8. Hostile sentiment on round 1 does NOT apply the bump
# ---------------------------------------------------------------------------
def test_hostile_sentiment_round_one_no_bump_applied() -> None:
    state = _initial_state()
    # Round 1 base floor = 970.  A 1.5% bump would push it to 955.
    # Carrier offers 960 with hostile sentiment.  Spec: bump only applies
    # on rounds 2/3, so engine must counter (not agree at 960).
    req = NegotiateRequest(
        state=state,
        carrier_offer=Decimal("960.00"),
        carrier_sentiment=CarrierSentiment.HOSTILE,
    )

    res = negotiate(req)

    assert res.state.status == "pending"
    assert res.state.round == 1
    # Confirms base round-1 floor of 970 was used (midpoint with 1000 = 985).
    assert res.state.agent_last_offer == Decimal("985.00")


# ---------------------------------------------------------------------------
# 9. Agreed at carrier_offer when it's between current_round_floor and
#    the agent's last offer
# ---------------------------------------------------------------------------
def test_agreed_at_carrier_offer_inside_round_window() -> None:
    state_after_round_1 = NegotiationState(
        load_id="LD-WINDOW",
        loadboard_rate=Decimal("1000.00"),
        round=1,
        agent_last_offer=Decimal("985.00"),
        carrier_last_offer=Decimal("800.00"),
        final_rate=None,
        status="pending",
    )
    # 950 is below agent_last (985) but above round-2 floor (930) and hard
    # floor (900) — branch 2 should fire and meet carrier where they are.
    req = NegotiateRequest(state=state_after_round_1, carrier_offer=Decimal("950.00"))

    res = negotiate(req)

    assert res.state.status == "agreed"
    assert res.state.round == 2
    assert res.state.final_rate == Decimal("950.00")
    assert res.state.carrier_last_offer == Decimal("950.00")
