# Deployment — Fly.io

End-to-end guide for taking the POC from a clean Fly.io account to a live deployed stack. Targets two apps (`inbound-carrier-sales-api`, `inbound-carrier-sales-dashboard`) backed by a single managed Postgres cluster.

## Prerequisites

- A Fly.io account with a verified payment method (free tier no longer covers Postgres past 14 days).
- `flyctl` installed locally and authenticated:

  ```bash
  curl -L https://fly.io/install.sh | sh
  flyctl auth login
  ```

- Repo cloned and `.env` populated (`HAPPYROBOT_API_KEY`, `FMCSA_WEBKEY`, `API_KEY`).
- Docker (for image builds before push — Fly builds remotely by default but local builds are faster).

## 1. Launch the apps (no deploy yet)

Run from the repo root for each app. `--no-deploy` writes the `fly.toml` without shipping anything yet so we can configure secrets first.

```bash
flyctl launch --no-deploy \
  --name inbound-carrier-sales-api \
  --region iad \
  --dockerfile api/Dockerfile \
  --copy-config

flyctl launch --no-deploy \
  --name inbound-carrier-sales-dashboard \
  --region iad \
  --dockerfile dashboard/Dockerfile \
  --copy-config
```

Each command writes a `fly.toml` (commit them into `api/fly.toml` and `dashboard/fly.toml` respectively). For the API set `internal_port = 8080`; for the dashboard set `internal_port = 5173` (or whichever port the nginx stage exposes).

## 2. Provision Postgres

```bash
flyctl postgres create \
  --name inbound-carrier-sales-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10
```

Attach it to the API app — this sets `DATABASE_URL` as a secret on the API:

```bash
flyctl postgres attach inbound-carrier-sales-db --app inbound-carrier-sales-api
```

The attached `DATABASE_URL` uses `postgres://` — the application code uses asyncpg, so the SQLAlchemy engine layer rewrites the scheme to `postgresql+asyncpg://` at runtime. If your `api/src/db.py` doesn't already do this, override the secret manually with the asyncpg form.

## 3. Set secrets

API app:

```bash
flyctl secrets set --app inbound-carrier-sales-api \
  HAPPYROBOT_API_KEY="sk_live_..." \
  FMCSA_WEBKEY="cdc33e44..." \
  API_KEY="<32-char-random-token>" \
  DASHBOARD_ORIGIN="https://inbound-carrier-sales-dashboard.fly.dev" \
  MAX_DISCOUNT_PCT="0.10"
```

Dashboard app (the dashboard image is built with the API base URL baked in at build time via `VITE_API_BASE_URL` — set it as a build arg in `fly.toml` or pass it on deploy):

```bash
flyctl secrets set --app inbound-carrier-sales-dashboard \
  VITE_API_BASE_URL="https://inbound-carrier-sales-api.fly.dev" \
  VITE_API_KEY="<same API_KEY as above>"
```

## 4. First deploy

```bash
flyctl deploy --app inbound-carrier-sales-api --config api/fly.toml
flyctl deploy --app inbound-carrier-sales-dashboard --config dashboard/fly.toml
```

Confirm both are healthy:

```bash
flyctl status --app inbound-carrier-sales-api
flyctl status --app inbound-carrier-sales-dashboard
curl https://inbound-carrier-sales-api.fly.dev/health
```

## 5. Run migrations on prod

```bash
flyctl ssh console --app inbound-carrier-sales-api \
  -C "sh -c 'cd /app && alembic -c api/alembic.ini upgrade head'"
```

Verify the schema landed:

```bash
flyctl postgres connect --app inbound-carrier-sales-db \
  -C "\dt"
```

## 6. Seed loads on prod

```bash
flyctl ssh console --app inbound-carrier-sales-api \
  -C "sh -c 'cd /app && python scripts/seed_db.py'"
```

## 7. Re-point the HappyRobot agent at production

The agent's tool nodes hold the API base URL. Re-run the provisioning script with the prod URL — the script is idempotent (looks up the workflow by slug and updates rather than recreates):

```bash
python scripts/setup_happyrobot.py \
  --api-base-url=https://inbound-carrier-sales-api.fly.dev
```

Place a test web call from the HappyRobot editor and confirm the call lands in the dashboard.

## 8. Troubleshooting

- **Cold starts.** Default Fly app config has `auto_stop_machines = true`. A cold start adds ~3-5 seconds to the first request. For a customer demo, set `min_machines_running = 1` on both apps in `fly.toml` to keep one instance warm.
- **Scaling.** Horizontal: `flyctl scale count 2 --app inbound-carrier-sales-api`. Vertical: `flyctl scale vm shared-cpu-2x --app inbound-carrier-sales-api`.
- **Logs.** Tail live: `flyctl logs --app inbound-carrier-sales-api`. The API emits structured JSON via loguru, one line per request with `request_id`, `path`, `status`, `duration_ms`.
- **Rollback.** `flyctl releases --app inbound-carrier-sales-api` lists every release with its image tag; `flyctl releases rollback <version> --app inbound-carrier-sales-api` ships the previous release.
- **DB outage.** `/health` returns `{"db": "down"}` on Postgres connectivity failure. Check `flyctl postgres list` and `flyctl status --app inbound-carrier-sales-db`. The carrier verification cache cushions short outages — `/loads/search` is the first thing that fails when Postgres goes hard down.
- **FMCSA outage.** The 24h cache on `carrier_verifications` keeps repeat callers working; first-time vetting fails closed (logged as `carrier_failed_vetting` with `rejection_reason="fmcsa_unavailable"`). Monitor the `fmcsa_service` logs for `httpx.HTTPStatusError`.
- **Secrets rotation.** `flyctl secrets set` triggers an immediate redeploy. To rotate `API_KEY`, set on the API and dashboard in the same minute — there will be a ~60s window of 401s otherwise.
