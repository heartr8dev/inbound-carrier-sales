# Architecture

## System diagram

```mermaid
flowchart TB
    subgraph Carrier_Edge["Carrier edge"]
        Carrier["Carrier (driver / dispatcher)"]
        Phone["PSTN / web call"]
    end

    subgraph HappyRobot["HappyRobot platform"]
        Workflow["Inbound voice workflow<br/>(LLM + ASR + TTS)"]
        Tools["Tool calls<br/>verify_carrier / search_loads /<br/>negotiate_offer / log_call"]
    end

    subgraph App["Application — Fly.io"]
        API["FastAPI service<br/>uvicorn, Python 3.12<br/>X-API-Key middleware<br/>JSON logging via loguru"]
        subgraph Services["Service modules"]
            FMCSAsvc["fmcsa_service<br/>(SAFER client + 24h cache)"]
            LoadSvc["load_matcher<br/>(city aliases, margin sort)"]
            NegSvc["negotiation_engine<br/>(floor enforcement)"]
            ClsSvc["call_classifier<br/>(outcome + sentiment)"]
        end
        DB[("PostgreSQL 16<br/>loads / call_logs /<br/>carrier_verifications<br/>alembic-managed")]
        Dashboard["React + Vite + visx dashboard<br/>nginx static serve"]
    end

    subgraph External["External"]
        FMCSA["FMCSA SAFER<br/>mobile.fmcsa.dot.gov"]
    end

    Operator["Broker operator"]

    Carrier --> Phone --> Workflow
    Workflow --> Tools
    Tools -->|HTTPS X-API-Key| API
    API --> FMCSAsvc --> FMCSA
    API --> LoadSvc --> DB
    API --> NegSvc
    API --> ClsSvc
    API <--> DB
    Operator --> Dashboard
    Dashboard -->|GET /metrics, /calls| API
```

## Sequence: carrier verification

```mermaid
sequenceDiagram
    autonumber
    participant HR as HappyRobot agent
    participant API as FastAPI /carrier/verify
    participant DB as Postgres
    participant FMCSA as FMCSA SAFER
    HR->>API: POST /carrier/verify {mc_number}
    API->>DB: SELECT * FROM carrier_verifications WHERE mc_number=? AND verified_at > now()-interval '24 hours'
    alt cache hit
        DB-->>API: cached row
        API-->>HR: {is_eligible, legal_name, safety_rating, rejection_reason}
    else cache miss
        API->>FMCSA: GET /carriers/docket-number/{MC}?webKey=...
        FMCSA-->>API: JSON payload (authority, safety, insurance)
        API->>API: derive is_eligible<br/>(allowed_to_operate AND safety != Unsatisfactory AND authority active)
        API->>DB: UPSERT carrier_verifications (raw_response JSONB)
        DB-->>API: ok
        API-->>HR: {is_eligible, legal_name, safety_rating, rejection_reason}
    end
```

## Sequence: load search

```mermaid
sequenceDiagram
    autonumber
    participant HR as HappyRobot agent
    participant API as FastAPI /loads/search
    participant Aliases as city_aliases
    participant DB as Postgres
    HR->>API: POST /loads/search {origin, destination, equipment_type, pickup_window_days?}
    API->>Aliases: normalize("DFW") -> "Dallas"
    Aliases-->>API: normalized strings
    API->>DB: SELECT * FROM loads<br/>WHERE origin ILIKE ? AND destination ILIKE ?<br/>  AND equipment_type=? AND is_available=true<br/>  AND pickup_datetime BETWEEN now() AND now()+interval '7 days'<br/>ORDER BY (loadboard_rate / miles) DESC LIMIT 3
    DB-->>API: rows
    alt rows empty
        API-->>HR: {matches: [], suggestion: "no_matching_loads"}
    else rows present
        API-->>HR: {matches: [LoadResponse x N]}
    end
```

## Sequence: negotiation

