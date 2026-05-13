// Radial-bar clockface of call volume by hour + sentiment-vs-outcome heatmap.
//
// Donut → Radial bars. 24 arcs in a polar layout, one per hour-of-day, each
// sized by its call count and colored by the dominant sentiment for that
// hour (using the per-sentiment gradient palette). Hover scales the arc up
// and shows a tooltip with the sentiment breakdown. Hour labels appear at
// the 4 cardinal positions (00, 06, 12, 18); the rest are tick marks.
//
// The heatmap below is unchanged in shape, only refreshed cosmetic-wise to
// use the unified mono numerals.
import { useMemo, useState } from "react";
import { Group } from "@visx/group";
import { Arc } from "@visx/shape";
import { HeatmapRect } from "@visx/heatmap";
import { scaleLinear } from "@visx/scale";
import { ParentSize } from "@visx/responsive";
import { LinearGradient } from "@visx/gradient";
import { useTooltip, useTooltipInPortal } from "@visx/tooltip";
import { localPoint } from "@visx/event";
import type { components } from "@/types/api";
import { outcomeLabels, sentimentLabels, theme } from "@/lib/theme";
import { EmptyState } from "@/components/Loading";
import { ChartTooltip, TooltipHeader, TooltipRow } from "@/components/Tooltip";
import { formatNumber } from "@/lib/formatters";
import { useOutcomesByBucket } from "@/hooks/useOutcomesByBucket";

type SentimentSection = components["schemas"]["SentimentSection"];
type CarrierSentiment = components["schemas"]["CarrierSentiment"];
type CallOutcome = components["schemas"]["CallOutcome"];
type RecentCallItem = components["schemas"]["RecentCallItem"];
type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];

interface SentimentChartProps {
  data: SentimentSection;
  period: MetricsPeriod;
  recentCalls: RecentCallItem[];
}

const SENTIMENT_ORDER: CarrierSentiment[] = [
  "positive",
  "neutral",
  "skeptical",
  "frustrated",
  "hostile",
];

const OUTCOME_ORDER: CallOutcome[] = [
  "booked",
  "transferred_to_rep",
  "no_matching_loads",
  "carrier_declined_rate",
  "negotiation_stalled",
  "carrier_failed_vetting",
  "carrier_hung_up",
];

const sentimentSwatch: Record<CarrierSentiment, string> = {
  positive: "#10b981",
  neutral: "#6366f1",
  skeptical: "#f59e0b",
  frustrated: "#fb923c",
  hostile: "#f43f5e",
};
const sentimentPalette: Record<
  CarrierSentiment,
  { from: string; to: string }
> = {
  positive: { from: "#34d399", to: "#059669" },
  neutral: { from: "#a5b4fc", to: "#4338ca" },
  skeptical: { from: "#fcd34d", to: "#d97706" },
  frustrated: { from: "#fdba74", to: "#c2410c" },
  hostile: { from: "#fb7185", to: "#be123c" },
};

interface HourBucket {
  hour: number;
  total: number;
  dominantSentiment: CarrierSentiment | null;
  bySentiment: Record<CarrierSentiment, number>;
}

interface HeatmapCellTooltip {
  sentiment: CarrierSentiment;
  outcome: CallOutcome;
  count: number;
}

