// Aggregates `/api/v1/calls` rows into hourly (or daily) buckets × outcome
// counts for the Streamgraph TimeSeries. The metrics endpoint only exposes
// total calls / booked per bucket, so we hit the calls listing endpoint once
// per period and roll up on the client.
//
// Granularity matches the metrics timeseries so the streamgraph aligns with
// the rest of the dashboard: "today" → hourly, "7d"/"30d"/"all" → daily.
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { components } from "@/types/api";

type CallListResponse = components["schemas"]["CallListResponse"];
type CallOutcome = components["schemas"]["CallOutcome"];
type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];

export interface OutcomeBucket {
  /** Start of the bucket (UTC). */
  t: Date;
  /** Per-outcome counts. Missing outcomes default to 0. */
  counts: Record<CallOutcome, number>;
  /** Total calls in this bucket. */
  total: number;
}

const ALL_OUTCOMES: CallOutcome[] = [
  "booked",
  "transferred_to_rep",
  "no_matching_loads",
  "carrier_declined_rate",
  "carrier_failed_vetting",
  "negotiation_stalled",
  "carrier_hung_up",
];

function emptyCounts(): Record<CallOutcome, number> {
  return ALL_OUTCOMES.reduce(
    (acc, o) => ((acc[o] = 0), acc),
    {} as Record<CallOutcome, number>,
  );
}

function periodWindow(period: MetricsPeriod): {
  from: string | undefined;
  to: string | undefined;
  hourly: boolean;
} {
  const now = new Date();
  const to = now.toISOString();
  if (period === "today") {
    const from = new Date(now);
    from.setUTCHours(0, 0, 0, 0);
    return { from: from.toISOString(), to, hourly: true };
  }
  if (period === "7d") {
    const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return { from: from.toISOString(), to, hourly: false };
  }
  if (period === "30d") {
    const from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    return { from: from.toISOString(), to, hourly: false };
  }
  return { from: undefined, to: undefined, hourly: false };
}

function bucketKey(d: Date, hourly: boolean): number {
  // Truncate to hour or day in UTC and return ms-since-epoch.
  const x = new Date(d);
  x.setUTCMinutes(0, 0, 0);
  if (!hourly) x.setUTCHours(0, 0, 0, 0);
  return x.getTime();
}

export function useOutcomesByBucket(period: MetricsPeriod) {
  // periodWindow uses Date.now for the `to` end, which drifts every render.
  // Memo by period so we don't churn the queryKey or queryFn identity on
  // every parent re-render.
  const win = useMemo(() => periodWindow(period), [period]);

  const query = useQuery<CallListResponse>({
    // Key on period only — the staleTime/refetchInterval combo handles
    // freshness; keying on `to` would loop-refetch every render.
    queryKey: ["outcomes-by-bucket", period],
    queryFn: () =>
      // Re-derive the window at fetch time so we get a current "now" for
      // each refetch rather than the one frozen at first render.
      apiGet<CallListResponse>("/calls", {
        ...((): { from?: string; to?: string } => {
          const w = periodWindow(period);
          return { from: w.from, to: w.to };
        })(),
        page_size: 500,
      }),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const buckets = useMemo<OutcomeBucket[]>(() => {
    const items = query.data?.items ?? [];
    if (items.length === 0) return [];
    const map = new Map<number, OutcomeBucket>();
    for (const c of items) {
      const t = new Date(c.created_at);
      if (Number.isNaN(t.getTime())) continue;
      const key = bucketKey(t, win.hourly);
      let entry = map.get(key);
      if (!entry) {
        entry = { t: new Date(key), counts: emptyCounts(), total: 0 };
        map.set(key, entry);
      }
      entry.counts[c.outcome] = (entry.counts[c.outcome] ?? 0) + 1;
      entry.total += 1;
    }
    return Array.from(map.values()).sort(
      (a, b) => a.t.getTime() - b.t.getTime(),
    );
  }, [query.data, win.hourly]);

  // For sparser periods, we want a continuous time axis: fill missing buckets
  // with zero rows so the streamgraph spans the whole window.
  const filled = useMemo<OutcomeBucket[]>(() => {
    if (buckets.length === 0) return buckets;
    const stepMs = win.hourly ? 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
    const first = buckets[0].t.getTime();
    const last = buckets[buckets.length - 1].t.getTime();
    const out: OutcomeBucket[] = [];
    const byKey = new Map(buckets.map((b) => [b.t.getTime(), b]));
    for (let t = first; t <= last; t += stepMs) {
      const existing = byKey.get(t);
      if (existing) out.push(existing);
      else out.push({ t: new Date(t), counts: emptyCounts(), total: 0 });
    }
    return out;
  }, [buckets, win.hourly]);

  return {
    buckets: filled,
    isLoading: query.isLoading,
    isError: query.isError,
    hourly: win.hourly,
  };
}

export { ALL_OUTCOMES };
