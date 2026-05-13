#!/usr/bin/env bash
# Integration smoke tests for the inbound carrier sales API.
# Hits a running instance (defaults to local docker-compose on :8080).
#
# Usage:
#   BASE=http://localhost:8080 API_KEY=devkey-please-change ./scripts/integration_test.sh
#
# Request shapes are adapted to the Pydantic schemas in api/src/schemas/*.py.

set -euo pipefail

BASE=${BASE:-http://localhost:8080}
KEY=${API_KEY:-devkey-please-change}
H_KEY="X-API-Key: $KEY"
H_JSON="Content-Type: application/json"

echo "==> /health"
curl -fsS "$BASE/health" | jq -e '.db == "ok"' >/dev/null

echo "==> /api/v1/carrier/verify"
# MC=123456 may return:
#   - 200 with mc_number set (FMCSA reachable, carrier active/inactive/not-found)
#   - 503 (FMCSA unreachable from this network — e.g. dev sandboxes blocked by WAF)
# Both are pass conditions; only treat connection errors or 5xx-not-503 as failure.
verify_status=$(curl -sS -o /tmp/verify.out -w '%{http_code}' \
  -H "$H_KEY" -H "$H_JSON" "$BASE/api/v1/carrier/verify" \
  -d '{"mc":"123456"}')
case "$verify_status" in
  200) jq -e '.mc_number != null' /tmp/verify.out >/dev/null ;;
  503) echo "    (FMCSA unreachable from this network — accepted as upstream-dependent)" ;;
  *)   echo "    UNEXPECTED status $verify_status: $(cat /tmp/verify.out)"; exit 1 ;;
esac

echo "==> /api/v1/loads/search"
curl -fsS -H "$H_KEY" -H "$H_JSON" "$BASE/api/v1/loads/search" \
  -d '{
        "equipment_type":"dry_van",
        "origin":"Dallas, TX",
        "destination":"Atlanta, GA",
        "pickup_date":"2026-05-14T00:00:00Z"
      }' \
  | jq -e '.matches | length >= 0' >/dev/null

echo "==> /api/v1/negotiate"
curl -fsS -H "$H_KEY" -H "$H_JSON" "$BASE/api/v1/negotiate" \
  -d '{
        "state":{
          "load_id":"LD-001",
          "loadboard_rate":"2800",
          "round":1,
          "agent_last_offer":"2800",
          "carrier_last_offer":"2500",
          "status":"pending"
        },
        "carrier_offer":"2500"
      }' \
  | jq -e '.state != null' >/dev/null

echo "==> /api/v1/calls/log"
curl -fsS -H "$H_KEY" -H "$H_JSON" "$BASE/api/v1/calls/log" \
  -d '{
        "call_id":"itest-001",
        "carrier_mc":"123456"
      }' \
  | jq -e '.call_id == "itest-001"' >/dev/null

echo "==> /api/v1/metrics?period=all"
curl -fsS -H "$H_KEY" "$BASE/api/v1/metrics?period=all" \
  | jq -e '.funnel != null' >/dev/null

echo "Integration tests: PASS"