```mermaid
sequenceDiagram
    autonumber
    participant HR as HappyRobot agent
    participant API as FastAPI /negotiate
    participant NegSvc as negotiation_engine
    participant DB as Postgres
    HR->>API: POST /negotiate {load_id, carrier_ask, round_number, agent_last_offer?}
    API->>DB: SELECT loadboard_rate FROM loads WHERE load_id=?
    DB-->>API: loadboard_rate
    API->>NegSvc: decide(loadboard_rate, ask, round, MAX_DISCOUNT_PCT)
    NegSvc->>NegSvc: floor = loadboard_rate * (1 - MAX_DISCOUNT_PCT)
    alt ask <= agent_last_offer or ask <= floor*1.02
        NegSvc-->>API: action=accept, final_rate=min(ask, agent_last_offer)
    else round >= 3
        NegSvc-->>API: action=reject (negotiation_stalled)
    else
        NegSvc->>NegSvc: counter = midpoint(agent_last_offer or loadboard_rate, ask), clamped to floor
        NegSvc-->>API: action=counter, counter_offer=...
    end
    API-->>HR: NegotiateResponse (floor never exposed)
```

## Sequence: call log + extraction

```mermaid
sequenceDiagram
    autonumber
    participant HR as HappyRobot agent
    participant API as FastAPI /calls/log
    participant Cls as call_classifier
    participant DB as Postgres
    HR->>API: POST /calls/log {call_id, mc, load_id, rates, transcript_summary, ...}
    API->>Cls: classify_outcome(transcript_summary, final_rate, rounds)
    Cls-->>API: outcome enum
    API->>Cls: classify_sentiment(transcript_summary)
    Cls-->>API: sentiment enum
    API->>DB: INSERT INTO call_logs (...) ON CONFLICT (call_id) DO UPDATE
    DB-->>API: row id
    API-->>HR: {call_log_id, outcome, sentiment}
    Note over DB: dashboard's GET /metrics<br/>aggregates over this table
```

## Why this stack

**FastAPI + SQLAlchemy 2.x (async) + Pydantic v2.** FastAPI gives us OpenAPI for free, which means the HappyRobot agent's tool schemas can be generated from the same source as the API contract; Pydantic v2 handles request validation and response shaping with zero boilerplate; SQLAlchemy 2's async API and the asyncpg driver get us real concurrent throughput on Postgres without thread-pool gymnastics. Alembic gives us reversible migrations on a single source of truth. Python is also the path of least resistance for the LLM-adjacent classifier and FMCSA-response normalisation work.

**PostgreSQL 16.** A real relational store is the right shape for this data: loads, calls, and carrier verifications all have foreign-key relationships and benefit from indexes (`equipment_type`, `pickup_datetime`, `mc_number`, `created_at`). JSONB lets us stash the raw FMCSA payload for audit without designing a new schema for every field. Fly Postgres makes provisioning a one-liner.

**React + Vite + TypeScript + visx.** Vite gives us a sub-second dev loop; TypeScript pairs with the OpenAPI client we generate from the API for end-to-end type safety. visx is Airbnb's D3-on-React — it's exactly the right primitive for a metrics dashboard that needs SVG export for slide decks, fine-grained chart customization (stacked bars, donut, sparklines), and a small bundle. Recharts would have been faster to wire up but harder to push to the level of polish we want for a customer-facing demo.

**HappyRobot.** The whole point of the exercise. The workflow editor is config-as-code, version-controlled, and audit-logged; the agent runtime handles ASR, TTS, LLM, and tool calling so we don't have to. Provisioning via the MCP server means the workflow build is reproducible from a Python script.

**Docker + Fly.io.** Compose for local parity (db + api + dashboard in one `up`). Fly for production: edge-terminated HTTPS, automatic Let's Encrypt, attached Postgres, secrets management, log streaming, and rollbacks via `flyctl releases`. One target, two services, no Kubernetes overhead.
