"""Generate a wide, rolling-date load board for the demo.

Produces ~300 loads across 60 major US freight lanes, 5 equipment types,
spread over the next 30 days of pickup dates with realistic per-mile rates.
Idempotent upsert by load_id.

Usage (locally):
    python scripts/generate_loads.py --count 300 --days-ahead 30 --reset

Run on prod via Fly:
    flyctl ssh console --app inbound-carrier-sales-api \\
        -C "sh -c 'cd /app && python scripts/generate_loads.py --reset'"
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from api.src.db import AsyncSessionLocal
from api.src.models.load import Load
from api.src.schemas.enums import EquipmentType


# 60 lanes across major US freight corridors. (origin, destination, miles)
LANES: list[tuple[str, str, int]] = [
    ("Dallas, TX", "Atlanta, GA", 781),
    ("Dallas, TX", "Houston, TX", 240),
    ("Dallas, TX", "Chicago, IL", 925),
    ("Dallas, TX", "Phoenix, AZ", 1067),
    ("Dallas, TX", "Memphis, TN", 452),
    ("Dallas, TX", "Oklahoma City, OK", 207),
    ("Houston, TX", "New Orleans, LA", 348),
    ("Houston, TX", "Atlanta, GA", 791),
    ("Houston, TX", "Laredo, TX", 318),
    ("Houston, TX", "Memphis, TN", 568),
    ("Atlanta, GA", "Miami, FL", 661),
    ("Atlanta, GA", "Charlotte, NC", 245),
    ("Atlanta, GA", "Nashville, TN", 248),
    ("Atlanta, GA", "Jacksonville, FL", 346),
    ("Atlanta, GA", "Tampa, FL", 458),
    ("Chicago, IL", "Los Angeles, CA", 2015),
    ("Chicago, IL", "Indianapolis, IN", 184),
    ("Chicago, IL", "Detroit, MI", 282),
    ("Chicago, IL", "Minneapolis, MN", 408),
    ("Chicago, IL", "Kansas City, MO", 508),
    ("Los Angeles, CA", "Phoenix, AZ", 372),
    ("Los Angeles, CA", "Las Vegas, NV", 270),
    ("Los Angeles, CA", "Sacramento, CA", 384),
    ("Los Angeles, CA", "Denver, CO", 1015),
    ("Los Angeles, CA", "Seattle, WA", 1135),
    ("Memphis, TN", "Nashville, TN", 211),
    ("Memphis, TN", "Louisville, KY", 384),
    ("Memphis, TN", "Birmingham, AL", 240),
    ("Memphis, TN", "St. Louis, MO", 285),
    ("Phoenix, AZ", "Albuquerque, NM", 419),
    ("Phoenix, AZ", "Tucson, AZ", 117),
    ("Phoenix, AZ", "El Paso, TX", 432),
    ("Phoenix, AZ", "San Diego, CA", 355),
    ("Seattle, WA", "Portland, OR", 174),
    ("Seattle, WA", "Spokane, WA", 280),
    ("Seattle, WA", "Boise, ID", 497),
    ("Sacramento, CA", "Reno, NV", 132),
    ("Sacramento, CA", "San Francisco, CA", 88),
    ("Sacramento, CA", "Portland, OR", 583),
    ("Tampa, FL", "Atlanta, GA", 458),
    ("Tampa, FL", "Miami, FL", 280),
    ("Tampa, FL", "Orlando, FL", 84),
    ("Laredo, TX", "Dallas, TX", 433),
    ("Laredo, TX", "Houston, TX", 318),
    ("Laredo, TX", "San Antonio, TX", 156),
    ("Newark, NJ", "Boston, MA", 220),
    ("Newark, NJ", "Philadelphia, PA", 95),
    ("Newark, NJ", "Pittsburgh, PA", 366),
    ("Newark, NJ", "Baltimore, MD", 184),
    ("Denver, CO", "Salt Lake City, UT", 525),
    ("Denver, CO", "Kansas City, MO", 600),
    ("Denver, CO", "Albuquerque, NM", 446),
    ("Kansas City, MO", "Indianapolis, IN", 488),
    ("Kansas City, MO", "St. Louis, MO", 248),
    ("Indianapolis, IN", "Cincinnati, OH", 112),
    ("Indianapolis, IN", "Louisville, KY", 114),
    ("Charlotte, NC", "Jacksonville, FL", 392),
    ("Charlotte, NC", "Raleigh, NC", 165),
    ("Charlotte, NC", "Richmond, VA", 290),
    ("Detroit, MI", "Cleveland, OH", 169),
    ("Detroit, MI", "Toledo, OH", 60),
]

EQUIPMENT_RATES: dict[str, tuple[float, float, str]] = {
    # equipment_type → (per_mile_min, per_mile_max, dim_template)
    EquipmentType.DRY_VAN.value:    (2.00, 3.00, "53L x 102W x 110H"),
    EquipmentType.REEFER.value:     (2.50, 3.60, "53L x 102W x 110H"),
    EquipmentType.FLATBED.value:    (2.50, 4.00, "48L x 102W"),
    EquipmentType.STEP_DECK.value:  (2.75, 4.20, "48L x 102W"),
    EquipmentType.POWER_ONLY.value: (1.80, 2.80, "n/a"),
}

EQUIPMENT_COMMODITIES: dict[str, list[str]] = {
    EquipmentType.DRY_VAN.value:    ["Retail Goods", "Paper Products", "Electronics", "Packaged Food", "Apparel", "Auto Parts", "Household Goods"],
    EquipmentType.REEFER.value:     ["Produce", "Frozen Foods", "Dairy", "Meat", "Pharmaceuticals", "Beverages", "Flowers"],
    EquipmentType.FLATBED.value:    ["Steel Coils", "Lumber", "Pipe", "Construction Materials", "Machinery", "Roofing"],
    EquipmentType.STEP_DECK.value:  ["Heavy Machinery", "Construction Equipment", "Tractors", "Generators", "Industrial Tanks"],
    EquipmentType.POWER_ONLY.value: ["Trailer Repositioning", "Pre-loaded Container", "Drop & Hook Trailer"],
}

NOTES_OPTIONS = [
    None, None, None,  # 3x more likely no notes
    "Driver assist required",
    "Dock-high only",
    "Tarp required",
    "Hazmat — placards needed",
    "Lumper fee paid by broker",
    "Pre-cooled to 34F",
    "Live load / live unload",
    "Drop trailer OK",
    "Team drivers required",
    "Oversize — permits attached",
]


DEMO_SPOTLIGHTS: list[tuple[str, str, int, str]] = [
    # Lanes the README's demo script uses — guaranteed multiple matches in the
    # next 5 days so Riley always has something to pitch for the obvious queries.
    ("Dallas, TX", "Atlanta, GA", 781, EquipmentType.DRY_VAN.value),
    ("Dallas, TX", "Atlanta, GA", 781, EquipmentType.REEFER.value),
    ("Memphis, TN", "Nashville, TN", 211, EquipmentType.DRY_VAN.value),
    ("Sacramento, CA", "Reno, NV", 132, EquipmentType.REEFER.value),
    ("Houston, TX", "New Orleans, LA", 348, EquipmentType.FLATBED.value),
    ("Chicago, IL", "Los Angeles, CA", 2015, EquipmentType.DRY_VAN.value),
]


def _build_load(idx: int, lane: tuple[str, str, int], equipment: str, pickup: datetime, rng: random.Random) -> dict:
    origin, destination, miles = lane
    rate_min, rate_max, dim = EQUIPMENT_RATES[equipment]
    per_mile = rng.uniform(rate_min, rate_max)
    loadboard = round(per_mile * miles, -1)
    transit_hours = max(8, int(miles / 50) + rng.randint(4, 12))
    delivery = pickup + timedelta(hours=transit_hours)
    if equipment == EquipmentType.POWER_ONLY.value:
        weight, pieces = rng.randint(15000, 25000), 1
    elif equipment in (EquipmentType.STEP_DECK.value, EquipmentType.FLATBED.value):
        weight, pieces = rng.randint(20000, 45000), rng.randint(1, 6)
    else:
        weight, pieces = rng.randint(8000, 44000), rng.randint(8, 30)
    return {
        "load_id": f"LD-{idx:04d}",
        "origin": origin,
        "destination": destination,
        "pickup_datetime": pickup,
        "delivery_datetime": delivery,
        "equipment_type": equipment,
        "loadboard_rate": Decimal(str(loadboard)),
        "notes": rng.choice(NOTES_OPTIONS),
        "weight": weight,
        "commodity_type": rng.choice(EQUIPMENT_COMMODITIES[equipment]),
        "num_of_pieces": pieces,
        "miles": miles,
        "dimensions": dim,
        "is_available": True,
    }


def generate_loads(count: int, days_ahead: int, seed: int | None) -> list[dict]:
    if seed is not None:
        random.seed(seed)
    rng = random.Random(seed) if seed is not None else random.Random()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    loads: list[dict] = []
    idx = 1
    # Spotlight passes: 4 loads per (lane, equipment) on days 0/1/2/3 so demo
    # queries against the next week are guaranteed to hit.
    for lane in DEMO_SPOTLIGHTS:
        origin, destination, miles, eq = lane
        for day_offset in (0, 1, 2, 3):
            pickup = today + timedelta(days=day_offset, hours=rng.choice([8, 10, 12, 14, 16]))
            loads.append(_build_load(idx, (origin, destination, miles), eq, pickup, rng))
            idx += 1
    # Remaining loads: random across all lanes/equipment/dates.
    remaining = max(0, count - len(loads))
    for _ in range(remaining):
        lane = rng.choice(LANES)
        equipment = rng.choice(list(EQUIPMENT_RATES.keys()))
        offset_days = rng.randint(0, days_ahead - 1)
        pickup_hour = rng.choice([6, 8, 10, 12, 14, 16, 18])
        pickup = today + timedelta(days=offset_days, hours=pickup_hour)
        loads.append(_build_load(idx, lane, equipment, pickup, rng))
        idx += 1
    return loads


async def write_loads(loads: list[dict], reset: bool) -> int:
    async with AsyncSessionLocal() as session:
        if reset:
            await session.execute(delete(Load))
        stmt = insert(Load).values(loads)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Load.load_id],
            set_={c: stmt.excluded[c] for c in (
                "origin", "destination", "pickup_datetime", "delivery_datetime",
                "equipment_type", "loadboard_rate", "notes", "weight",
                "commodity_type", "num_of_pieces", "miles", "dimensions", "is_available",
            )},
        )
        await session.execute(stmt)
        await session.commit()
    return len(loads)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count", type=int, default=300, help="Number of loads to generate.")
    p.add_argument("--days-ahead", type=int, default=30, help="Pickup dates span today .. today+N days.")
    p.add_argument("--reset", action="store_true", help="Delete all existing loads before insert.")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    args = p.parse_args()
    loads = generate_loads(args.count, args.days_ahead, args.seed)
    written = asyncio.run(write_loads(loads, args.reset))
    earliest = min(l["pickup_datetime"] for l in loads).date()
    latest = max(l["pickup_datetime"] for l in loads).date()
    print(f"loads upserted: {written} | pickup window: {earliest} → {latest} | {len(LANES)} lanes × 5 equipment types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
