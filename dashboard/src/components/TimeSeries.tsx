// Streamgraph of call outcomes over time with a Voronoi overlay for
// pixel-perfect cursor lookup.
//
// Visual recipe:
//   * `@visx/shape` `Stack` configured with `silhouette` offset (wiggle-style
//     symmetric flow) and `insideout` order. Renders 7 layers — one per
//     CallOutcome — using `curveBasis` so the silhouette ripples like aurora
//     rather than a stack of bars.
//   * Each layer fills with a vertical outcome gradient (declared inline in
//     this file so the streamgraph owns its own palette). A 1px stroke in a
//     darker tone of the same hue carves a ~1px gap between bands.
//   * A subtle SVG Gaussian blur filter (`feGaussianBlur stdDeviation="0.5"`)
//     softens hard edges into a glow.
//
// Interaction (the showstopper):
//   * A `voronoi` layout is built from one synthetic point per (bucket × outcome).
//     `find(x, y, 60)` returns the nearest stack point under the cursor.
//   * The matched outcome becomes the "active" layer — held at 100% opacity
//     while every other layer is interpolated down to 30% via CSS transition.
//   * A vertical crosshair snaps to the bucket; a glass tooltip lists every
//     outcome's count at that bucket with its gradient swatch.
//
// The metrics endpoint only ships aggregate (calls/booked) per bucket, so
// the underlying data is pulled from /api/v1/calls and rolled up by
// `useOutcomesByBucket`.
import { useMemo, useCallback, useState, useId } from "react";
import { Group } from "@visx/group";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { ParentSize } from "@visx/responsive";
import { curveBasis } from "@visx/curve";
import { useTooltip, useTooltipInPortal } from "@visx/tooltip";
import { localPoint } from "@visx/event";
import { voronoi } from "@visx/voronoi";
import {
  stack as d3stack,
  stackOffsetSilhouette,
  stackOffsetNone,
  stackOrderInsideOut,
  area as d3area,
} from "d3-shape";
import { format as formatDate } from "date-fns";
import { timeFormat } from "d3-time-format";
import type { components } from "@/types/api";
import { theme } from "@/lib/theme";
import { EmptyState } from "@/components/Loading";
import { ChartTooltip, TooltipHeader } from "@/components/Tooltip";
import { formatNumber } from "@/lib/formatters";
import { outcomeLabels } from "@/lib/theme";
import { useOutcomesByBucket } from "@/hooks/useOutcomesByBucket";

type TimeseriesSection = components["schemas"]["TimeseriesSection"];
type CallOutcome = components["schemas"]["CallOutcome"];
type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];

interface TimeSeriesProps {
  data: TimeseriesSection;
  period: MetricsPeriod;
  height?: number;
}

// Order matters: positive outcomes drift to the top via stackOrderInsideOut,
// but we render legend pills + tooltip rows in this canonical sequence.
const OUTCOME_ORDER: CallOutcome[] = [
  "booked",
  "transferred_to_rep",
  "carrier_declined_rate",
  "negotiation_stalled",
  "no_matching_loads",
  "carrier_failed_vetting",
  "carrier_hung_up",
];

// Per-outcome two-stop palette (top→bottom). Each band uses its own
// `<linearGradient>` declared inside the SVG so the stream owns its colors.
const OUTCOME_PALETTE: Record<CallOutcome, { from: string; to: string; line: string }> = {
  booked: { from: "#34d399", to: "#0d9488", line: "#064e3b" },
  transferred_to_rep: { from: "#5eead4", to: "#14b8a6", line: "#0f766e" },
  carrier_declined_rate: { from: "#fbbf24", to: "#ea580c", line: "#9a3412" },
  negotiation_stalled: { from: "#f0abfc", to: "#db2777", line: "#831843" },
  no_matching_loads: { from: "#94a3b8", to: "#334155", line: "#1e293b" },
  carrier_failed_vetting: { from: "#fb7185", to: "#e11d48", line: "#881337" },
  carrier_hung_up: { from: "#cbd5e1", to: "#475569", line: "#0f172a" },
};

interface VoronoiPoint {
  outcome: CallOutcome;
  bucketIdx: number;
  x: number;
  y: number;
  value: number;
}

interface StackedPoint {
  t: Date;
  total: number;
  byOutcome: Record<CallOutcome, number>;
}

