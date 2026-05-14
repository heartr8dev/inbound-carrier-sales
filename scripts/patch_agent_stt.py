#!/usr/bin/env python3
"""Patch the live HappyRobot agent node with STT config from agent/config.yaml.

This script captures the v2 → v3 fix where the Inbound Voice Agent was missing
a `transcriber` (so it could speak but not hear). Reading agent/config.yaml,
it applies:

  - transcriber:           id + display name
  - enable_denoised_stt:   bool
  - keyterms:              list[str] (transcriber biasing for domain terms)
  - voices, languages:     templated-value objects
  - real_time_sentiment_classifier, record, max_*: behavior knobs
  - initial_message:       greeting

The HR REST API path for arbitrary node-config edits isn't yet on the public
surface (the platform's UI and MCP server use an internal route). Until that
ships, prefer the MCP equivalent of this script (4 calls, documented inline):

    fork live version  ───>  update agent node  ───>  publish

This Python entrypoint will try the most-likely REST path first and print the
exact MCP fallback if it 404s. Idempotent — safe to re-run.

Usage:
    python scripts/patch_agent_stt.py --hr-api-key $HAPPYROBOT_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "agent" / "config.yaml"
SNAPSHOT_PATH = REPO_ROOT / "agent" / "workflows" / "inbound_carrier_sales.json"
HR_BASE = "https://api.platform.happyrobot.ai/api/v2"


def _plate_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "paragraph", "children": [{"text": text}]}]


def build_agent_config(yaml_path: Path, trigger_persistent_id: str) -> dict[str, Any]:
    cfg = yaml.safe_load(yaml_path.read_text())
    return {
        "call": {
            "type": "static",
            "static": {"id": trigger_persistent_id, "name": "Webhook Trigger"},
        },
        "agent": {
            "name": _plate_text(cfg["agent_name"]),
            "voices": [{"type": "static", "static": v} for v in cfg["voices"]],
            "languages": [{"type": "static", "static": l} for l in cfg["languages"]],
        },
        "record": cfg.get("record", True),
        "background": {
            "type": "static",
            "static": {
                "id": "https://storage.googleapis.com/happyrobot-public/backgrounds/call-center.8k.wav",
                "name": "Call center",
            },
        },
        "enable_memory": cfg.get("enable_memory", False),
        "multi_lingual": cfg.get("multi_lingual", False),
        "max_call_duration": cfg.get("max_call_duration", 600),
        "max_silence_hold_duration": cfg.get("max_silence_hold_duration", 8),
        "business_hours_setting_name": "default",
        "real_time_sentiment_classifier": cfg.get("real_time_sentiment_classifier", True),
        "transcriber": cfg["transcriber"],
        "enable_denoised_stt": cfg.get("enable_denoised_stt", True),
        "keyterms": cfg.get("keyterms", []),
    }


def print_mcp_fallback(snapshot: dict[str, Any], configuration: dict[str, Any]) -> None:
    print("\n" + "=" * 70, file=sys.stderr)
    print("HR REST endpoint not reachable. Run the MCP equivalent instead:", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(
        f"""
1. Fork the live version:
   mcp__happyrobot-workflows__manage_versions(
     version_id="{snapshot['current_live_version_id']}",
     action="fork",
   )

2. From the returned new version_id, fetch the fork's nodes:
   mcp__happyrobot-workflows__get_workflow_details(
     workflow_id="{snapshot['workflow_id']}",
     include_nodes=true,
     version_id=<new version_id>,
   )

3. Find the agent node by persistent_id == "{snapshot['agent']['persistent_id']}".
   Then update it (configuration is a FULL REPLACE):

   mcp__happyrobot-workflows__update_workflow_nodes(
     version_id=<new version_id>,
     action="update",
     node_id=<agent fork node_id>,
     updates={json.dumps({"configuration": configuration})},
   )

4. Publish the fork:
   mcp__happyrobot-workflows__manage_versions(
     version_id=<new version_id>,
     action="publish",
     environment="production",
     force=true,
   )
""",
        file=sys.stderr,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hr-api-key", default=os.environ.get("HAPPYROBOT_API_KEY"))
    p.add_argument("--snapshot", default=str(SNAPSHOT_PATH))
    p.add_argument("--config", default=str(CONFIG_PATH))
    p.add_argument("--dry-run", action="store_true", help="Print the configuration that would be sent and exit.")
    args = p.parse_args()

    snapshot = json.loads(Path(args.snapshot).read_text())
    trigger_pid = snapshot["trigger"]["persistent_id"]
    configuration = build_agent_config(Path(args.config), trigger_pid)

    if args.dry_run:
        print(json.dumps(configuration, indent=2))
        return 0

    if not args.hr_api_key:
        print("ERROR: --hr-api-key or HAPPYROBOT_API_KEY env var required", file=sys.stderr)
        return 2

    # Attempt the REST patch against the most-likely endpoint shapes. If neither
    # works we fall back to printing the MCP recipe.
    candidate_paths = [
        f"/workflows/{snapshot['workflow_id']}/versions/{snapshot['current_live_version_id']}/nodes/{snapshot['agent']['persistent_id']}",
        f"/versions/{snapshot['current_live_version_id']}/nodes/{snapshot['agent']['persistent_id']}",
    ]
    for path in candidate_paths:
        url = f"{HR_BASE}{path}"
        resp = requests.patch(
            url,
            headers={
                "Authorization": f"Bearer {args.hr_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"configuration": configuration},
            timeout=30,
        )
        if resp.status_code < 400:
            print(f"Agent node patched via {path}")
            return 0
        if resp.status_code != 404:
            print(f"PATCH {path} → {resp.status_code}: {resp.text[:200]}", file=sys.stderr)

    print_mcp_fallback(snapshot, configuration)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
