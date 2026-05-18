// Data adapter — MetricsResponse + recent_calls → AggView shape expected by
// the ported chart components. Pure function, easy to unit-test against a
// MetricsResponse JSON fixture.
import type { components } from "@/types/api";
import { toNumber } from "@/lib/formatters";

type Metrics = components["schemas"]["MetricsResponse"];
type RecentCall = components["schemas"]["RecentCallItem"];
type Outcome = components["schemas"]["CallOutcome"];
type Sentiment = components["schemas"]["CarrierSentiment"];

// Stable orderings used by the heatmap / lane chord components.
export const SENTIMENTS: Sentiment[] = [
  "positive",
  "neutral",
  "skeptical",
  "frustrated",
  "hostile",
];

export const OUTCOMES: Outcome[] = [
  "booked",
  "transferred_to_rep",
  "no_matching_loads",
  "carrier_declined_rate",
  "negotiation_stalled",
  "carrier_failed_vetting",
  "carrier_hung_up",
];

export type HourBucket = {
  h: number; // 0..23 in UTC
  calls: number;
  booked: number;
};

export type RoundBucket = {
  round: number;
  agreed: number;
  walked: number;
  avgDiscount: number; // 0..1
};

export type FailReason = { reason: string; count: number };

export type LaneTuple = [
  origin: string,
  destination: string,
  count: number,
  originState: string,
  destState: string,
];

export type AggView = {
  total: number;
  bookedRate: number; // 0..1
  avgSaved: number;
  avgRounds: string; // string for display ("1.2")

  // Funnel — extracted from FunnelSection.stages by canonical name
  qualified: number;
  matched: number;
  negotiated: number;
  booked: number;

  // Revenue
  avgLoadboard: number;
  avgFinal: number;
  marginPreserved: number; // already in % form (e.g. 92.4)

  // Timeseries
  hourly: HourBucket[];

  // Negotiation
  byRound: RoundBucket[];

  // Vetting
  totalFailed: number;
  failReasons: FailReason[];

  // Sentiment heatmap pivoted
  sentOut: Record<Sentiment, Record<Outcome, number>>;

  // Lanes
  laneCounts: Record<string, number>;
  LANES: LaneTuple[];

  // Underlying call list
  calls: RecentCall[];
};

const FUNNEL_NAME = {
  // FastAPI emits human-readable stage names. We accept several plausible casings/spellings.
  total: ["Total calls", "Total Calls", "total_calls"],
  qualified: ["Qualified", "Vetted", "Eligible"],
  matched: ["Matched", "Loads matched"],
  negotiated: ["Negotiated", "In Negotiation"],
  booked: ["Booked", "Booked / Transferred"],
} as const;

function findStageCount(
  stages: { name: string; count: number }[],
  candidates: readonly string[],
  fallback = 0,
): number {
  for (const c of candidates) {
    const hit = stages.find((s) => s.name === c);
    if (hit) return hit.count;
  }
  return fallback;
}

// Extracts the trailing 2-letter token from a "City, ST" string. Falls back to "??" when missing.
export function stateOf(loc: string | null | undefined): string {
  if (!loc) return "??";
  const m = loc.trim().match(/,\s*([A-Z]{2})\s*$/);
  return m ? m[1] : "??";
}

// Pivot timeseries.points → 24 hourly buckets (UTC). Points carrying the same
// UTC hour are summed; missing hours are zero-filled.
function pivotHourly(points: { bucket_start: string; calls: number; booked: number }[]): HourBucket[] {
  const hourly: HourBucket[] = Array.from({ length: 24 }, (_, h) => ({
    h,
    calls: 0,
    booked: 0,
  }));
  for (const p of points) {
    const d = new Date(p.bucket_start);
    if (Number.isNaN(d.getTime())) continue;
    const h = d.getUTCHours();
    hourly[h].calls += p.calls;
    hourly[h].booked += p.booked;
  }
  return hourly;
}

// Pivot sentiment.heatmap[] → {[sent]: {[out]: count}} with zero-fill so the
// SentimentHeatmap component can iterate without undefined checks.
function pivotSentOut(
  cells: { sentiment: Sentiment; outcome: Outcome; count: number }[],
): Record<Sentiment, Record<Outcome, number>> {
  const out = Object.fromEntries(
    SENTIMENTS.map((s) => [s, Object.fromEntries(OUTCOMES.map((o) => [o, 0]))]),
  ) as Record<Sentiment, Record<Outcome, number>>;
  for (const c of cells) {
    if (out[c.sentiment] && c.outcome in out[c.sentiment]) {
      out[c.sentiment][c.outcome] += c.count;
    }
  }
  return out;
}

export function toAggView(metrics: Metrics, callList: RecentCall[] = []): AggView {
  const stages = metrics.funnel.stages;
  const total = stages.length > 0 ? stages[0].count : metrics.kpi.calls_today;
  const qualified = findStageCount(stages, FUNNEL_NAME.qualified, total);
  const matched = findStageCount(stages, FUNNEL_NAME.matched, qualified);
  const negotiated = findStageCount(stages, FUNNEL_NAME.negotiated, matched);
  const booked = findStageCount(stages, FUNNEL_NAME.booked, 0);

  const avgLoadboard = toNumber(metrics.revenue.avg_loadboard_rate);
  const avgFinal = toNumber(metrics.revenue.avg_booked_rate);
  const marginPreserved = metrics.revenue.avg_margin_preserved_pct;
  const avgSaved = toNumber(metrics.kpi.avg_margin_saved_usd);

  const byRound: RoundBucket[] = metrics.negotiation.buckets.map((b) => ({
    round: b.round,
    agreed: b.agreed,
    walked: b.walked,
    avgDiscount: b.avg_discount_pct,
  }));

  const failReasons: FailReason[] = metrics.vetting.top_failure_reasons.map((r) => ({
    reason: typeof r.reason === "string" ? r.reason : "Unknown",
    count: typeof r.count === "number" ? r.count : Number(r.count) || 0,
  }));

  const sentOut = pivotSentOut(metrics.sentiment.heatmap);

  const laneCounts: Record<string, number> = {};
  for (const l of metrics.load_matching.top_lanes) {
    laneCounts[`${l.origin} → ${l.destination}`] = l.count;
  }

  const LANES: LaneTuple[] = metrics.load_matching.top_lanes.map((l) => [
    l.origin,
    l.destination,
    l.count,
    stateOf(l.origin),
    stateOf(l.destination),
  ]);

  return {
    total,
    bookedRate: metrics.kpi.booked_rate_pct / 100,
    avgSaved,
    avgRounds: metrics.kpi.avg_negotiation_rounds.toFixed(1),

    qualified,
    matched,
    negotiated,
    booked,

    avgLoadboard,
    avgFinal,
    marginPreserved,

    hourly: pivotHourly(metrics.timeseries.points),

    byRound,

    totalFailed: metrics.vetting.fail_count,
    failReasons,

    sentOut,

    laneCounts,
    LANES,

    calls: callList,
  };
}