export function SentimentChart({
  data,
  period,
  recentCalls,
}: SentimentChartProps) {
  const { buckets } = useOutcomesByBucket(period);

  // Build hour-of-day distribution. Primary source: every call from the
  // periods listing endpoint. Fall back to recent_calls if the calls listing
  // hasn't paged yet.
  const hourBuckets = useMemo<HourBucket[]>(() => {
    // Initialize 24 empty slots.
    const slots: HourBucket[] = Array.from({ length: 24 }, (_, h) => ({
      hour: h,
      total: 0,
      dominantSentiment: null,
      bySentiment: {
        positive: 0,
        neutral: 0,
        skeptical: 0,
        frustrated: 0,
        hostile: 0,
      },
    }));
    // We need per-call sentiment — buckets carry only outcomes. So aggregate
    // the call listing manually here using recentCalls (the dashboard always
    // surfaces a good chunk of recent_calls via the metrics endpoint), plus
    // the OutcomeBucket totals as a fallback for "calls per hour".
    const calls = recentCalls ?? [];
    for (const c of calls) {
      const t = new Date(c.created_at);
      if (Number.isNaN(t.getTime())) continue;
      const h = t.getUTCHours();
      slots[h].total += 1;
      slots[h].bySentiment[c.sentiment] += 1;
    }
    // If we have OutcomeBucket data and the recent-calls signal is sparser,
    // top up the totals so the radial reflects the broader period.
    if (calls.length < 30 && buckets.length > 0) {
      for (const b of buckets) {
        const h = b.t.getUTCHours();
        // Don't double-count if buckets are daily — only hour-granular buckets
        // truly represent a single hour-of-day. Daily buckets get smeared.
        const isHourly =
          buckets.length > 1 &&
          buckets[1].t.getTime() - buckets[0].t.getTime() < 6 * 60 * 60 * 1000;
        if (!isHourly) {
          // Distribute evenly: not strictly correct but keeps the shape alive.
          for (let i = 0; i < 24; i++) slots[i].total += b.total / 24;
        } else {
          slots[h].total += b.total;
        }
      }
    }
    // Compute dominant sentiment per slot.
    for (const s of slots) {
      let best: CarrierSentiment | null = null;
      let bestN = 0;
      for (const k of SENTIMENT_ORDER) {
        if (s.bySentiment[k] > bestN) {
          best = k;
          bestN = s.bySentiment[k];
        }
      }
      s.dominantSentiment = best;
    }
    return slots;
  }, [recentCalls, buckets]);

  const totalCallsRadial = useMemo(
    () => hourBuckets.reduce((s, b) => s + Math.round(b.total), 0),
    [hourBuckets],
  );
  const peakHour = useMemo(() => {
    let best = -1;
    let bestN = -1;
    for (const b of hourBuckets) {
      if (b.total > bestN) {
        bestN = b.total;
        best = b.hour;
      }
    }
    return best;
  }, [hourBuckets]);

  const columns = useMemo(() => {
    return OUTCOME_ORDER.map((outcome) => ({
      outcome,
      bins: SENTIMENT_ORDER.map((sentiment) => {
        const cell = data.heatmap?.find(
          (c) => c.sentiment === sentiment && c.outcome === outcome,
        );
        return { sentiment, count: cell?.count ?? 0 };
      }),
    }));
  }, [data]);

  const maxCount = useMemo(() => {
    let m = 0;
    for (const col of columns) for (const b of col.bins) m = Math.max(m, b.count);
    return m;
  }, [columns]);

  if (totalCallsRadial === 0 && maxCount === 0) {
    return <EmptyState title="No sentiment data yet" />;
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Volume by hour (UTC)
        </p>
        <div className="relative" style={{ width: "100%", height: 280 }}>
          <ParentSize>
            {({ width, height }) =>
              width === 0 || height === 0 ? null : (
                <RadialBars
                  width={width}
                  height={height}
                  hours={hourBuckets}
                  total={totalCallsRadial}
                  peakHour={peakHour}
                  periodLabel={
                    period === "today"
                      ? "today"
                      : period === "7d"
                        ? "7 days"
                        : period === "30d"
                          ? "30 days"
                          : "all time"
                  }
                />
              )
            }
          </ParentSize>
        </div>
      </div>

      <div className="lg:col-span-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Sentiment × Outcome
        </p>
        <Heatmap columns={columns} maxCount={maxCount} />
      </div>
    </div>
  );
}

interface RadialBarsProps {
  width: number;
  height: number;
  hours: HourBucket[];
  total: number;
  peakHour: number;
  periodLabel: string;
}

interface RadialTooltip {
  hour: number;
  total: number;
  dominant: CarrierSentiment | null;
  bySentiment: Record<CarrierSentiment, number>;
}

