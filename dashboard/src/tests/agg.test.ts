// Smoke tests for the MetricsResponse → AggView adapter.
// Confirms the pivot logic for timeseries, sentiment heatmap, and state codes.
import { describe, expect, it } from "vitest";
import { stateOf, toAggView } from "@/lib/agg";
import type { components } from "@/types/api";

type Metrics = components["schemas"]["MetricsResponse"];
type Call = components["schemas"]["RecentCallItem"];

function makeMetrics(overrides: Partial<Metrics> = {}): Metrics {
  return {
    period: "today",
    generated_at: "2026-05-18T20:30:00Z",
    kpi: {
      calls_today: 250,
      booked_rate_pct: 36.4,
      avg_margin_saved_usd: "68",
      avg_negotiation_rounds: 1.2,
    },
    funnel: {
      stages: [
        { name: "Total calls", count: 250, drop_off_pct: 0 },
        { name: "Qualified", count: 209, drop_off_pct: 16.4 },
        { name: "Matched", count: 138, drop_off_pct: 33.9 },
        { name: "Negotiated", count: 95, drop_off_pct: 31.2 },
        { name: "Booked", count: 91, drop_off_pct: 4.2 },
      ],
    },
    revenue: {
      avg_loadboard_rate: "2690",
      avg_booked_rate: "2530",
      avg_margin_preserved_pct: 94.1,
    },
    negotiation: {
      buckets: [
        { round: 1, agreed: 60, walked: 8, avg_discount_pct: 0.02 },
        { round: 2, agreed: 24, walked: 12, avg_discount_pct: 0.05 },
        { round: 3, agreed: 7, walked: 23, avg_discount_pct: 0.09 },
      ],
    },
    vetting: {
      pass_count: 209,
      fail_count: 41,
      top_failure_reasons: [
        { reason: "Authority not active", count: 11 },
        { reason: "Insufficient insurance", count: 9 },
      ],
    },
    sentiment: {
      distribution: [],
      heatmap: [
        { sentiment: "positive", outcome: "booked", count: 32 },
        { sentiment: "frustrated", outcome: "carrier_declined_rate", count: 7 },
      ],
    },
    load_matching: {
      top_lanes: [
        { origin: "Phoenix, AZ", destination: "Albuquerque, NM", count: 13 },
        { origin: "Dallas, TX", destination: "Atlanta, GA", count: 7 },
      ],
      equipment_demand: [],
    },
    timeseries: {
      points: [
        { bucket_start: "2026-05-18T05:00:00Z", calls: 3, booked: 1 },
        { bucket_start: "2026-05-18T05:30:00Z", calls: 2, booked: 0 },
        { bucket_start: "2026-05-18T18:00:00Z", calls: 22, booked: 9 },
      ],
    },
    recent_calls: [],
    ...overrides,
  };
}

describe("stateOf", () => {
  it("parses trailing 2-letter state codes", () => {
    expect(stateOf("Phoenix, AZ")).toBe("AZ");
    expect(stateOf("Salt Lake City, UT")).toBe("UT");
    expect(stateOf("New York City, NY")).toBe("NY");
  });
  it("returns ?? for malformed locations", () => {
    expect(stateOf(null)).toBe("??");
    expect(stateOf("")).toBe("??");
    expect(stateOf("Atlanta")).toBe("??");
  });
});

describe("toAggView", () => {
  const calls: Call[] = [];
  const agg = toAggView(makeMetrics(), calls);

  it("threads KPI fields through", () => {
    expect(agg.total).toBe(250);
    expect(agg.bookedRate).toBeCloseTo(0.364);
    expect(agg.avgSaved).toBe(68);
    expect(agg.avgRounds).toBe("1.2");
  });

  it("extracts funnel stage counts by canonical name", () => {
    expect(agg.qualified).toBe(209);
    expect(agg.matched).toBe(138);
    expect(agg.negotiated).toBe(95);
    expect(agg.booked).toBe(91);
  });

  it("pivots timeseries points into 24 hourly buckets and sums same-hour entries", () => {
    expect(agg.hourly).toHaveLength(24);
    // 05:00 + 05:30 buckets both fall in hour 5 → 3+2 = 5 calls
    expect(agg.hourly[5]).toEqual({ h: 5, calls: 5, booked: 1 });
    expect(agg.hourly[18]).toEqual({ h: 18, calls: 22, booked: 9 });
    expect(agg.hourly[0].calls).toBe(0);
  });

  it("pivots sentiment heatmap into nested object with zero-fill", () => {
    expect(agg.sentOut.positive.booked).toBe(32);
    expect(agg.sentOut.frustrated.carrier_declined_rate).toBe(7);
    expect(agg.sentOut.hostile.booked).toBe(0);
  });

  it("builds LANES tuples with derived state codes", () => {
    expect(agg.LANES[0]).toEqual([
      "Phoenix, AZ",
      "Albuquerque, NM",
      13,
      "AZ",
      "NM",
    ]);
    expect(agg.laneCounts["Phoenix, AZ → Albuquerque, NM"]).toBe(13);
  });
});
