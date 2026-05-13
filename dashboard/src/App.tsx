// Top-level layout for the Inbound Carrier Sales dashboard.
//
// Sections (top → bottom):
//   1. Header bar (brand + live indicator + period selector)
//   2. KPI bar (4 glass tiles with sparklines)
//   3. Two-column grid: ConversionFunnel + RevenueStrip
//      then TimeSeries + NegotiationAnalytics
//   4. Two-column grid: VettingBreakdown + SentimentChart
//   5. Full-width LoadMatching
//   6. Full-width RecentCalls
//
// The page is rendered once with a single <GradientDefs /> so every chart can
// reference any of the named gradients by `url(#…)` without re-declaring them.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PeriodSelector } from "@/components/PeriodSelector";
import { KpiBar } from "@/components/KpiBar";
import { Card } from "@/components/Card";
import { ConversionFunnel } from "@/components/ConversionFunnel";
import { TimeSeries } from "@/components/TimeSeries";
import { RevenueStrip } from "@/components/RevenueStrip";
import { NegotiationAnalytics } from "@/components/NegotiationAnalytics";
import { VettingBreakdown } from "@/components/VettingBreakdown";
import { SentimentChart } from "@/components/SentimentChart";
import { LoadMatching } from "@/components/LoadMatching";
import { RecentCalls } from "@/components/RecentCalls";
import { ChartSkeleton, Skeleton } from "@/components/Loading";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Particles } from "@/components/Particles";
import { LiveIndicator } from "@/components/LiveIndicator";
import { LiveEventToast } from "@/components/LiveEventToast";
import { useMetrics } from "@/hooks/useMetrics";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { GradientDefs } from "@/lib/gradients";
import { TruckIcon } from "@/components/icons";
import type { components } from "@/types/api";

type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];

