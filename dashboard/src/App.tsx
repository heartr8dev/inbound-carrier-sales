// Top-level layout for the Inbound Carrier Sales dashboard.
//
// Visual design: linen/obsidian neumorphic — see /tmp/acme-design/ for the
// reference prototype and dashboard/src/styles/ for the ported tokens.
//
// Section order (matches the design's app.jsx):
//   1. Header (brand + live pill + period pills)
//   2. KPI strip (4 tiles with sparklines)
//   3. Funnel + Revenue
//   4. CallTimeline + NegotiationChart
//   5. VettingCard + SentimentHeatmap
//   6. Anomalies
//   7. TopLanes + LaneFlow
//   8. CallsTable
//   9. CallDrawer (overlay)
//   10. TweaksPanel (floating)
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useMetrics } from "@/hooks/useMetrics";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { useCalls } from "@/hooks/useCalls";
import { useTweaks } from "@/hooks/useTweaks";
import { BrandMark } from "@/components/BrandMark";
import { KpiStrip } from "@/components/KpiStrip";
import { Funnel } from "@/components/Funnel";
import { Revenue } from "@/components/Revenue";
import { CallTimeline } from "@/components/CallTimeline";
import { NegotiationChart } from "@/components/NegotiationChart";
import { VettingCard } from "@/components/VettingCard";
import { SentimentHeatmap } from "@/components/SentimentHeatmap";
import { Anomalies } from "@/components/Anomalies";
import { TopLanes } from "@/components/TopLanes";
import { LaneFlow } from "@/components/LaneFlow";
import { CallsTable } from "@/components/CallsTable";
import { CallDrawer } from "@/components/CallDrawer";
import { TweaksPanel } from "@/components/TweaksPanel";
import { toAggView } from "@/lib/agg";
import type { components } from "@/types/api";

type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];
type Call = components["schemas"]["RecentCallItem"];

const RANGE_OPTIONS: { label: string; value: MetricsPeriod }[] = [
  { label: "Today", value: "today" },
  { label: "7d", value: "7d" },
  { label: "30d", value: "30d" },
  { label: "All", value: "all" },
];

