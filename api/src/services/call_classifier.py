"""Post-call classification — derive outcome + sentiment from the extracted payload.

The HappyRobot agent posts a rich extraction payload to ``POST /api/v1/calls/log``.
This module turns that payload into the two enum values stored on every ``CallLog``
row (``outcome`` and ``sentiment``). Both columns are ``NOT NULL`` in the schema, so
every input must yield a value — the rule cascade falls through to
``CARRIER_HUNG_UP`` / ``NEUTRAL`` as natural defaults.
"""

from __future__ import annotations

from api.src.schemas.call import CallLogRequest
from api.src.schemas.enums import CallOutcome, CarrierSentiment

# Keyword sets for the lightweight sentiment heuristic. Order matters: hostile and
# frustrated are checked before positive/neutral so a transcript that mixes "thanks"
# with profanity is correctly flagged as hostile.
_HOSTILE_KEYWORDS: tuple[str, ...] = ("bullshit", "no way", "ridiculous", "fuck")
_FRUSTRATED_KEYWORDS: tuple[str, ...] = ("really?", "are you serious", "what?")
_POSITIVE_KEYWORDS: tuple[str, ...] = ("thanks", "perfect", "great")
_NEUTRAL_KEYWORDS: tuple[str, ...] = ("ok", "fine", "alright")


def classify_outcome(call_data: CallLogRequest) -> CallOutcome:
    """Map the extracted call payload to a single ``CallOutcome``.

    Rules are checked top-to-bottom; first match wins. See the workstream plan for
    the canonical rule list — this implementation mirrors it verbatim.
    """

    if call_data.final_agreed_rate is not None and call_data.transferred:
        return CallOutcome.TRANSFERRED_TO_REP

    if call_data.final_agreed_rate is not None:
        return CallOutcome.BOOKED

    if call_data.vetting_passed is False:
        return CallOutcome.CARRIER_FAILED_VETTING

    if call_data.loads_searched and call_data.matches_returned == 0:
        return CallOutcome.NO_MATCHING_LOADS

    if call_data.negotiation_rounds == 3 and call_data.final_agreed_rate is None:
        return CallOutcome.NEGOTIATION_STALLED

    if call_data.negotiation_rounds > 0 and call_data.final_agreed_rate is None:
        return CallOutcome.CARRIER_DECLINED_RATE

    return CallOutcome.CARRIER_HUNG_UP


def classify_sentiment(call_data: CallLogRequest) -> CarrierSentiment:
    """Return the carrier's sentiment for this call.

    Prefer the agent's AI Extract output when present. Otherwise apply a tiny
    keyword heuristic over ``transcript_summary``. The heuristic is intentionally
    conservative — checked hostile→frustrated→positive→neutral, defaulting to
    ``NEUTRAL`` when nothing matches (or no transcript is available).
    """

    if call_data.sentiment is not None:
        return call_data.sentiment

    transcript = (call_data.transcript_summary or "").lower()
    if not transcript:
        return CarrierSentiment.NEUTRAL

    if any(keyword in transcript for keyword in _HOSTILE_KEYWORDS):
        return CarrierSentiment.HOSTILE
    if any(keyword in transcript for keyword in _FRUSTRATED_KEYWORDS):
        return CarrierSentiment.FRUSTRATED
    if any(keyword in transcript for keyword in _POSITIVE_KEYWORDS):
        return CarrierSentiment.POSITIVE
    if any(keyword in transcript for keyword in _NEUTRAL_KEYWORDS):
        return CarrierSentiment.NEUTRAL

    return CarrierSentiment.NEUTRAL
