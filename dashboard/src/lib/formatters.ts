// Number / time formatters shared across cards and charts.
// Currency uses USD; numbers/percent intentionally show no decimals for
// dashboard density.
import { formatDistanceToNowStrict, parseISO } from "date-fns";

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const usdWithCents = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const decimal = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const abbr = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/**
 * Accepts either a number or a string (FastAPI serializes Decimal as string).
 */
export function toNumber(value: number | string | null | undefined): number {
  if (value == null) return 0;
  if (typeof value === "number") return value;
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatCurrency(
  value: number | string | null | undefined,
  options?: { cents?: boolean },
): string {
  const n = toNumber(value);
  return options?.cents ? usdWithCents.format(n) : usd.format(n);
}

export function formatPercent(
  value: number | null | undefined,
  fractionDigits = 1,
): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(fractionDigits)}%`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "0";
  return decimal.format(value);
}

export function formatAbbrNumber(value: number | null | undefined): string {
  if (value == null) return "0";
  return abbr.format(value);
}

export function formatRelativeTime(iso: string | Date): string {
  try {
    const date = typeof iso === "string" ? parseISO(iso) : iso;
    return `${formatDistanceToNowStrict(date)} ago`;
  } catch {
    return "—";
  }
}

export function formatDelta(
  current: number,
  prior: number,
): { text: string; sign: "up" | "down" | "flat" } {
  if (!Number.isFinite(current) || !Number.isFinite(prior) || prior === 0) {
    return { text: "—", sign: "flat" };
  }
  const pct = ((current - prior) / Math.abs(prior)) * 100;
  if (Math.abs(pct) < 0.05) return { text: "0.0%", sign: "flat" };
  const sign = pct > 0 ? "up" : "down";
  return { text: `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`, sign };
}
