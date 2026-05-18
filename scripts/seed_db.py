"""Idempotent loader for data/seed_loads.json into the loads table.

Pickup / delivery datetimes in the JSON file are anchored to 2026-05-13 (the
day the seed was first authored). At load time they're shifted forward so the
earliest pickup is `today` — keeps the demo loads matchable against `today /
tomorrow / this week` queries no matter when the seed is run. Pass --no-rebase
to keep the absolute dates as-written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from api.src.db import AsyncSessionLocal
from api.src.models.load import Load


REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = REPO_ROOT / "data" / "seed_loads.json"
SEED_EPOCH = datetime(2026, 5, 13, tzinfo=timezone.utc)


def _rebase_offset(rows: list[dict[str, Any]]) -> timedelta:
    earliest = min(datetime.fromisoformat(r["pickup_datetime"]) for r in rows)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - earliest.replace(hour=0, minute=0, second=0, microsecond=0)


def _coerce_row(raw: dict[str, Any], offset: timedelta | None) -> dict[str, Any]:
    pickup = datetime.fromisoformat(raw["pickup_datetime"])
    delivery = datetime.fromisoformat(raw["delivery_datetime"])
    if offset is not None:
        pickup = pickup + offset
        delivery = delivery + offset
    return {
        "load_id": raw["load_id"],
        "origin": raw["origin"],
        "destination": raw["destination"],
        "pickup_datetime": pickup,
        "delivery_datetime": delivery,
        "equipment_type": raw["equipment_type"],
        "loadboard_rate": Decimal(str(raw["loadboard_rate"])),
        "notes": raw.get("notes"),
        "weight": int(raw["weight"]),
        "commodity_type": raw["commodity_type"],
        "num_of_pieces": int(raw["num_of_pieces"]),
        "miles": int(raw["miles"]),
        "dimensions": raw["dimensions"],
        "is_available": raw.get("is_available", True),
    }


async def seed(skip_if_exists: bool, rebase: bool = True) -> int:
    payload = json.loads(SEED_PATH.read_text())
    offset = _rebase_offset(payload) if rebase else None
    rows = [_coerce_row(r, offset) for r in payload]

    async with AsyncSessionLocal() as session:
        if skip_if_exists:
            existing = await session.execute(select(Load.load_id))
            existing_ids = {r[0] for r in existing.all()}
            rows = [r for r in rows if r["load_id"] not in existing_ids]
            if not rows:
                return 0

        stmt = insert(Load).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Load.load_id],
            set_={
                "origin": stmt.excluded.origin,
                "destination": stmt.excluded.destination,
                "pickup_datetime": stmt.excluded.pickup_datetime,
                "delivery_datetime": stmt.excluded.delivery_datetime,
                "equipment_type": stmt.excluded.equipment_type,
                "loadboard_rate": stmt.excluded.loadboard_rate,
                "notes": stmt.excluded.notes,
                "weight": stmt.excluded.weight,
                "commodity_type": stmt.excluded.commodity_type,
                "num_of_pieces": stmt.excluded.num_of_pieces,
                "miles": stmt.excluded.miles,
                "dimensions": stmt.excluded.dimensions,
                "is_available": stmt.excluded.is_available,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed loads from data/seed_loads.json")
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Skip rows whose load_id already exists rather than upserting them.",
    )
    parser.add_argument(
        "--no-rebase",
        action="store_true",
        help="Use absolute pickup/delivery datetimes from the JSON file. Default rebases dates so the earliest pickup is today (keeps the demo data matchable against this-week queries).",
    )
    args = parser.parse_args()
    inserted = asyncio.run(seed(skip_if_exists=args.skip_if_exists, rebase=not args.no_rebase))
    print(f"loads upserted: {inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
