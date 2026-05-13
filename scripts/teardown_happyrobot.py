#!/usr/bin/env python3
"""Tear down the Inbound Carrier Sales workflow on the HappyRobot platform.

Cancels active runs, then soft-deletes the workflow. Destructive — requires --yes.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests

HR_BASE = "https://platform.happyrobot.ai/api/v2"


def hr_request(method: str, path: str, api_key: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{HR_BASE}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {api_key}"
    headers.setdefault("Accept", "application/json")
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def find_workflow(api_key: str, name: str) -> str | None:
    res = hr_request("GET", "/workflows", api_key, params={"search": name})
    for wf in res.get("data", res.get("items", [])):
        if wf.get("name") == name:
            return wf.get("id") or wf.get("slug")
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workflow-name", default="Inbound Carrier Sales")
    p.add_argument("--hr-api-key", default=os.environ.get("HAPPYROBOT_API_KEY"))
    p.add_argument("--yes", action="store_true")
    args = p.parse_args()

    if not args.hr_api_key:
        print("ERROR: --hr-api-key or HAPPYROBOT_API_KEY required", file=sys.stderr)
        return 2
    if not args.yes:
        print("Refusing to delete without --yes flag.", file=sys.stderr)
        return 2

    wf_id = find_workflow(args.hr_api_key, args.workflow_name)
    if not wf_id:
        print(f"No workflow named '{args.workflow_name}' found.")
        return 0

    print(f"Cancelling runs for workflow {wf_id}…")
    hr_request("POST", f"/workflows/{wf_id}/cancel-runs", args.hr_api_key)
    print(f"Deleting workflow {wf_id}…")
    hr_request("DELETE", f"/workflows/{wf_id}", args.hr_api_key)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