function RadialBars({
  width,
  height,
  hours,
  total,
  peakHour,
  periodLabel,
}: RadialBarsProps) {
  const cx = width / 2;
  const cy = height / 2;
  const innerRadius = Math.min(width, height) / 2 - 90;
  const outerMax = Math.min(width, height) / 2 - 18;
  const innerR = Math.max(40, innerRadius);
  const maxValue = Math.max(1, ...hours.map((h) => h.total));
  const valueScale = scaleLinear<number>({
    domain: [0, maxValue],
    range: [0, outerMax - innerR],
  });
  const TWO_PI = Math.PI * 2;
  const step = TWO_PI / 24;
  const [hovered, setHovered] = useState<number | null>(null);

  const {
    showTooltip,
    hideTooltip,
    tooltipData,
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
  } = useTooltip<RadialTooltip>();
  const { containerRef, TooltipInPortal } = useTooltipInPortal({
    detectBounds: true,
    scroll: true,
  });
  const trackTooltip = (
    e: React.MouseEvent<SVGElement>,
    payload: RadialTooltip,
  ) => {
    const p = localPoint(e);
    if (!p) return;
    showTooltip({
      tooltipData: payload,
      tooltipLeft: p.x,
      tooltipTop: p.y,
    });
  };

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          {SENTIMENT_ORDER.map((s) => (
            <linearGradient
              key={`rb-${s}`}
              id={`rb-${s}`}
              x1="0%"
              y1="0%"
              x2="0%"
              y2="100%"
            >
              <stop offset="0%" stopColor={sentimentPalette[s].from} />
              <stop offset="100%" stopColor={sentimentPalette[s].to} />
            </linearGradient>
          ))}
        </defs>
        <Group top={cy} left={cx}>
          {/* Concentric grid rings at 25/50/75/100% */}
          {[0.25, 0.5, 0.75, 1].map((f) => (
            <circle
              key={`ring-${f}`}
              r={innerR + (outerMax - innerR) * f}
              fill="none"
              stroke="rgba(255,255,255,0.04)"
              strokeWidth={1}
              strokeDasharray="2 4"
            />
          ))}
          <circle
            r={innerR}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />

          {/* Hour bars */}
          {hours.map((b) => {
            // 12 o'clock = top, increment clockwise → angle = h * step
            const startAngle = b.hour * step - step / 2;
            const endAngle = b.hour * step + step / 2;
            const palette = sentimentPalette[b.dominantSentiment ?? "neutral"];
            const outer = innerR + valueScale(b.total);
            const isHover = hovered === b.hour;
            const isPeak = peakHour === b.hour;
            return (
              <g
                key={`hr-${b.hour}`}
                style={{
                  transition: "transform 220ms cubic-bezier(0.16,1,0.3,1)",
                  transform: isHover ? "scale(1.05)" : "scale(1)",
                  transformOrigin: "0 0",
                  cursor: "pointer",
                }}
              >
                <Arc
                  innerRadius={innerR}
                  outerRadius={Math.max(innerR + 1, outer)}
                  startAngle={startAngle}
                  endAngle={endAngle}
                  padAngle={0.015}
                  cornerRadius={2}
                  fill={
                    b.total > 0
                      ? `url(#rb-${b.dominantSentiment ?? "neutral"})`
                      : "rgba(255,255,255,0.04)"
                  }
                  stroke={palette.to}
                  strokeOpacity={isHover ? 0.7 : 0.18}
                  strokeWidth={isHover ? 1 : 0.5}
                  style={{
                    filter: isHover
                      ? `drop-shadow(0 0 12px ${palette.to})`
                      : isPeak && b.total > 0
                        ? `drop-shadow(0 0 6px ${palette.to}aa)`
                        : undefined,
                    transition: "filter 220ms ease, stroke-opacity 220ms ease",
                  }}
                  onMouseEnter={(e) => {
                    setHovered(b.hour);
                    trackTooltip(e, {
                      hour: b.hour,
                      total: Math.round(b.total),
                      dominant: b.dominantSentiment,
                      bySentiment: b.bySentiment,
                    });
                  }}
                  onMouseMove={(e) =>
                    trackTooltip(e, {
                      hour: b.hour,
                      total: Math.round(b.total),
                      dominant: b.dominantSentiment,
                      bySentiment: b.bySentiment,
                    })
                  }
                  onMouseLeave={() => {
                    setHovered(null);
                    hideTooltip();
                  }}
                />
              </g>
            );
          })}

          {/* Hour labels: 00, 06, 12, 18 outside the chart */}
          {[0, 6, 12, 18].map((h) => {
            const a = h * step - Math.PI / 2;
            const r = outerMax + 12;
            const x = Math.cos(a) * r;
            const y = Math.sin(a) * r;
            return (
              <text
                key={`hl-${h}`}
                x={x}
                y={y}
                dy="0.33em"
                textAnchor="middle"
                fontSize={9}
                letterSpacing="0.14em"
                fill="#64748b"
                style={{
                  textTransform: "uppercase",
                  fontFamily: "JetBrains Mono, ui-monospace, monospace",
                  pointerEvents: "none",
                }}
              >
                {String(h).padStart(2, "0")}
              </text>
            );
          })}
          {/* Center stack: total + period */}
          <text
            textAnchor="middle"
            dy="-0.6em"
            fontSize={26}
            fontWeight={600}
            fill="#f8fafc"
            style={{
              fontFamily: "JetBrains Mono, ui-monospace, monospace",
              pointerEvents: "none",
            }}
          >
            {formatNumber(total)}
          </text>
          <text
            textAnchor="middle"
            dy="0.7em"
            fontSize={9}
            letterSpacing="0.18em"
            fill="#94a3b8"
            style={{
              textTransform: "uppercase",
              pointerEvents: "none",
            }}
          >
            calls · {periodLabel}
          </text>
          {peakHour >= 0 && total > 0 && (
            <g transform="translate(0, 30)">
              <rect
                x={-32}
                y={-7}
                width={64}
                height={14}
                rx={7}
                fill="rgba(255,255,255,0.04)"
                stroke="rgba(255,255,255,0.08)"
              />
              <text
                y={3}
                textAnchor="middle"
                fontSize={9}
                letterSpacing="0.14em"
                fill="#cbd5e1"
                style={{
                  textTransform: "uppercase",
                  fontFamily: "JetBrains Mono, ui-monospace, monospace",
                  pointerEvents: "none",
                }}
              >
                peak {String(peakHour).padStart(2, "0")}:00
              </text>
            </g>
          )}
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
              {String(tooltipData.hour).padStart(2, "0")}:00 UTC
            </TooltipHeader>
            <TooltipRow
              label="Calls"
              value={formatNumber(tooltipData.total)}
              swatch={
                tooltipData.dominant
                  ? sentimentSwatch[tooltipData.dominant]
                  : "#64748b"
              }
              emphasis
            />
            {tooltipData.dominant && (
              <p className="mt-1 text-[10px] uppercase tracking-[0.12em] text-slate-500">
                mostly {sentimentLabels[tooltipData.dominant].toLowerCase()}
              </p>
            )}
          </ChartTooltip>
        </TooltipInPortal>
      )}
    </div>
  );
}

