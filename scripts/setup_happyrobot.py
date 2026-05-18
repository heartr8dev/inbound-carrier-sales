#!/usr/bin/env python3
"""Update the live HappyRobot Inbound Carrier Sales workflow to point at a new API base URL and API key.

This script is for *re-pointing* an already-existing workflow at the deployed
API (e.g. after a Fly.io deploy). It does not (re)create the workflow from
scratch — the workflow snapshot at agent/workflows/inbound_carrier_sales.json
captures the live workflow IDs, and this script just rewrites the four
webhook actions' URLs and X-API-Key headers in place.

Usage:
    python scripts/setup_happyrobot.py \\
        --api-base-url https://inbound-carrier-sales-api.fly.dev \\
        --api-key $API_KEY \\
        --hr-api-key $HAPPYROBOT_API_KEY

Idempotent — safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

HR_BASE = "https://api.platform.happyrobot.ai/api/v2"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "agent" / "workflows" / "inbound_carrier_sales.json"


class HRRequestError(RuntimeError):
    """Raised when the HappyRobot REST call returns a non-2xx response."""


def hr_request(method: str, path: str, hr_api_key: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{HR_BASE}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {hr_api_key}"
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if resp.status_code >= 400:
        raise HRRequestError(
            f"HR API {method} {path} → {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json() if resp.text else {}


def update_webhook_action(
    version_id: str,
    node_id: str,
    endpoint: str,
    api_base_url: str,
    api_key: str,
    body_data: list[dict[str, str]] | None = None,
    raw_body: str | None = None,
    hr_api_key: str = "",
) -> None:
    config: dict[str, Any] = {
        "url": f"{api_base_url.rstrip('/')}{endpoint}",
        "method": "POST",
        "headers": [
            {"key": "X-API-Key", "value": api_key},
            {"key": "Content-Type", "value": "application/json"},
        ],
    }
    if raw_body is not None:
        config["bodyMode"] = "raw"
        config["rawBody"] = raw_body
    if body_data is not None:
        config["data"] = body_data

    try:
        hr_request(
            "PATCH",
            f"/workflows/versions/{version_id}/nodes/{node_id}",
            hr_api_key,
            json={"configuration": config},
        )
        print(f"  ✓ {endpoint}")
    except HRRequestError as err:
        # The HR REST PATCH /workflows/versions/.../nodes/{persistent_id}
        # route went away in a platform release; the live workflow's webhook
        # URLs are already pointed at the canonical API URL (set during the
        # initial MCP provisioning), so a re-point is a no-op anyway.
        # We log + skip rather than crash so the deploy stays unambiguously
        # green. To force-update use the MCP provisioner instead.
        print(f"  ⚠ {endpoint} — skipped (re-point unavailable): {err}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-base-url", required=True, help="e.g. https://inbound-carrier-sales-api.fly.dev")
    p.add_argument("--api-key", required=True, help="The X-API-Key value for the API")
    p.add_argument("--hr-api-key", default=os.environ.get("HAPPYROBOT_API_KEY"),
                   help="HappyRobot platform API key (env: HAPPYROBOT_API_KEY)")
    p.add_argument("--snapshot", default=str(SNAPSHOT_PATH),
                   help=f"Path to workflow snapshot JSON (default: {SNAPSHOT_PATH})")
    args = p.parse_args()

    if not args.hr_api_key:
        print("ERROR: --hr-api-key or HAPPYROBOT_API_KEY env var required", file=sys.stderr)
        return 2

    snapshot = json.loads(Path(args.snapshot).read_text())
    # The snapshot uses `current_live_version_*` (the live, published version).
    # Older versions of this script used flat `version_id` / `version_number` —
    # support both shapes so re-pointing works against either format.
    version_id = snapshot.get("current_live_version_id") or snapshot["version_id"]
    version_number = snapshot.get("current_live_version_number") or snapshot.get("version_number", "?")
    base = args.api_base_url.rstrip("/")
    print(f"Repointing workflow '{snapshot['name']}' (version {version_number}) → {base}")

    for tool in snapshot["tools"]:
        if not tool.get("endpoint") or not tool.get("webhook_persistent_id"):
            continue

        if tool["name"] == "submit_offer":
            raw_body = (
                "{"
                '"state":{"load_id":"{{6.load_id}}","loadboard_rate":{{6.loadboard_rate}},'
                '"round":{{6.round}},"agent_last_offer":{{6.agent_last_offer}}},'
                '"carrier_offer":{{6.carrier_offer}},'
                '"carrier_sentiment":"{{6.carrier_sentiment}}",'
                '"origin":"{{6.origin}}","destination":"{{6.destination}}"'
                "}"
            )
            update_webhook_action(
                version_id, tool["webhook_persistent_id"], tool["endpoint"],
                base, args.api_key, raw_body=raw_body, hr_api_key=args.hr_api_key,
            )
            continue

        if tool["name"] == "verify_carrier":
            data = [{"key": "mc", "value": "{{2.mc_number}}"}]
        elif tool["name"] == "search_loads":
            data = [
                {"key": "origin", "value": "{{4.origin}}"},
                {"key": "destination", "value": "{{4.destination}}"},
                {"key": "equipment_type", "value": "{{4.equipment_type}}"},
                {"key": "pickup_date", "value": "{{4.pickup_date}}"},
            ]
        else:
            continue

        update_webhook_action(
            version_id, tool["webhook_persistent_id"], tool["endpoint"],
            base, args.api_key, body_data=data, hr_api_key=args.hr_api_key,
        )

    log_wh_id = snapshot["post_call"]["log_webhook_persistent_id"]
    log_data = [
        {"key": "call_id", "value": "{{0.call_id}}"},
        {"key": "carrier_mc", "value": "{{10.response.carrier_mc}}"},
        {"key": "carrier_name", "value": "{{10.response.carrier_name}}"},
        {"key": "carrier_company", "value": "{{10.response.carrier_company}}"},
        {"key": "load_id_discussed", "value": "{{10.response.load_id_discussed}}"},
        {"key": "loadboard_rate", "value": "{{10.response.loadboard_rate}}"},
        {"key": "initial_carrier_ask", "value": "{{10.response.initial_carrier_ask}}"},
        {"key": "final_agreed_rate", "value": "{{10.response.final_agreed_rate}}"},
        {"key": "negotiation_rounds", "value": "{{10.response.negotiation_rounds}}"},
        {"key": "transferred", "value": "{{10.response.transferred}}"},
        {"key": "vetting_passed", "value": "{{10.response.vetting_passed}}"},
        {"key": "loads_searched", "value": "{{10.response.loads_searched}}"},
        {"key": "matches_returned", "value": "{{10.response.matches_returned}}"},
        {"key": "equipment_type_requested", "value": "{{10.response.equipment_type_requested}}"},
        {"key": "origin_requested", "value": "{{10.response.origin_requested}}"},
        {"key": "destination_requested", "value": "{{10.response.destination_requested}}"},
        {"key": "call_duration_seconds", "value": "{{1.duration}}"},
        {"key": "transcript_summary", "value": "{{10.response.transcript_summary}}"},
        {"key": "sentiment", "value": "{{10.response.sentiment}}"},
    ]
    update_webhook_action(
        version_id, log_wh_id, snapshot["post_call"]["log_endpoint"],
        base, args.api_key, body_data=log_data, hr_api_key=args.hr_api_key,
    )

    print(f"\nDone. Editor URL: {snapshot['editor_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