function ThemeToggle() {
  const { tweaks, setTweak } = useTweaks();
  const isDark = tweaks.theme === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={isDark ? "Switch to Linen (light) theme" : "Switch to Obsidian (dark) theme"}
      aria-pressed={isDark}
      title={isDark ? "Linen" : "Obsidian"}
      onClick={() => setTweak("theme", isDark ? "light" : "dark")}
    >
      {isDark ? (
        // Sun — switch TO light
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      ) : (
        // Moon — switch TO dark
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

function Header({
  range,
  setRange,
  liveLabel,
}: {
  range: MetricsPeriod;
  setRange: (next: MetricsPeriod) => void;
  liveLabel: string;
}) {
  return (
    <header className="header">
      <div className="header__brand">
        <div className="brand-mark">
          <BrandMark />
        </div>
        <div className="header__title">
          <h1>Inbound Carrier Sales</h1>
          <div className="sub">Acme Logistics · Real-time operations</div>
        </div>
      </div>
      <div className="header__right">
        <div className="live">
          <span className="live__dot" />
          <span>Live · {liveLabel}</span>
        </div>
        <div className="seg" role="tablist" aria-label="Time period">
          {RANGE_OPTIONS.map((r) => (
            <button
              key={r.value}
              data-on={range === r.value}
              onClick={() => setRange(r.value)}
              type="button"
            >
              {r.label}
            </button>
          ))}
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}

export default function App() {
  const [range, setRange] = useState<MetricsPeriod>("today");
  const [activeCall, setActiveCall] = useState<Call | null>(null);
  const [tick, setTick] = useState(0);

  const queryClient = useQueryClient();
  const metricsQ = useMetrics(range);
  const callsQ = useCalls({});
  const live = useLiveEvents();

  // Bump every 15s so the "Live · X ago" label refreshes.
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 15_000);
    return () => window.clearInterval(id);
  }, []);

  const onRangeChange = (next: MetricsPeriod) => {
    setRange(next);
    queryClient.invalidateQueries({ queryKey: ["metrics"] });
  };

  // Pick the richer call list for the table + drawer.
  const fullCallList: Call[] = useMemo(() => {
    if (callsQ.data?.items?.length) return callsQ.data.items as Call[];
    return metricsQ.data?.recent_calls ?? [];
  }, [callsQ.data, metricsQ.data]);

  const agg = useMemo(() => {
    if (!metricsQ.data) return null;
    return toAggView(metricsQ.data, fullCallList);
  }, [metricsQ.data, fullCallList]);

  const liveLabel = useMemo(() => {
    void tick; // re-evaluate every tick
    if (live.state !== "open") {
      return live.state === "connecting" ? "connecting…" : "polling";
    }
    if (!live.lastEvent) return "just now";
    const ageMs = Date.now() - live.lastEvent.ts;
    if (ageMs < 4_000) return "just now";
    const secs = Math.floor(ageMs / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
  }, [live.state, live.lastEvent, tick]);

  return (
    <div className="app">
      <Header range={range} setRange={onRangeChange} liveLabel={liveLabel} />

      {agg ? (
        <>
          <KpiStrip agg={agg} period={range} />

          <div className="grid" style={{ marginBottom: "var(--s-5)" }}>
            <div className="card col-7">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Conversion funnel</h3>
                  <div className="card__sub">Inbound → vetted → matched → booked</div>
                </div>
              </div>
              <Funnel agg={agg} />
            </div>
            <div className="card col-5">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Revenue</h3>
                  <div className="card__sub">Rate negotiated vs. loadboard</div>
                </div>
              </div>
              <Revenue agg={agg} />
            </div>
          </div>

          <div className="grid" style={{ marginBottom: "var(--s-5)" }}>
            <div className="card col-7">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Call volume</h3>
                  <div className="card__sub">
                    Total calls and bookings over the selected period (UTC, hourly buckets)
                  </div>
                </div>
                <div className="legend">
                  <span className="legend__item">
                    <span className="legend__dot" style={{ background: "var(--brand)" }} /> Total calls
                  </span>
                  <span className="legend__item">
                    <span className="legend__dot" style={{ background: "var(--good)" }} /> Booked
                  </span>
                </div>
              </div>
              <CallTimeline hourly={agg.hourly} />
            </div>
            <div className="card col-5">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Negotiation performance</h3>
                  <div className="card__sub">Outcome and discount by round</div>
                </div>
                <div className="legend">
                  <span className="legend__item">
                    <span className="legend__dot" style={{ background: "var(--good)" }} /> Agreed
                  </span>
                  <span className="legend__item">
                    <span className="legend__dot" style={{ background: "var(--warn)" }} /> Walked
                  </span>
                  <span className="legend__item">
                    <span className="legend__dot" style={{ background: "var(--info)" }} /> Avg discount
                  </span>
                </div>
              </div>
              <NegotiationChart byRound={agg.byRound} />
            </div>
          </div>

          <div className="grid" style={{ marginBottom: "var(--s-5)" }}>
            <div className="card col-4">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Carrier vetting</h3>
                  <div className="card__sub">FMCSA pass rate + failure reasons</div>
                </div>
              </div>
              <VettingCard agg={agg} />
            </div>
            <div className="card col-8">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Sentiment × outcome</h3>
                  <div className="card__sub">
                    Carrier mood and how it maps to outcomes — click a cell to drill in
                  </div>
                </div>
              </div>
              <SentimentHeatmap
                sentOut={agg.sentOut}
                onCellClick={(s, o) => {
                  const match = fullCallList.find(
                    (c) => c.sentiment === s && c.outcome === o,
                  );
                  if (match) setActiveCall(match);
                }}
              />
            </div>
          </div>

          <div className="grid" style={{ marginBottom: "var(--s-5)" }}>
            <div className="card col-12">
              <div className="card__head">
                <div>
                  <h3 className="card__title">What the agent noticed today</h3>
                  <div className="card__sub">
                    Auto-detected anomalies and opportunities from the selected window
                  </div>
                </div>
              </div>
              <Anomalies agg={agg} />
            </div>
          </div>

          <div className="grid" style={{ marginBottom: "var(--s-5)" }}>
            <div className="card col-7">
              <div className="card__head">
                <div>
                  <h3 className="card__title">Top lanes by volume</h3>
                  <div className="card__sub">Where carriers are calling from and going to</div>
                </div>
              </div>
              <TopLanes laneCounts={agg.laneCounts} />
            </div>
            <div className="card col-5">
              <div className="card__head">
                <div>
                  <h3 className="card__title">State-to-state flow</h3>
                  <div className="card__sub">Top 10 lanes · width = call volume</div>
                </div>
              </div>
              <LaneFlow lanes={agg.LANES} />
            </div>
          </div>

          <CallsTable
            calls={fullCallList}
            activeId={activeCall?.call_id}
            onPick={setActiveCall}
          />
        </>
      ) : metricsQ.isLoading ? (
        <div className="card" style={{ marginTop: "var(--s-6)" }}>
          <div className="card__sub">Loading metrics…</div>
        </div>
      ) : metricsQ.isError ? (
        <div className="card" style={{ marginTop: "var(--s-6)" }}>
          <div className="card__title">Couldn&apos;t load metrics</div>
          <div className="card__sub">
            {(metricsQ.error as Error | null)?.message ?? "Unknown error"}
          </div>
        </div>
      ) : null}

      {activeCall && (
        <CallDrawer call={activeCall} onClose={() => setActiveCall(null)} />
      )}

      <TweaksPanel />
    </div>
  );
}
