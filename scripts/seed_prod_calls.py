#!/usr/bin/env python3
"""Post a weighted random batch of demo CallLogs to the deployed API.

Mirrors `scripts/generate_mock_calls.py` (which writes directly to a local DB)
but goes through HTTP so it works against any deployed API. Useful for filling
the production dashboard with realistic shapes for a demo.

Usage:
    python scripts/seed_prod_calls.py \\
        --api-base-url https://inbound-carrier-sales-api.fly.dev \\
        --api-key      "$API_KEY" \\
        --count        250
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

OUTCOMES = [
    ("transferred_to_rep", 0.25, "positive"),
    ("booked", 0.10, "positive"),
    ("carrier_declined_rate", 0.20, "frustrated"),
    ("no_matching_loads", 0.15, "neutral"),
    ("carrier_failed_vetting", 0.15, "skeptical"),
    ("negotiation_stalled", 0.10, "frustrated"),
    ("carrier_hung_up", 0.05, "hostile"),
]
LANES = [
    ("Dallas, TX", "Atlanta, GA"),
    ("Chicago, IL", "Los Angeles, CA"),
    ("Memphis, TN", "Nashville, TN"),
    ("Phoenix, AZ", "Albuquerque, NM"),
    ("Sacramento, CA", "Reno, NV"),
    ("Tampa, FL", "Atlanta, GA"),
    ("Houston, TX", "New Orleans, LA"),
    ("Seattle, WA", "Portland, OR"),
    ("Laredo, TX", "Houston, TX"),
    ("Newark, NJ", "Boston, MA"),
]
EQUIPMENT = ["dry_van", "reefer", "flatbed", "step_deck", "power_only"]
COMPANIES = [
    "BlueLine Transport", "Lone Star Freight", "Pacific Crest Logistics",
    "Heartland Carriers", "Gulf Coast Express", "Cascade Drayage",
    "Sunbelt Trucking", "Iron Hills Trucking", "Rio Grande Cargo",
    "Three Rivers Freight", "Skyline Hauling", "Cornbelt Transport",
]


def weighted(items: list[tuple[str, float, str]]) -> tuple[str, str]:
    r = random.random()
    acc = 0.0
    for outcome, weight, sentiment in items:
        acc += weight
        if r < acc:
            return outcome, sentiment
    return items[-1][0], items[-1][2]


def random_call(now: datetime) -> dict:
    outcome, base_sentiment = weighted(OUTCOMES)
    origin, dest = random.choice(LANES)
    eq = random.choice(EQUIPMENT)
    loadboard = round(random.uniform(900, 3200), 2)
    company = random.choice(COMPANIES)
    mc = str(random.randint(100000, 999999))
    rounds = (
        random.choice([1, 2, 3]) if outcome in {"transferred_to_rep", "booked", "carrier_declined_rate"}
        else 3 if outcome == "negotiation_stalled"
        else 0
    )
    initial_ask = round(loadboard * random.uniform(0.75, 0.92), 2) if rounds else None
    final = round(loadboard * random.uniform(0.90, 0.99), 2) if outcome in {"transferred_to_rep", "booked"} else None
    # Spread over the past 7 days, weekday-business-hours weighted
    delta_hours = random.randint(0, 7 * 24)
    created = now - timedelta(hours=delta_hours)
    return {
        "call_id": f"seed-{int(created.timestamp() * 1000)}-{random.randint(1000, 9999)}",
        "carrier_mc": mc if outcome != "carrier_failed_vetting" else mc,
        "carrier_company": company,
        "load_id_discussed": f"LD-{random.randint(1, 45):03d}",
        "loadboard_rate": loadboard,
        "initial_carrier_ask": initial_ask,
        "final_agreed_rate": final,
        "negotiation_rounds": rounds,
        "transferred": outcome == "transferred_to_rep",
        "vetting_passed": outcome != "carrier_failed_vetting",
        "loads_searched": outcome != "carrier_failed_vetting",
        "matches_returned": 0 if outcome == "no_matching_loads" else random.randint(1, 3),
        "equipment_type_requested": eq,
        "origin_requested": origin,
        "destination_requested": dest,
        "call_duration_seconds": random.randint(60, 480),
        "transcript_summary": f"{company} (MC {mc}) called for a {origin}→{dest} {eq.replace('_', ' ')}; outcome: {outcome}.",
        "sentiment": base_sentiment,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-base-url", required=True)
    p.add_argument("--api-key", default=os.environ.get("API_KEY"), required=False)
    p.add_argument("--count", type=int, default=250)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--sleep-ms", type=int, default=20)
    args = p.parse_args()
    if not args.api_key:
        print("ERROR: --api-key or API_KEY env var required", file=sys.stderr)
        return 2
    if args.seed is not None:
        random.seed(args.seed)

    url = f"{args.api_base_url.rstrip('/')}/api/v1/calls/log"
    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
    now = datetime.now(timezone.utc)
    ok = fail = 0
    for i in range(args.count):
        body = random_call(now)
        try:
            r = requests.post(url, headers=headers, data=json.dumps(body), timeout=15)
            if r.status_code < 400:
                ok += 1
            else:
                fail += 1
                print(f"  fail [{r.status_code}]: {r.text[:120]}", file=sys.stderr)
        except requests.RequestException as exc:
            fail += 1
            print(f"  fail: {exc}", file=sys.stderr)
        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{args.count} (ok={ok} fail={fail})")
    print(f"\nDone. {ok} inserted, {fail} failed.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