export function TimeSeries({ data, period, height = 320 }: TimeSeriesProps) {
  const { buckets } = useOutcomesByBucket(period);

  // If the calls listing hasn't returned (or returned empty), fall back to the
  // metrics-derived calls-by-bucket as a single "neutral" stack — keeps the
  // chart non-empty while still respecting the streamgraph aesthetic.
  const rows = useMemo<StackedPoint[]>(() => {
    if (buckets.length > 0) {
      return buckets.map((b) => ({
        t: b.t,
        total: b.total,
        byOutcome: b.counts as Record<CallOutcome, number>,
      }));
    }
    return (data.points ?? []).map((p) => ({
      t: new Date(p.bucket_start),
      total: p.calls,
      byOutcome: {
        booked: p.booked,
        transferred_to_rep: 0,
        no_matching_loads: Math.max(0, p.calls - p.booked),
        carrier_declined_rate: 0,
        carrier_failed_vetting: 0,
        negotiation_stalled: 0,
        carrier_hung_up: 0,
      },
    }));
  }, [buckets, data.points]);

  const granularity = useMemo<"hour" | "day">(() => {
    if (rows.length < 2) return "day";
    const diff = rows[1].t.getTime() - rows[0].t.getTime();
    return diff < 6 * 60 * 60 * 1000 ? "hour" : "day";
  }, [rows]);

  const tickFormatter = useMemo(
    () =>
      timeFormat(granularity === "hour" ? "%H:%M" : "%b %d") as unknown as (
        v: Date,
      ) => string,
    [granularity],
  );

  // Totals per outcome — drives the legend chip ordering by volume.
  const totals = useMemo(() => {
    const t = {} as Record<CallOutcome, number>;
    for (const o of OUTCOME_ORDER) t[o] = 0;
    for (const r of rows) {
      for (const o of OUTCOME_ORDER) t[o] += r.byOutcome[o] ?? 0;
    }
    return t;
  }, [rows]);

  if (rows.length === 0) {
    return <EmptyState title="No timeseries data yet" />;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
        {OUTCOME_ORDER.filter((o) => totals[o] > 0).map((o) => (
          <span
            key={o}
            className="flex items-center gap-1.5 rounded-full border border-white/[0.06] bg-white/[0.02] px-2 py-0.5"
          >
            <span
              aria-hidden
              className="h-2 w-3 rounded-sm"
              style={{
                background: `linear-gradient(135deg,${OUTCOME_PALETTE[o].from},${OUTCOME_PALETTE[o].to})`,
                boxShadow: `0 0 6px ${OUTCOME_PALETTE[o].to}66`,
              }}
            />
            <span className="text-[10px] uppercase tracking-[0.08em] text-slate-400">
              {outcomeLabels[o]}
            </span>
            <span className="num-mono text-[11px] text-slate-100">
              {formatNumber(totals[o])}
            </span>
          </span>
        ))}
      </div>
      <div style={{ width: "100%", height }}>
        <ParentSize>
          {({ width, height: h }) => (
            <StreamInner
              width={width}
              height={h}
              rows={rows}
              tickFormatter={tickFormatter}
            />
          )}
        </ParentSize>
      </div>
    </div>
  );
}

interface InnerProps {
  width: number;
  height: number;
  rows: StackedPoint[];
  tickFormatter: (v: Date) => string;
}

interface TooltipPayload {
  bucketIdx: number;
  activeOutcome: CallOutcome | null;
  x: number;
  y: number;
}

