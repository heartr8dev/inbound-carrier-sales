"""Idempotent loader for data/seed_loads.json into the loads table."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from api.src.db import AsyncSessionLocal
from api.src.models.load import Load


REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = REPO_ROOT / "data" / "seed_loads.json"


def _coerce_row(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "load_id": raw["load_id"],
        "origin": raw["origin"],
        "destination": raw["destination"],
        "pickup_datetime": datetime.fromisoformat(raw["pickup_datetime"]),
        "delivery_datetime": datetime.fromisoformat(raw["delivery_datetime"]),
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


async def seed(skip_if_exists: bool) -> int:
    payload = json.loads(SEED_PATH.read_text())
    rows = [_coerce_row(r) for r in payload]

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
    args = parser.parse_args()
    inserted = asyncio.run(seed(skip_if_exists=args.skip_if_exists))
    print(f"loads upserted: {inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
