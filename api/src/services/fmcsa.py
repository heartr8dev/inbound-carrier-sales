"""FMCSA QCMobile API client + carrier eligibility logic + 24h cache + circuit breaker.

This module is the only place in the codebase that talks to
`mobile.fmcsa.dot.gov`. Field names in the FMCSA response are pinned as
constants at the top of this file and documented in
`docs/fmcsa_response_schema.md`.

Behavior summary:
- `FMCSAClient.lookup_by_mc(mc, db)` performs a cached lookup, calling the
  FMCSA endpoint only on cache miss (cache TTL configurable, default 24h).
- `evaluate_eligibility(carrier_json)` implements the policy rules from the
  Workstream A plan (and from `docs/fmcsa_response_schema.md`).
- An in-process circuit breaker fronts the live HTTP call: 5 consecutive
  failures within a 60-second window opens the circuit for 60 seconds. While
  open, `lookup_by_mc` short-circuits and returns `is_eligible=None` with
  `rejection_reason="fmcsa_unavailable"` (no DB write).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.config import settings
from api.src.models.carrier import CarrierVerification

# ---------------------------------------------------------------------------
# FMCSA response field-name constants (pinned — see docs/fmcsa_response_schema.md)
# ---------------------------------------------------------------------------

FMCSA_BASE_URL = "https://mobile.fmcsa.dot.gov/qc/services/carriers/docket-number"

# Envelope keys
FIELD_CONTENT = "content"
FIELD_RETRIEVAL_DATE = "retrievalDate"

# CarrierDetails wrapper
FIELD_CARRIER = "carrier"

# Carrier fields
F_ALLOWED_TO_OPERATE = "allowedToOperate"
F_STATUS_CODE = "statusCode"
F_LEGAL_NAME = "legalName"
F_DBA_NAME = "dbaName"
F_DOT_NUMBER = "dotNumber"
F_SAFETY_RATING = "safetyRating"
F_OOS_DATE = "oosDate"
F_BIPD_ON_FILE = "bipdInsuranceOnFile"
F_CARGO_ON_FILE = "cargoInsuranceOnFile"
F_COMMON_AUTHORITY = "commonAuthorityStatus"
F_CONTRACT_AUTHORITY = "contractAuthorityStatus"
F_BROKER_AUTHORITY = "brokerAuthorityStatus"
F_CARRIER_OPERATION = "carrierOperation"
F_CARRIER_OPERATION_DESC = "carrierOperationDesc"

# FMCSA status code values
STATUS_ACTIVE = "A"
STATUS_INACTIVE = "I"

# FMCSA safety rating values
SAFETY_SATISFACTORY = "S"
SAFETY_CONDITIONAL = "C"
SAFETY_UNSATISFACTORY = "U"

_SAFETY_RATING_LABELS: dict[str, str] = {
    SAFETY_SATISFACTORY: "Satisfactory",
    SAFETY_CONDITIONAL: "Conditional",
    SAFETY_UNSATISFACTORY: "Unsatisfactory",
}

# Sentinel returned when the FMCSA maintenance HTML page is detected.
_MAINTENANCE_SENTINEL = b"<title>FMCSA System Maintenance Page</title>"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FMCSAError(Exception):
    """Base for FMCSA service errors."""


class FMCSANotFound(FMCSAError):
    """The MC docket number is not in the FMCSA database."""


class FMCSAUnavailable(FMCSAError):
    """FMCSA upstream is unavailable (timeout, 5xx, maintenance, bad webkey)."""


class FMCSACircuitOpen(FMCSAError):
    """The local circuit breaker is open; we did not call FMCSA."""


# ---------------------------------------------------------------------------
# Circuit breaker (module-level singleton, in-process state)
# ---------------------------------------------------------------------------


@dataclass
class _CircuitBreaker:
    """Simple closed/open circuit breaker with sliding-window failure count.

    State machine:
      - closed: requests pass through. Each failure is appended to `_failures`
        (a list of monotonic timestamps). Failures outside the
        `window_seconds` are discarded on every check. When the count inside
        the window reaches `fail_threshold`, the circuit opens.
      - open: requests are short-circuited. After `open_seconds` the circuit
        transitions back to closed and the failure log is cleared.

    We do NOT model a half-open probe state — the next request after the open
    window expires is the probe; if it fails we open again immediately.
    """

    fail_threshold: int
    window_seconds: float
    open_seconds: float
    _failures: list[float] = field(default_factory=list)
    _opened_at: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _now(self) -> float:
        return time.monotonic()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        # In-place filter for low GC churn.
        self._failures[:] = [t for t in self._failures if t >= cutoff]

    async def check_open(self) -> bool:
        """Returns True if the circuit is currently open (callers should short-circuit)."""
        async with self._lock:
            now = self._now()
            if self._opened_at is not None:
                if now - self._opened_at >= self.open_seconds:
                    logger.bind(component="fmcsa.circuit").info(
                        "circuit closing after open window elapsed"
                    )
                    self._opened_at = None
                    self._failures.clear()
                    return False
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            # On any success we wipe the failure log; this prevents stale
            # failures from accumulating to threshold across long periods.
            if self._failures:
                self._failures.clear()

    async def record_failure(self) -> None:
        async with self._lock:
            now = self._now()
            self._prune(now)
            self._failures.append(now)
            if self._opened_at is None and len(self._failures) >= self.fail_threshold:
                self._opened_at = now
                logger.bind(component="fmcsa.circuit").warning(
                    "circuit OPENED after {} failures in {}s window; will retry after {}s",
                    len(self._failures),
                    self.window_seconds,
                    self.open_seconds,
                )

    # Test / introspection helpers
    def reset(self) -> None:
        self._failures.clear()
        self._opened_at = None

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None


_circuit = _CircuitBreaker(
    fail_threshold=settings.FMCSA_CIRCUIT_FAIL_THRESHOLD,
    window_seconds=settings.FMCSA_CIRCUIT_WINDOW_SECONDS,
    open_seconds=settings.FMCSA_CIRCUIT_OPEN_SECONDS,
)


def get_circuit_breaker() -> _CircuitBreaker:
    """Accessor for tests to reset / inspect the module-level circuit breaker."""
    return _circuit


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_decimal_thousands(raw: Any) -> Decimal | None:
    """FMCSA reports insurance amounts as strings in thousands of USD.

    e.g. "1000" => $1,000,000. "0" or "" => None (no coverage on file).
    """
    if raw is None:
        return None
    try:
        s = str(raw).strip()
        if not s:
            return None
        val = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if val <= 0:
        return None
    return val * Decimal(1000)


def _parse_oos_date(raw: Any) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _derive_authority_type(carrier: dict[str, Any]) -> str:
    """Pick the broadest active authority bucket. Falls back to 'none'."""
    if carrier.get(F_COMMON_AUTHORITY) == STATUS_ACTIVE:
        return "common"
    if carrier.get(F_CONTRACT_AUTHORITY) == STATUS_ACTIVE:
        return "contract"
    if carrier.get(F_BROKER_AUTHORITY) == STATUS_ACTIVE:
        return "broker"
    return "none"


def _derive_operating_status(carrier: dict[str, Any]) -> str:
    """Synthesize a human-readable operating_status.

    If the carrier is not allowed to operate we emit the literal
    "NOT AUTHORIZED" so the substring check in `evaluate_eligibility` fires
    even when the upstream `carrierOperationDesc` is set (e.g. "Interstate"
    can legitimately appear on a carrier whose authority is revoked).
    """
    if str(carrier.get(F_ALLOWED_TO_OPERATE, "")).upper() != "Y":
        return "NOT AUTHORIZED"
    op = carrier.get(F_CARRIER_OPERATION) or {}
    desc = op.get(F_CARRIER_OPERATION_DESC) if isinstance(op, dict) else None
    return str(desc) if desc else "AUTHORIZED"


def _map_safety_rating(raw: Any) -> str | None:
    if raw is None:
        return None
    code = str(raw).strip().upper()
    return _SAFETY_RATING_LABELS.get(code, code or None)


# ---------------------------------------------------------------------------
# Eligibility policy
# ---------------------------------------------------------------------------


def evaluate_eligibility(
    carrier: dict[str, Any], today: date | None = None
) -> tuple[bool, str | None]:
    """Apply the policy rules in `docs/fmcsa_response_schema.md`.

    Args:
        carrier: The `carrier` sub-object from the FMCSA payload (NOT the
            outer envelope).
        today: Optional date override for testability of the OOS rule.

    Returns:
        `(is_eligible, rejection_reason)`. `rejection_reason` is `None` when
        the carrier passes cleanly. It is `"conditional_safety_rating"` when
        the carrier passes with a warning.
    """
    today = today or datetime.now(timezone.utc).date()

    if str(carrier.get(F_ALLOWED_TO_OPERATE, "")).upper() != "Y":
        return False, "not_allowed_to_operate"

    status_code = str(carrier.get(F_STATUS_CODE, "")).upper()
    operating_status = _derive_operating_status(carrier)
    if status_code == STATUS_INACTIVE or "NOT AUTHORIZED" in operating_status.upper():
        return False, "inactive_or_not_authorized"

    oos_date = _parse_oos_date(carrier.get(F_OOS_DATE))
    if oos_date is not None and oos_date <= today:
        return False, "out_of_service"

    rating_label = _map_safety_rating(carrier.get(F_SAFETY_RATING))
    if rating_label == "Unsatisfactory":
        return False, "unsatisfactory_safety_rating"
    if rating_label == "Conditional":
        return True, "conditional_safety_rating"

    return True, None


# ---------------------------------------------------------------------------
# FMCSA client
# ---------------------------------------------------------------------------


@dataclass
class _LookupResult:
    """Internal struct used to communicate a successful lookup to callers."""

    row: CarrierVerification | None  # None iff the circuit was open
    cached: bool
    circuit_open: bool = False


class FMCSAClient:
    """Async client for the FMCSA QCMobile docket-number endpoint.

    Wraps `httpx.AsyncClient` (one client per instance — callers should treat
    this as a request-scoped resource OR a long-lived singleton; both work).
    """

    def __init__(
        self,
        *,
        webkey: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
        cache_ttl: timedelta | None = None,
    ) -> None:
        self._webkey = webkey if webkey is not None else settings.FMCSA_WEBKEY
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.FMCSA_TIMEOUT_SECONDS
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=self._timeout)
        self._cache_ttl = cache_ttl or timedelta(hours=settings.FMCSA_CACHE_TTL_HOURS)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "FMCSAClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    # ---- Public API -----------------------------------------------------

    async def lookup_by_mc(
        self,
        mc: str,
        db: AsyncSession,
    ) -> _LookupResult:
        """Cache-aware lookup.

        Order of operations:
          1. Check the local cache (`CarrierVerification` row by `mc_number`).
             If present and fresh, return it.
          2. Check the circuit breaker. If open, return `_LookupResult(row=None, circuit_open=True)`.
          3. Fetch the live FMCSA payload (raises on timeout/5xx/maintenance).
          4. Parse + evaluate eligibility.
          5. Upsert the row and return it.
        """
        log = logger.bind(component="fmcsa", mc=mc)

        cached_row = await self._read_cache(db, mc)
        if cached_row is not None and self._is_fresh(cached_row):
            log.debug("cache hit (fresh)")
            return _LookupResult(row=cached_row, cached=True)

        if await _circuit.check_open():
            log.warning("circuit open — returning fmcsa_unavailable without DB write")
            return _LookupResult(row=None, cached=False, circuit_open=True)

        try:
            payload = await self._fetch_live(mc)
        except FMCSAUnavailable:
            await _circuit.record_failure()
            raise
        except FMCSANotFound:
            # 404 / empty content is a normal business outcome, not an upstream
            # failure. Don't count against the circuit breaker.
            await _circuit.record_success()
            raise
        else:
            await _circuit.record_success()

        carrier_json = self._extract_carrier(payload)
        row = await self._upsert(db, mc=mc, payload=payload, carrier=carrier_json)
        return _LookupResult(row=row, cached=False)

    # ---- Cache ----------------------------------------------------------

    async def _read_cache(
        self, db: AsyncSession, mc: str
    ) -> CarrierVerification | None:
        result = await db.execute(
            select(CarrierVerification).where(CarrierVerification.mc_number == mc)
        )
        return result.scalar_one_or_none()

    def _is_fresh(self, row: CarrierVerification) -> bool:
        verified_at = row.verified_at
        if verified_at is None:
            return False
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - verified_at < self._cache_ttl

    # ---- HTTP -----------------------------------------------------------

    async def _fetch_live(self, mc: str) -> dict[str, Any]:
        url = f"{FMCSA_BASE_URL}/{mc}"
        params = {"webKey": self._webkey}
        log = logger.bind(component="fmcsa.http", mc=mc)
        try:
            response = await self._client.get(url, params=params)
        except httpx.TimeoutException as exc:
            log.warning("timeout calling FMCSA: {!r}", exc)
            raise FMCSAUnavailable("fmcsa_timeout") from exc
        except httpx.HTTPError as exc:
            log.warning("transport error calling FMCSA: {!r}", exc)
            raise FMCSAUnavailable("fmcsa_transport_error") from exc

        # Maintenance page comes back as 200 with HTML.
        if _MAINTENANCE_SENTINEL in response.content:
            log.warning("FMCSA returned maintenance HTML page")
            raise FMCSAUnavailable("fmcsa_maintenance")

        if response.status_code >= 500:
            log.warning("FMCSA 5xx status={}", response.status_code)
            raise FMCSAUnavailable(f"fmcsa_5xx_{response.status_code}")

        # 4xx — distinguish "MC not in DB" from "bad webkey" by inspecting body.
        if response.status_code == 404:
            body = self._safe_json(response)
            content = body.get(FIELD_CONTENT) if isinstance(body, dict) else None
            if isinstance(content, str):
                # webkey or other config error masquerading as 404
                log.error("FMCSA 404 with config error: {}", content)
                raise FMCSAUnavailable(f"fmcsa_config_error:{content}")
            raise FMCSANotFound("mc_not_found")

        if response.status_code >= 400:
            log.warning("FMCSA unexpected 4xx status={}", response.status_code)
            raise FMCSAUnavailable(f"fmcsa_4xx_{response.status_code}")

        payload = self._safe_json(response)
        if not isinstance(payload, dict):
            raise FMCSAUnavailable("fmcsa_malformed_response")

        content = payload.get(FIELD_CONTENT)
        # Empty array => MC not found (treated as 200 + empty content by FMCSA).
        if isinstance(content, list) and len(content) == 0:
            raise FMCSANotFound("mc_not_found")
        # Webkey error returned with 200 + string content.
        if isinstance(content, str):
            log.error("FMCSA 200 with string content (config error): {}", content)
            raise FMCSAUnavailable(f"fmcsa_config_error:{content}")

        return payload

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    # ---- Parsing --------------------------------------------------------

    @staticmethod
    def _extract_carrier(payload: dict[str, Any]) -> dict[str, Any]:
        """Pull the first carrier object out of the envelope.

        The docket-number endpoint always returns a list; we take the first
        entry. If for some reason the upstream changes to a single-object
        envelope (as the by-DOT endpoint does), we handle that too.
        """
        content = payload.get(FIELD_CONTENT)
        details: dict[str, Any] | None
        if isinstance(content, list):
            if not content:
                raise FMCSANotFound("mc_not_found")
            first = content[0]
            details = first if isinstance(first, dict) else None
        elif isinstance(content, dict):
            details = content
        else:
            details = None

        if not details:
            raise FMCSAUnavailable("fmcsa_malformed_response")

        carrier = details.get(FIELD_CARRIER)
        if not isinstance(carrier, dict):
            raise FMCSAUnavailable("fmcsa_malformed_response")
        return carrier

    # ---- DB upsert ------------------------------------------------------

    async def _upsert(
        self,
        db: AsyncSession,
        *,
        mc: str,
        payload: dict[str, Any],
        carrier: dict[str, Any],
    ) -> CarrierVerification:
        is_eligible, reason = evaluate_eligibility(carrier)
        values: dict[str, Any] = {
            "mc_number": mc,
            "legal_name": str(carrier.get(F_LEGAL_NAME) or "Unknown"),
            "dba_name": carrier.get(F_DBA_NAME),
            "operating_status": _derive_operating_status(carrier),
            "authority_type": _derive_authority_type(carrier),
            "allowed_to_operate": str(carrier.get(F_ALLOWED_TO_OPERATE, "")).upper()
            == "Y",
            "safety_rating": _map_safety_rating(carrier.get(F_SAFETY_RATING)),
            "insurance_bipd_on_file": _parse_decimal_thousands(
                carrier.get(F_BIPD_ON_FILE)
            ),
            "insurance_cargo_on_file": _parse_decimal_thousands(
                carrier.get(F_CARGO_ON_FILE)
            ),
            "is_eligible": is_eligible,
            "rejection_reason": reason,
            "raw_response": payload,
            "verified_at": datetime.now(timezone.utc),
        }

        stmt = pg_insert(CarrierVerification).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "mc_number"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[CarrierVerification.mc_number],
            set_=update_cols,
        ).returning(CarrierVerification)

        result = await db.execute(stmt)
        row = result.scalar_one()
        await db.commit()
        await db.refresh(row)
        return row