function StreamInner({ width, height: h, rows, tickFormatter }: InnerProps) {
  const filterId = useId();
  const gradPrefix = useId().replace(/[:]/g, "");
  const margin = { top: 18, right: 18, bottom: 30, left: 36 };
  const innerW = Math.max(0, width - margin.left - margin.right);
  const innerH = Math.max(0, h - margin.top - margin.bottom);

  const [activeOutcome, setActiveOutcome] = useState<CallOutcome | null>(null);

  const {
    showTooltip,
    hideTooltip,
    tooltipData,
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
  } = useTooltip<TooltipPayload>();
  const { containerRef, TooltipInPortal } = useTooltipInPortal({
    detectBounds: true,
    scroll: true,
  });

  // Build the silhouette stack. We toggle to `stackOffsetNone` (anchored to 0)
  // when total is tiny so we don't get a degenerate ribbon — silhouette mode
  // looks great once there's > ~5 rows of meaningful data.
  const useSilhouette = rows.length >= 3;
  const stacked = useMemo(() => {
    const stacker = d3stack<StackedPoint, CallOutcome>()
      .keys(OUTCOME_ORDER)
      .value((d, key) => d.byOutcome[key] ?? 0)
      .order(stackOrderInsideOut)
      .offset(useSilhouette ? stackOffsetSilhouette : stackOffsetNone);
    return stacker(rows);
  }, [rows, useSilhouette]);

  const xMin = rows[0]?.t.getTime() ?? 0;
  const xMax = rows[rows.length - 1]?.t.getTime() ?? 0;
  const xScale = useMemo(
    () =>
      scaleTime<number>({
        domain: [new Date(xMin), new Date(xMax)],
        range: [0, innerW],
      }),
    [xMin, xMax, innerW],
  );

  // yScale — silhouette puts the stack on a symmetric domain. Compute min/max
  // across every layer so the ribbon fits comfortably.
  const yDomain = useMemo<[number, number]>(() => {
    let lo = 0;
    let hi = 0;
    for (const layer of stacked) {
      for (const pt of layer) {
        if (pt[0] < lo) lo = pt[0];
        if (pt[1] > hi) hi = pt[1];
      }
    }
    if (lo === 0 && hi === 0) {
      lo = -1;
      hi = 1;
    }
    return [lo, hi];
  }, [stacked]);

  const [yLo, yHi] = yDomain;
  const yScale = useMemo(
    () =>
      scaleLinear<number>({
        domain: [yLo, yHi],
        range: [innerH, 0],
        nice: false,
      }),
    [yLo, yHi, innerH],
  );

  // d3 area generator for each stacked layer.
  const areaGen = useMemo(
    () =>
      d3area<{ data: StackedPoint; 0: number; 1: number }>()
        .x((d) => xScale(d.data.t))
        .y0((d) => yScale(d[0]))
        .y1((d) => yScale(d[1]))
        .curve(curveBasis),
    [xScale, yScale],
  );

  // Voronoi points — one per (bucket × outcome) at the *centerline* of that
  // outcome's stack band. Hovering snaps to the closest band, so even the
  // skinniest stripe is reachable.
  const voronoiPoints = useMemo<VoronoiPoint[]>(() => {
    const out: VoronoiPoint[] = [];
    for (const layer of stacked) {
      const outcome = layer.key as CallOutcome;
      for (let i = 0; i < layer.length; i++) {
        const pt = layer[i];
        const value = pt[1] - pt[0];
        if (value === 0) continue;
        const mid = (pt[0] + pt[1]) / 2;
        out.push({
          outcome,
          bucketIdx: i,
          x: xScale(rows[i].t),
          y: yScale(mid),
          value,
        });
      }
    }
    return out;
  }, [stacked, xScale, yScale, rows]);

  const voronoiLayout = useMemo(
    () =>
      voronoi<VoronoiPoint>({
        x: (d) => d.x,
        y: (d) => d.y,
        width: innerW,
        height: innerH,
      }),
    [innerW, innerH],
  );

  // Build the diagram once so `find` is O(log n).
  const voronoiDiagram = useMemo(
    () => voronoiLayout(voronoiPoints),
    [voronoiLayout, voronoiPoints],
  );

  const handleMove = useCallback(
    (event: React.MouseEvent<SVGRectElement>) => {
      const p = localPoint(event);
      if (!p) return;
      const x = p.x - margin.left;
      const y = p.y - margin.top;
      if (x < 0 || x > innerW || y < 0 || y > innerH) return;
      const hit = voronoiDiagram.find(x, y, 60);
      if (!hit) {
        hideTooltip();
        setActiveOutcome(null);
        return;
      }
      setActiveOutcome(hit.data.outcome);
      showTooltip({
        tooltipData: {
          bucketIdx: hit.data.bucketIdx,
          activeOutcome: hit.data.outcome,
          x: hit.data.x,
          y: hit.data.y,
        },
        tooltipLeft: hit.data.x + margin.left,
        tooltipTop: hit.data.y + margin.top,
      });
    },
    [
      voronoiDiagram,
      innerW,
      innerH,
      margin.left,
      margin.top,
      showTooltip,
      hideTooltip,
    ],
  );

  const handleLeave = useCallback(() => {
    hideTooltip();
    setActiveOutcome(null);
  }, [hideTooltip]);

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <svg width={width} height={h} className="overflow-visible">
        <defs>
          {OUTCOME_ORDER.map((o) => {
            const p = OUTCOME_PALETTE[o];
            const id = `${gradPrefix}-${o}`;
            return (
              <linearGradient
                key={id}
                id={id}
                x1="0%"
                y1="0%"
                x2="0%"
                y2="100%"
              >
                <stop offset="0%" stopColor={p.from} stopOpacity={0.95} />
                <stop offset="100%" stopColor={p.to} stopOpacity={0.55} />
              </linearGradient>
            );
          })}
          <filter id={filterId} x="-2%" y="-2%" width="104%" height="104%">
            <feGaussianBlur stdDeviation="0.6" />
          </filter>
        </defs>

        <Group left={margin.left} top={margin.top}>
          {/* Stacked layers */}
          {stacked.map((layer) => {
            const outcome = layer.key as CallOutcome;
            const pal = OUTCOME_PALETTE[outcome];
            const d = areaGen(
              layer as unknown as {
                data: StackedPoint;
                0: number;
                1: number;
              }[],
            );
            if (!d) return null;
            const dim = activeOutcome != null && activeOutcome !== outcome;
            return (
              <path
                key={`layer-${outcome}`}
                d={d}
                fill={`url(#${gradPrefix}-${outcome})`}
                stroke={pal.line}
                strokeOpacity={0.55}
                strokeWidth={0.6}
                filter={`url(#${filterId})`}
                style={{
                  transition:
                    "opacity 220ms cubic-bezier(0.16,1,0.3,1), filter 220ms ease",
                  opacity: dim ? 0.3 : 1,
                  cursor: "crosshair",
                }}
                pointerEvents="none"
              />
            );
          })}

          {/* Crosshair line over the active bucket */}
          {tooltipOpen && tooltipData && (
            <line
              x1={tooltipData.x}
              x2={tooltipData.x}
              y1={0}
              y2={innerH}
              stroke="rgba(255,255,255,0.22)"
              strokeWidth={1}
              strokeDasharray="3 3"
              pointerEvents="none"
            />
          )}

          {/* Bottom axis */}
          <AxisBottom
            top={innerH}
            scale={xScale}
            stroke={theme.axis}
            tickStroke={theme.axis}
            numTicks={Math.min(7, rows.length)}
            tickFormat={(v) => tickFormatter(v as Date)}
            tickLabelProps={{
              fill: theme.axisLabel,
              fontSize: 10,
              textAnchor: "middle",
              letterSpacing: "0.08em",
              style: { textTransform: "uppercase" },
            }}
            hideAxisLine
          />

          {/* Left axis — only useful when offset is none (positive-only). */}
          {!useSilhouette && (
            <AxisLeft
              scale={yScale}
              stroke={theme.axis}
              tickStroke={theme.axis}
              numTicks={4}
              hideAxisLine
              tickLabelProps={{
                fill: theme.axisLabel,
                fontSize: 10,
                textAnchor: "end",
                dx: -4,
                dy: "0.3em",
              }}
            />
          )}

          {/* Voronoi hit region — invisible but covers the inner plot */}
          <rect
            x={0}
            y={0}
            width={innerW}
            height={innerH}
            fill="transparent"
            onMouseMove={handleMove}
            onMouseLeave={handleLeave}
            style={{ cursor: "crosshair" }}
          />
        </Group>
      </svg>

      {tooltipOpen && tooltipData && (
        <TooltipInPortal
          top={tooltipTop}
          left={tooltipLeft}
          style={{ position: "absolute", pointerEvents: "none" }}
        >
          <ChartTooltip>
            <TooltipHeader>
              {formatDate(rows[tooltipData.bucketIdx].t, "MMM d, HH:mm")}
            </TooltipHeader>
            <div className="flex flex-col gap-0.5">
              {OUTCOME_ORDER.filter(
                (o) => rows[tooltipData.bucketIdx].byOutcome[o] > 0,
              ).map((o) => {
                const pal = OUTCOME_PALETTE[o];
                const isActive = tooltipData.activeOutcome === o;
                return (
                  <div
                    key={o}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.1em] text-slate-400">
                      <span
                        aria-hidden
                        className="h-2 w-2 rounded-sm"
                        style={{
                          background: `linear-gradient(135deg,${pal.from},${pal.to})`,
                          boxShadow: isActive ? `0 0 6px ${pal.to}` : undefined,
                        }}
                      />
                      {outcomeLabels[o]}
                    </span>
                    <span
                      className={
                        "num-mono text-[11px] " +
                        (isActive
                          ? "font-semibold text-slate-50"
                          : "text-slate-200")
                      }
                    >
                      {formatNumber(rows[tooltipData.bucketIdx].byOutcome[o])}
                    </span>
                  </div>
                );
              })}
              <div className="mt-1 flex items-center justify-between border-t border-white/10 pt-1">
                <span className="text-[10px] uppercase tracking-[0.1em] text-slate-500">
                  Total
                </span>
                <span className="num-mono text-[11px] font-semibold text-slate-100">
                  {formatNumber(rows[tooltipData.bucketIdx].total)}
                </span>
              </div>
            </div>
          </ChartTooltip>
        </TooltipInPortal>
      )}
    </div>
  );
}