export default function App() {
  const [period, setPeriod] = useState<MetricsPeriod>("7d");
  const queryClient = useQueryClient();
  const { data, isLoading, isFetching, isError, error } = useMetrics(period);
  // Live SSE feed (additive to the 30s polling — see useLiveEvents).
  const live = useLiveEvents();

  const onPeriodChange = (next: MetricsPeriod) => {
    setPeriod(next);
    queryClient.invalidateQueries({ queryKey: ["metrics"] });
  };

  return (
    <div className="min-h-screen text-slate-100">
      {/* Ambient drifting dots behind everything (paused for reduced motion) */}
      <Particles />
      {/* Shared SVG defs (one set of gradients for every chart) */}
      <GradientDefs />

      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-slate-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div className="flex items-center gap-3">
            <BrandMark />
            <div className="leading-tight">
              <h1 className="text-base font-semibold tracking-tight text-slate-100">
                Inbound Carrier Sales
              </h1>
              <p className="text-[11px] tracking-wide text-slate-400">
                Acme Logistics &middot; Real-time operations
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <LiveIndicator
              state={live.state}
              lastEventTs={live.lastEvent?.ts ?? null}
              eventCount={live.eventCount}
            />
            <PeriodSelector value={period} onPeriodChange={onPeriodChange} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-6 animate-fade-up">
        <div className="mb-6">
          {isLoading ? (
            <KpiBarSkeleton />
          ) : data ? (
            <KpiBar
              data={data.kpi}
              prior={null}
              loading={isFetching}
              timeseries={data.timeseries}
            />
          ) : (
            <KpiBarError message={(error as Error | null)?.message ?? null} />
          )}
        </div>

        {isError && !isLoading && (
          <div className="mb-5 rounded-xl border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">
            <p className="font-semibold">Failed to load metrics.</p>
            <p className="mt-0.5 break-words text-xs text-rose-300/80">
              {(error as Error | null)?.message}
            </p>
          </div>
        )}

        <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
          <ErrorBoundary>
            <Card
              title="Conversion Funnel"
              subtitle="Inbound → vetted → matched → booked"
              tone="warm"
            >
              {data ? (
                <ConversionFunnel data={data.funnel} />
              ) : (
                <ChartSkeleton height={340} />
              )}
            </Card>
          </ErrorBoundary>

          <ErrorBoundary>
            <Card title="Revenue" subtitle="Rate negotiated vs. loadboard" tone="cool">
              {data ? (
                <RevenueStrip data={data.revenue} />
              ) : (
                <ChartSkeleton height={260} />
              )}
            </Card>
          </ErrorBoundary>

          <ErrorBoundary>
            <Card
              title="Call Volume"
              subtitle="Total calls and bookings over time"
            >
              {data ? (
                <TimeSeries data={data.timeseries} period={period} />
              ) : (
                <ChartSkeleton height={280} />
              )}
            </Card>
          </ErrorBoundary>

          <ErrorBoundary>
            <Card
              title="Negotiation Performance"
              subtitle="Outcome and discount by round"
              tone="warm"
            >
              {data ? (
                <NegotiationAnalytics data={data.negotiation} />
              ) : (
                <ChartSkeleton height={280} />
              )}
            </Card>
          </ErrorBoundary>
        </div>

        <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
          <ErrorBoundary>
            <Card
              title="Carrier Vetting"
              subtitle="FMCSA pass rate + failure reasons"
              tone="muted"
            >
              {data ? (
                <VettingBreakdown data={data.vetting} />
              ) : (
                <ChartSkeleton height={220} />
              )}
            </Card>
          </ErrorBoundary>

          <ErrorBoundary>
            <Card
              title="Sentiment"
              subtitle="Carrier mood and how it maps to outcomes"
              tone="cool"
            >
              {data ? (
                <SentimentChart
                  data={data.sentiment}
                  period={period}
                  recentCalls={data.recent_calls}
                />
              ) : (
                <ChartSkeleton height={280} />
              )}
            </Card>
          </ErrorBoundary>
        </div>

        <div className="mb-6">
          <ErrorBoundary>
            <Card
              title="Load Matching"
              subtitle="Top lanes and equipment requested"
            >
              {data ? (
                <LoadMatching
                  data={data.load_matching}
                  recentCalls={data.recent_calls}
                />
              ) : (
                <ChartSkeleton height={220} />
              )}
            </Card>
          </ErrorBoundary>
        </div>

        <ErrorBoundary>
          <Card
            title="Recent Calls"
            subtitle="Click a row to reveal transcript summary"
            bodyClassName="p-0"
          >
            {data ? (
              <RecentCalls calls={data.recent_calls} />
            ) : (
              <div className="p-6">
                <ChartSkeleton height={200} />
              </div>
            )}
          </Card>
        </ErrorBoundary>

        <footer className="mt-10 flex flex-col items-center gap-1 text-center text-[10px] uppercase tracking-[0.16em] text-slate-600">
          <span>Inbound Carrier Sales</span>
          <span className="text-slate-700">
            Acme Logistics &middot; HappyRobot FDE submission
          </span>
        </footer>
      </main>

      {/* Live event toast — bottom right corner. */}
      <LiveEventToast events={live.recent} onDismiss={live.ackEvent} />
    </div>
  );
}

function BrandMark() {
  return (
    <div className="relative">
      <div
        className="flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-lg shadow-indigo-500/30 ring-1 ring-white/10"
        style={{
          background:
            "linear-gradient(135deg, #6366f1 0%, #06b6d4 50%, #10b981 100%)",
        }}
      >
        <TruckIcon size={20} />
      </div>
      <div className="pointer-events-none absolute inset-0 rounded-xl bg-gradient-to-tr from-white/10 to-transparent" />
    </div>
  );
}

function KpiBarSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="glass-surface rounded-2xl px-5 py-4"
        >
          <div className="flex items-start justify-between">
            <Skeleton className="h-7 w-7 rounded-lg" />
            <Skeleton className="h-4 w-12 rounded-full" />
          </div>
          <Skeleton className="mt-3 h-3 w-20" />
          <Skeleton className="mt-2 h-9 w-32" />
          <Skeleton className="mt-2 h-2 w-24" />
          <Skeleton className="mt-3 h-[44px] w-full" />
        </div>
      ))}
    </div>
  );
}

function KpiBarError({ message }: { message: string | null }) {
  return (
    <div className="rounded-2xl border border-rose-500/30 bg-rose-950/30 p-5 text-sm text-rose-200">
      <p className="font-semibold">KPIs unavailable</p>
      <p className="mt-1 text-xs text-rose-300/80">
        {message ?? "The metrics endpoint is unreachable."}
      </p>
    </div>
  );
}