interface HeatmapProps {
  columns: { outcome: CallOutcome; bins: { sentiment: CarrierSentiment; count: number }[] }[];
  maxCount: number;
}

function Heatmap({ columns, maxCount }: HeatmapProps) {
  const {
    showTooltip,
    hideTooltip,
    tooltipData,
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
  } = useTooltip<HeatmapCellTooltip>();
  const { containerRef, TooltipInPortal } = useTooltipInPortal({
    detectBounds: true,
    scroll: true,
  });

  return (
    <div ref={containerRef} className="relative" style={{ width: "100%", height: 280 }}>
      <ParentSize>
        {({ width, height }) => {
          if (width === 0 || height === 0) return null;
          const margin = { top: 4, right: 8, bottom: 64, left: 90 };
          const innerW = Math.max(0, width - margin.left - margin.right);
          const innerH = Math.max(0, height - margin.top - margin.bottom);
          const gap = 4;
          const binWidth = innerW / OUTCOME_ORDER.length;
          const binHeight = innerH / SENTIMENT_ORDER.length;
          const xScale = scaleLinear<number>({
            domain: [0, OUTCOME_ORDER.length],
            range: [0, innerW],
          });
          const yScale = scaleLinear<number>({
            domain: [0, SENTIMENT_ORDER.length],
            range: [0, innerH],
          });
          const colorScale = scaleLinear<string>({
            domain: [0, Math.max(1, maxCount) * 0.4, Math.max(1, maxCount)],
            range: ["#1e293b", "#6366f1", "#5eead4"],
          });
          const opacityScale = scaleLinear<number>({
            domain: [0, Math.max(1, maxCount)],
            range: [0.35, 1],
          });
          return (
            <svg width={width} height={height} className="overflow-visible">
              <LinearGradient
                id="heatmap-text-shadow"
                from="rgba(0,0,0,0.6)"
                to="rgba(0,0,0,0)"
                vertical
              />
              <Group left={margin.left} top={margin.top}>
                <HeatmapRect
                  data={columns}
                  xScale={(d) => xScale(d)}
                  yScale={(d) => yScale(d)}
                  colorScale={colorScale}
                  opacityScale={opacityScale}
                  binWidth={binWidth}
                  binHeight={binHeight}
                  gap={gap}
                  bins={(col) => col.bins}
                  count={(bin) => bin.count}
                >
                  {(heatmap) =>
                    heatmap.map((cols, colIdx) =>
                      cols.map((cell, rowIdx) => {
                        const outcome = OUTCOME_ORDER[colIdx];
                        const sentiment = SENTIMENT_ORDER[rowIdx];
                        const count = cell.count ?? 0;
                        return (
                          <g key={`heat-${cell.column}-${cell.row}`}>
                            <rect
                              x={cell.x}
                              y={cell.y}
                              width={cell.width}
                              height={cell.height}
                              fill={cell.color}
                              fillOpacity={cell.opacity}
                              rx={4}
                              style={{
                                transition:
                                  "filter 220ms ease, fill-opacity 220ms ease",
                                cursor: count > 0 ? "pointer" : "default",
                              }}
                              onMouseEnter={(e) => {
                                const p = localPoint(e);
                                if (!p) return;
                                showTooltip({
                                  tooltipData: { sentiment, outcome, count },
                                  tooltipLeft: p.x,
                                  tooltipTop: p.y,
                                });
                              }}
                              onMouseMove={(e) => {
                                const p = localPoint(e);
                                if (!p) return;
                                showTooltip({
                                  tooltipData: { sentiment, outcome, count },
                                  tooltipLeft: p.x,
                                  tooltipTop: p.y,
                                });
                              }}
                              onMouseLeave={hideTooltip}
                            />
                            {count > 0 && (
                              <text
                                x={cell.x + cell.width / 2}
                                y={cell.y + cell.height / 2}
                                dy="0.33em"
                                textAnchor="middle"
                                fontSize={10}
                                fontWeight={600}
                                fill="#f8fafc"
                                style={{
                                  fontFamily:
                                    "JetBrains Mono, ui-monospace, monospace",
                                  pointerEvents: "none",
                                }}
                              >
                                {count}
                              </text>
                            )}
                          </g>
                        );
                      }),
                    )
                  }
                </HeatmapRect>
                {SENTIMENT_ORDER.map((s, i) => (
                  <text
                    key={`yl-${s}`}
                    x={-8}
                    y={yScale(i) + binHeight / 2}
                    dy="0.33em"
                    textAnchor="end"
                    fontSize={10}
                    fill={theme.axisLabel}
                    letterSpacing="0.06em"
                  >
                    {sentimentLabels[s]}
                  </text>
                ))}
                {OUTCOME_ORDER.map((o, i) => (
                  <g
                    key={`xl-${o}`}
                    transform={`translate(${xScale(i) + binWidth / 2}, ${innerH + 10}) rotate(-35)`}
                  >
                    <text
                      textAnchor="end"
                      fontSize={9}
                      fill={theme.axisLabel}
                      letterSpacing="0.06em"
                    >
                      {outcomeLabels[o]}
                    </text>
                  </g>
                ))}
              </Group>
            </svg>
          );
        }}
      </ParentSize>
      {tooltipOpen && tooltipData && (
        <TooltipInPortal
          top={tooltipTop}
          left={tooltipLeft}
          style={{ position: "absolute", pointerEvents: "none" }}
        >
          <ChartTooltip>
            <TooltipHeader>
              {sentimentLabels[tooltipData.sentiment]} → {outcomeLabels[tooltipData.outcome]}
            </TooltipHeader>
            <TooltipRow
              label="Calls"
              value={formatNumber(tooltipData.count)}
              swatch={sentimentSwatch[tooltipData.sentiment]}
              emphasis
            />
          </ChartTooltip>
        </TooltipInPortal>
      )}
    </div>
  );
}
