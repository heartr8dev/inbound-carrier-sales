"""Insert mock CallLog rows spread over a configurable historical window.

Used to populate the dashboard with plausible-looking traffic when no real
calls have flowed yet. Outcome weights mirror what a healthy inbound-sales
operation might produce; sentiment is conditionally sampled given the outcome
so the heatmap actually correlates (happy carriers tend to book, frustrated
ones tend to walk).

Defaults are tuned so the dashboard's four period pills (Today/7d/30d/All)
all show meaningful traffic: 3000 rows across 90 days is ~33 calls/day —
plenty for the 7d funnel to look populated and the 30d/All view to show
real depth, while still leaving plenty of room in business hours.

Usage::

    python scripts/generate_mock_calls.py                          # 3000 rows × 90 days (default)
    python scripts/generate_mock_calls.py --reset                  # truncate first
    python scripts/generate_mock_calls.py --count 250 --days-back 7   # the original demo profile
    python scripts/generate_mock_calls.py --count 10000 --days-back 180  # half-year archive
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from api.src.db import AsyncSessionLocal
from api.src.models.call_log import CallLog
from api.src.models.load import Load
from api.src.schemas.enums import CallOutcome, CarrierSentiment, EquipmentType


REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = REPO_ROOT / "data" / "seed_loads.json"
CHICAGO_TZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# Sampling tables
# ---------------------------------------------------------------------------


OUTCOME_WEIGHTS: list[tuple[CallOutcome, float]] = [
    (CallOutcome.BOOKED, 0.35),
    (CallOutcome.CARRIER_DECLINED_RATE, 0.20),
    (CallOutcome.NO_MATCHING_LOADS, 0.15),
    (CallOutcome.CARRIER_FAILED_VETTING, 0.15),
    (CallOutcome.NEGOTIATION_STALLED, 0.10),
    (CallOutcome.CARRIER_HUNG_UP, 0.05),
]

# Outcome → list[(sentiment, weight)]. Anything not listed falls back to neutral.
SENTIMENT_BY_OUTCOME: dict[CallOutcome, list[tuple[CarrierSentiment, float]]] = {
    CallOutcome.BOOKED: [
        (CarrierSentiment.POSITIVE, 0.70),
        (CarrierSentiment.NEUTRAL, 0.20),
        (CarrierSentiment.SKEPTICAL, 0.10),
    ],
    CallOutcome.TRANSFERRED_TO_REP: [
        (CarrierSentiment.POSITIVE, 0.65),
        (CarrierSentiment.NEUTRAL, 0.25),
        (CarrierSentiment.SKEPTICAL, 0.10),
    ],
    CallOutcome.CARRIER_DECLINED_RATE: [
        (CarrierSentiment.FRUSTRATED, 0.40),
        (CarrierSentiment.NEUTRAL, 0.30),
        (CarrierSentiment.SKEPTICAL, 0.20),
        (CarrierSentiment.POSITIVE, 0.10),
    ],
    CallOutcome.NEGOTIATION_STALLED: [
        (CarrierSentiment.FRUSTRATED, 0.45),
        (CarrierSentiment.SKEPTICAL, 0.30),
        (CarrierSentiment.NEUTRAL, 0.20),
        (CarrierSentiment.HOSTILE, 0.05),
    ],
    CallOutcome.CARRIER_FAILED_VETTING: [
        (CarrierSentiment.NEUTRAL, 0.50),
        (CarrierSentiment.SKEPTICAL, 0.30),
        (CarrierSentiment.FRUSTRATED, 0.20),
    ],
    CallOutcome.NO_MATCHING_LOADS: [
        (CarrierSentiment.NEUTRAL, 0.55),
        (CarrierSentiment.SKEPTICAL, 0.25),
        (CarrierSentiment.FRUSTRATED, 0.20),
    ],
    CallOutcome.CARRIER_HUNG_UP: [
        (CarrierSentiment.FRUSTRATED, 0.50),
        (CarrierSentiment.HOSTILE, 0.20),
        (CarrierSentiment.NEUTRAL, 0.20),
        (CarrierSentiment.SKEPTICAL, 0.10),
    ],
}


CARRIER_COMPANIES = [
    "Lone Star Logistics",
    "Midwest Freightways",
    "Pacific Coast Carriers",
    "Apex Trucking LLC",
    "Sunbelt Express",
    "Rocky Mountain Hauling",
    "Eagle Transport Co",
    "Frontier Freight",
    "Summit Logistics",
    "Riverbend Trucking",
    "Heartland Hauling",
    "Iron Horse Transport",
    "Cascade Carriers",
    "Gulf Coast Freight",
    "Northern Light Logistics",
    "Coastal Trucking Solutions",
    "Prairie State Express",
    "High Plains Hauling",
    "Bayou Freight Lines",
    "Silver Wheel Transport",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pick_weighted(rng: random.Random, items: list[tuple[Any, float]]) -> Any:
    values, weights = zip(*items, strict=False)
    return rng.choices(values, weights=weights, k=1)[0]


def _random_mc(rng: random.Random) -> str:
    """7-digit MC number (no leading zeros)."""
    return str(rng.randint(1_000_000, 9_999_999))


def _random_call_id(rng: random.Random) -> str:
    suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=8))
    return f"mock-{suffix}-{uuid.uuid4().hex[:6]}"


def _sample_created_at(rng: random.Random, days_back: int) -> datetime:
    """Bias toward weekday 08:00–18:00 America/Chicago.

    Two-stage rejection sample: pick a uniform datetime in the window, then
    accept with probability 1.0 inside business hours and 0.15 outside. This
    gives ~85% business-hours density without hard-coding bucket counts.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    span_seconds = int((end - start).total_seconds())
    for _ in range(20):
        ts_utc = start + timedelta(seconds=rng.randint(0, span_seconds))
        local = ts_utc.astimezone(CHICAGO_TZ)
        is_weekday = local.weekday() < 5
        is_business_hours = 8 <= local.hour < 18
        accept_prob = 1.0 if (is_weekday and is_business_hours) else 0.15
        if rng.random() < accept_prob:
            return ts_utc
    return ts_utc  # fall through after retries


