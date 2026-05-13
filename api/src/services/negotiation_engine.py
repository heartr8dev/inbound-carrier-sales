"""Stateless negotiation engine.

The HappyRobot agent (or any caller) supplies the full prior
``NegotiationState`` plus the latest ``carrier_offer`` and we return the
updated state along with a tactical natural-language reply the agent can
read aloud. No persistence happens here; every request carries its own
history.

Pricing rules (per Workstream C plan):

* ``floor_price = loadboard_rate * (1 - settings.MAX_DISCOUNT_PCT)`` — hard
  lower bound for any final rate.
* ``agent_first_offer = loadboard_rate`` — the opening anchor on round 1.
* Concession curve, cumulative max % off loadboard by round:
  round 1 = 3%, round 2 = 7%, round 3 = ``MAX_DISCOUNT_PCT * 100``.
* Sentiment adjustment: on round 2 or 3 with carrier sentiment
  ``frustrated`` or ``hostile``, add an extra 1.5% concession on top of
  the round's curve — still capped at ``floor_price``.

Decision tree (per call):

1. ``carrier_offer >= agent_last_offer`` → ``agreed`` at ``agent_last_offer``.
2. Else if ``carrier_offer >= floor_price`` AND
   ``carrier_offer >= current_round_floor`` → ``agreed`` at ``carrier_offer``.
3. Else if ``round < 3`` → counter at midpoint of ``agent_last_offer`` and
   the round's max-concession price; status stays ``pending``.
4. Else (``round == 3`` and offer is below the floor) → ``walked_away``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from api.src.config import settings
from api.src.schemas.enums import CarrierSentiment
from api.src.schemas.negotiation import (
    NegotiateRequest,
    NegotiateResponse,
    NegotiationState,
)

# Cumulative max-concession curve by negotiation round.
# Round 3 uses settings.MAX_DISCOUNT_PCT so the operator can dial the floor.
_BASE_CONCESSION_BY_ROUND: dict[int, Decimal] = {
    1: Decimal("0.03"),
    2: Decimal("0.07"),
}

_SENTIMENT_BUMP = Decimal("0.015")
_AGGRESSIVE_SENTIMENTS = {CarrierSentiment.FRUSTRATED, CarrierSentiment.HOSTILE}

_CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """Quantise to cents using banker-free half-up rounding."""

    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _fmt(value: Decimal) -> str:
    """Format a money Decimal as a human-friendly string with commas."""

    return f"{_money(value):,.2f}"


def _cumulative_concession(round_num: int) -> Decimal:
    """Return the cumulative max-concession fraction for ``round_num``."""

    if round_num <= 0:
        return Decimal("0")
    if round_num >= 3:
        return Decimal(str(settings.MAX_DISCOUNT_PCT))
    return _BASE_CONCESSION_BY_ROUND[round_num]


def _round_floor(
    loadboard_rate: Decimal,
    floor_price: Decimal,
    round_num: int,
    sentiment: CarrierSentiment | None,
) -> Decimal:
    """Lowest price we are willing to sit at this round, sentiment-adjusted."""

    concession = _cumulative_concession(round_num)
    if (
        sentiment in _AGGRESSIVE_SENTIMENTS
        and round_num >= 2
    ):
        concession += _SENTIMENT_BUMP
    price = loadboard_rate * (Decimal("1") - concession)
    # Sentiment bump (and any future bumps) must never cross floor_price.
    if price < floor_price:
        price = floor_price
    return _money(price)


def negotiate(request: NegotiateRequest) -> NegotiateResponse:
    """Drive one negotiation turn forward and produce an agent reply."""

    prior = request.state
    loadboard_rate = Decimal(prior.loadboard_rate)
    floor_price = _money(
        loadboard_rate * (Decimal("1") - Decimal(str(settings.MAX_DISCOUNT_PCT)))
    )

    # If the caller has already closed the deal, just echo state with the
    # appropriate canned reply rather than re-running the tree.
    if prior.status != "pending":
        return _terminal_response(prior)

    carrier_offer = _money(Decimal(request.carrier_offer))
    next_round = prior.round + 1

    # On the very first turn the agent has not yet "spoken"; the opening
    # anchor is the full loadboard rate.
    agent_last_offer = (
        _money(Decimal(prior.agent_last_offer))
        if prior.agent_last_offer is not None
        else _money(loadboard_rate)
    )

    current_round_floor = _round_floor(
        loadboard_rate=loadboard_rate,
        floor_price=floor_price,
        round_num=next_round,
        sentiment=request.carrier_sentiment,
    )

    # Branch 1: carrier meets or exceeds the agent's standing offer.
    if carrier_offer >= agent_last_offer:
        final_rate = agent_last_offer
        new_state = NegotiationState(
            load_id=prior.load_id,
            loadboard_rate=loadboard_rate,
            round=next_round,
            agent_last_offer=agent_last_offer,
            carrier_last_offer=carrier_offer,
            final_rate=final_rate,
            status="agreed",
        )
        return NegotiateResponse(
            state=new_state,
            suggested_response=(
                f"Perfect — we've got a deal at ${_fmt(final_rate)}. "
                "Let me transfer you over to finalize the rate confirmation."
            ),
            counter_offer=None,
        )

    # Branch 2: carrier offer is between this round's floor and the agent's
    # last offer, and still above the hard floor.  Meet them where they are.
    if carrier_offer >= floor_price and carrier_offer >= current_round_floor:
        final_rate = carrier_offer
        new_state = NegotiationState(
            load_id=prior.load_id,
            loadboard_rate=loadboard_rate,
            round=next_round,
            agent_last_offer=agent_last_offer,
            carrier_last_offer=carrier_offer,
            final_rate=final_rate,
            status="agreed",
        )
        return NegotiateResponse(
            state=new_state,
            suggested_response=(
                f"Perfect — we've got a deal at ${_fmt(final_rate)}. "
                "Let me transfer you over to finalize the rate confirmation."
            ),
            counter_offer=None,
        )

    # Branch 3: still have rounds left — counter at the midpoint of our
    # standing offer and this round's max-concession price.
    if next_round < 3:
        counter = _money((agent_last_offer + current_round_floor) / Decimal("2"))
        # Safety: never counter below the hard floor.
        if counter < floor_price:
            counter = floor_price

        new_state = NegotiationState(
            load_id=prior.load_id,
            loadboard_rate=loadboard_rate,
            round=next_round,
            agent_last_offer=counter,
            carrier_last_offer=carrier_offer,
            final_rate=None,
            status="pending",
        )

        if next_round == 1:
            origin = request.origin or "origin"
            destination = request.destination or "destination"
            suggested = (
                f"That's already a strong rate for {origin}→{destination} this week "
                "— I've got carriers booking it at this level."
            )
        else:  # next_round == 2
            suggested = (
                "I hear you. Let me see what flexibility I have on my end "
                f"— I can come up to ${_fmt(counter)}."
            )

        return NegotiateResponse(
            state=new_state,
            suggested_response=suggested,
            counter_offer=counter,
        )

    # next_round == 3 path: if we didn't agree above, check whether we can
    # still pitch one final counter at the round-3 floor, otherwise walk.
    if next_round == 3:
        # If carrier sits between floor_price and current_round_floor we
        # already agreed in branch 2.  If they're below floor_price entirely
        # we walk.  If they're above floor but below current_round_floor we
        # can't reach them — also walk (we've exhausted concessions).
        # Per spec: "Else (round == 3 and offer below floor) → walked_away".
        new_state = NegotiationState(
            load_id=prior.load_id,
            loadboard_rate=loadboard_rate,
            round=next_round,
            agent_last_offer=current_round_floor,
            carrier_last_offer=carrier_offer,
            final_rate=None,
            status="walked_away",
        )
        return NegotiateResponse(
            state=new_state,
            suggested_response=(
                "I understand if it doesn't work for you. Appreciate the call "
                "— we get new loads daily, definitely reach back out."
            ),
            counter_offer=None,
        )

    # Shouldn't happen — state.round capped at 3 by schema — but be safe.
    raise ValueError(f"Negotiation overflowed past round 3: {next_round}")


def _terminal_response(state: NegotiationState) -> NegotiateResponse:
    """Re-issue a canned reply for an already-closed negotiation."""

    if state.status == "agreed" and state.final_rate is not None:
        return NegotiateResponse(
            state=state,
            suggested_response=(
                f"Perfect — we've got a deal at ${_fmt(Decimal(state.final_rate))}. "
                "Let me transfer you over to finalize the rate confirmation."
            ),
            counter_offer=None,
        )
    return NegotiateResponse(
        state=state,
        suggested_response=(
            "I understand if it doesn't work for you. Appreciate the call "
            "— we get new loads daily, definitely reach back out."
        ),
        counter_offer=None,
    )