def _negotiation_rounds(rng: random.Random, outcome: CallOutcome) -> int:
    if outcome == CallOutcome.NEGOTIATION_STALLED:
        return 3
    if outcome in (CallOutcome.BOOKED, CallOutcome.TRANSFERRED_TO_REP):
        return rng.choices([1, 2, 3], weights=[0.45, 0.35, 0.20], k=1)[0]
    if outcome == CallOutcome.CARRIER_DECLINED_RATE:
        return rng.choices([1, 2, 3], weights=[0.40, 0.35, 0.25], k=1)[0]
    return 0


def _build_row(
    rng: random.Random, loads: list[dict[str, Any]], days_back: int = 7
) -> dict[str, Any]:
    outcome: CallOutcome = _pick_weighted(rng, OUTCOME_WEIGHTS)
    sentiment: CarrierSentiment = _pick_weighted(rng, SENTIMENT_BY_OUTCOME[outcome])

    load = rng.choice(loads)
    loadboard_rate = Decimal(str(load["loadboard_rate"]))
    initial_ask: Decimal | None = None
    final_rate: Decimal | None = None
    load_id_discussed: str | None = load["load_id"]

    if outcome == CallOutcome.CARRIER_FAILED_VETTING:
        # Carrier never got to load discussion → blank out load context.
        load_id_discussed = None

    if outcome != CallOutcome.NO_MATCHING_LOADS and outcome != CallOutcome.CARRIER_FAILED_VETTING:
        initial_ask = (loadboard_rate * Decimal(str(round(rng.uniform(0.80, 0.92), 4)))).quantize(
            Decimal("0.01")
        )

    if outcome in (CallOutcome.BOOKED, CallOutcome.TRANSFERRED_TO_REP):
        final_rate = (loadboard_rate * Decimal(str(round(rng.uniform(0.92, 0.99), 4)))).quantize(
            Decimal("0.01")
        )

    rounds = _negotiation_rounds(rng, outcome)
    duration = rng.randint(45, 540)

    summary_map = {
        CallOutcome.BOOKED: "Carrier accepted final rate; booked load and confirmed pickup.",
        CallOutcome.TRANSFERRED_TO_REP: "Carrier qualified; transferred to sales rep to close booking.",
        CallOutcome.CARRIER_DECLINED_RATE: "Carrier declined after multiple counters; ended call.",
        CallOutcome.NEGOTIATION_STALLED: "Walked to round 3 without convergence; agent walked away.",
        CallOutcome.CARRIER_FAILED_VETTING: "FMCSA check returned ineligible; call ended before load discussion.",
        CallOutcome.NO_MATCHING_LOADS: "No loads matched carrier's equipment / lane / pickup window.",
        CallOutcome.CARRIER_HUNG_UP: "Carrier disconnected mid-call.",
    }
    transcript_summary = summary_map[outcome]

    created_at = _sample_created_at(rng, days_back=days_back)

    return {
        "call_id": _random_call_id(rng),
        "carrier_mc": _random_mc(rng),
        "carrier_name": None,
        "carrier_company": rng.choice(CARRIER_COMPANIES),
        "load_id_discussed": load_id_discussed,
        "loadboard_rate": loadboard_rate if load_id_discussed else None,
        "initial_carrier_ask": initial_ask,
        "final_agreed_rate": final_rate,
        "negotiation_rounds": rounds,
        "outcome": outcome,
        "sentiment": sentiment,
        "equipment_type_requested": EquipmentType(load["equipment_type"]),
        "origin_requested": load["origin"],
        "destination_requested": load["destination"],
        "call_duration_seconds": duration,
        "transcript_summary": transcript_summary,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _load_lanes(session) -> list[dict[str, Any]]:
    """Prefer rows from the DB; fall back to the seed file if empty."""
    rows = (
        await session.execute(
            select(
                Load.load_id,
                Load.origin,
                Load.destination,
                Load.equipment_type,
                Load.loadboard_rate,
            )
        )
    ).all()
    if rows:
        return [
            {
                "load_id": r.load_id,
                "origin": r.origin,
                "destination": r.destination,
                "equipment_type": r.equipment_type.value if hasattr(r.equipment_type, "value") else r.equipment_type,
                "loadboard_rate": float(r.loadboard_rate),
            }
            for r in rows
        ]
    return json.loads(SEED_PATH.read_text())


async def generate(count: int, reset: bool, seed: int | None, days_back: int) -> int:
    rng = random.Random(seed)
    async with AsyncSessionLocal() as session:
        if reset:
            await session.execute(delete(CallLog))
            await session.commit()

        loads = await _load_lanes(session)
        if not loads:
            print("ERROR: no loads available (seed the loads table first)", file=sys.stderr)
            return 0

        # Batch the insert so a 10K seed doesn't hold the whole row set in
        # one transaction stream.
        BATCH = 500
        inserted = 0
        for batch_start in range(0, count, BATCH):
            batch_n = min(BATCH, count - batch_start)
            rows = [
                CallLog(**_build_row(rng, loads, days_back=days_back))
                for _ in range(batch_n)
            ]
            session.add_all(rows)
            await session.commit()
            inserted += batch_n
        return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate mock CallLog rows for the dashboard.")
    parser.add_argument("--count", type=int, default=3000, help="number of rows to insert (default 3000)")
    parser.add_argument("--days-back", type=int, default=90, help="historical window in days (default 90)")
    parser.add_argument("--reset", action="store_true", help="truncate call_logs before inserting")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for deterministic runs")
    args = parser.parse_args()

    inserted = asyncio.run(
        generate(
            count=args.count,
            reset=args.reset,
            seed=args.seed,
            days_back=args.days_back,
        )
    )
    print(f"call_logs inserted: {inserted} over {args.days_back} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
