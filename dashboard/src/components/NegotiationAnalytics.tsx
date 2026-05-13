// Grouped bars (agreed vs walked) per negotiation round + a line overlay for
// average discount percentage on the secondary axis.
//
// Polish:
//   • Bars get a vertical gradient (emerald for agreed, rose for walked) and
//     rounded top corners. `walked` uses a hatched pattern via `@visx/pattern`
//     so it stays distinguishable for color-blind viewers.
//   • Hovering a bar floats a tooltip with round-level breakdown.
//   • Discount line is amber, 2.5px, with halo dots at each round.
//   • Axes use hairline ticks + dotted grid rows + uppercase micro-labels.
import { useMemo, useState } from "react";
import { BarGroup, LinePath, Bar } from "@visx/shape";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { AxisBottom, AxisLeft, AxisRight } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { ParentSize } from "@visx/responsive";
import { LinearGradient } from "@visx/gradient";
import { PatternLines } from "@visx/pattern";
import { curveMonotoneX } from "@visx/curve";
import { useTooltip, useTooltipInPortal } from "@visx/tooltip";
import { localPoint } from "@visx/event";
import type { components } from "@/types/api";
import { theme } from "@/lib/theme";
import { EmptyState } from "@/components/Loading";
import { ChartTooltip, TooltipHeader, TooltipRow } from "@/components/Tooltip";
import { formatNumber, formatPercent } from "@/lib/formatters";

type NegotiationSection = components["schemas"]["NegotiationSection"];

interface NegotiationAnalyticsProps {
  data: NegotiationSection;
  height?: number;
}

const keys = ["agreed", "walked"] as const;
type Key = (typeof keys)[number];

interface Row {
  round: string;
  agreed: number;
  walked: number;
  discount: number;
}

interface TooltipData {
  row: Row;
}

export function NegotiationAnalytics({
  data,
  height = 280,
}: NegotiationAnalyticsProps) {
  const rows: Row[] = useMemo(
    () =>
      (data.buckets ?? []).map((b) => ({
        round: `R${b.round}`,
        agreed: b.agreed,
        walked: b.walked,
        discount: b.avg_discount_pct,
      })),
    [data],
  );

  if (rows.length === 0) {
    return <EmptyState title="No negotiations yet" />;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-end gap-4 text-xs">
        <LegendSwatch gradId="neg-agreed-h" label="Agreed" />
        <LegendSwatch
          gradId="neg-walked-h"
          label="Walked"
          patternId="neg-walked-legend"
        />
        <LegendSwatch
          color="#f59e0b"
          label="Avg discount %"
          dashed
        />
      </div>
      <div style={{ width: "100%", height }}>
        <ParentSize>
          {({ width, height: h }) => (
            <NegotiationInner width={width} height={h} rows={rows} />
          )}
        </ParentSize>
      </div>
    </div>
  );
}

interface InnerProps {
  width: number;
  height: number;
  rows: Row[];
}

function NegotiationInner({ width, height: h, rows }: InnerProps) {
  const {
    showTooltip,
    hideTooltip,
    tooltipData,
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
  } = useTooltip<TooltipData>();
  const { containerRef, TooltipInPortal } = useTooltipInPortal({
    detectBounds: true,
    scroll: true,
  });
  const [hoveredRound, setHoveredRound] = useState<string | null>(null);

  if (width === 0 || h === 0) return null;
  const margin = { top: 14, right: 50, bottom: 34, left: 40 };
  const innerW = Math.max(0, width - margin.left - margin.right);
  const innerH = Math.max(0, h - margin.top - margin.bottom);

  const x0Scale = scaleBand<string>({
    domain: rows.map((r) => r.round),
    range: [0, innerW],
    padding: 0.32,
  });
  const x1Scale = scaleBand<Key>({
    domain: [...keys],
    range: [0, x0Scale.bandwidth()],
    padding: 0.12,
  });
  const yMax = Math.max(1, ...rows.map((r) => Math.max(r.agreed, r.walked)));
  const yScale = scaleLinear<number>({
    domain: [0, yMax * 1.18],
    range: [innerH, 0],
    nice: true,
  });
  const discountMax = Math.max(5, ...rows.map((r) => r.discount));
  const yDiscount = scaleLinear<number>({
    domain: [0, discountMax * 1.18],
    range: [innerH, 0],
    nice: true,
  });

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <svg width={width} height={h} className="overflow-visible">
        <LinearGradient
          id="neg-agreed"
          from="#34d399"
          to="#059669"
          vertical
        />
        <LinearGradient
          id="neg-agreed-h"
          from="#34d399"
          to="#059669"
          vertical={false}
        />
        <LinearGradient
          id="neg-walked"
          from="#fb7185"
          to="#be123c"
          vertical
        />
        <LinearGradient
          id="neg-walked-h"
          from="#fb7185"
          to="#be123c"
          vertical={false}
        />
        <PatternLines
          id="neg-walked-pattern"
          height={6}
          width={6}
          stroke="rgba(255,255,255,0.18)"
          strokeWidth={1}
          orientation={["diagonal"]}
        />
        <PatternLines
          id="neg-walked-legend"
          height={4}
          width={4}
          stroke="rgba(255,255,255,0.4)"
          strokeWidth={1}
          orientation={["diagonal"]}
        />
        <Group left={margin.left} top={margin.top}>
          <GridRows
            scale={yScale}
            width={innerW}
            stroke={theme.grid}
            strokeDasharray="2 4"
            numTicks={4}
          />
          <BarGroup<Row, Key>
            data={rows}
            keys={[...keys]}
            height={innerH}
            x0={(d) => d.round}
            x0Scale={x0Scale}
            x1Scale={x1Scale}
            yScale={yScale}
            color={(k) => (k === "agreed" ? "url(#neg-agreed)" : "url(#neg-walked)")}
          >
            {(barGroups) =>
              barGroups.map((bg) => {
                const round = rows[bg.index].round;
                const isHover = hoveredRound === round;
                return (
                  <Group key={`bg-${bg.index}`} left={bg.x0}>
                    {bg.bars.map((bar) => (
                      <g key={`bar-${bg.index}-${bar.key}`}>
                        <rect
                          x={bar.x}
                          y={bar.y}
                          width={bar.width}
                          height={Math.max(0, bar.height)}
                          fill={bar.color}
                          rx={4}
                          ry={4}
                          style={{
                            transition: "filter 200ms ease, opacity 200ms ease",
                            opacity:
                              hoveredRound && !isHover ? 0.55 : 1,
                            filter: isHover
                              ? "drop-shadow(0 4px 10px rgba(0,0,0,0.35))"
                              : "drop-shadow(0 1px 2px rgba(0,0,0,0.25))",
                            cursor: "pointer",
                          }}
                        />
                        {bar.key === "walked" && (
                          <rect
                            x={bar.x}
                            y={bar.y}
                            width={bar.width}
                            height={Math.max(0, bar.height)}
                            fill="url(#neg-walked-pattern)"
                            rx={4}
                            ry={4}
                            pointerEvents="none"
                            style={{
                              opacity:
                                hoveredRound && !isHover ? 0.55 : 1,
                              transition: "opacity 200ms ease",
                            }}
                          />
                        )}
                        {/* Value label on hover */}
                        {isHover && bar.height > 4 && (
                          <text
                            x={bar.x + bar.width / 2}
                            y={bar.y - 4}
                            textAnchor="middle"
                            fontSize={10}
                            fontWeight={600}
                            fill="#f8fafc"
                            style={{ fontVariantNumeric: "tabular-nums" }}
                          >
                            {formatNumber(rows[bg.index][bar.key as Key])}
                          </text>
                        )}
                      </g>
                    ))}
                    {/* Hover capture overlay over the full group */}
                    <Bar
                      x={0}
                      y={0}
                      width={x0Scale.bandwidth()}
                      height={innerH}
                      fill="transparent"
                      onMouseEnter={(e) => {
                        setHoveredRound(round);
                        const p = localPoint(e);
                        if (!p) return;
                        showTooltip({
                          tooltipData: { row: rows[bg.index] },
                          tooltipLeft: p.x,
                          tooltipTop: p.y,
                        });
                      }}
                      onMouseMove={(e) => {
                        const p = localPoint(e);
                        if (!p) return;
                        showTooltip({
                          tooltipData: { row: rows[bg.index] },
                          tooltipLeft: p.x,
                          tooltipTop: p.y,
                        });
                      }}
                      onMouseLeave={() => {
                        setHoveredRound(null);
                        hideTooltip();
                      }}
                      style={{ cursor: "pointer" }}
                    />
                  </Group>
                );
              })
            }
          </BarGroup>
          <LinePath<Row>
            data={rows}
            x={(d) => (x0Scale(d.round) ?? 0) + x0Scale.bandwidth() / 2}
            y={(d) => yDiscount(d.discount)}
            stroke="#f59e0b"
            strokeWidth={2.25}
            strokeDasharray="4 3"
            strokeLinecap="round"
            curve={curveMonotoneX}
          >
            {({ path }) => (
              // Marquee animation: the dashes slowly drift left → right,
              // pulling the eye along the discount trajectory. Respects
              // reduced-motion via the global CSS rule on `animation`.
              <path
                d={path(rows) ?? undefined}
                fill="none"
                stroke="#f59e0b"
                strokeWidth={2.25}
                strokeDasharray="4 3"
                strokeLinecap="round"
              >
                <animate
                  attributeName="stroke-dashoffset"
                  from="14"
                  to="0"
                  dur="2.4s"
                  repeatCount="indefinite"
                />
              </path>
            )}
          </LinePath>
          {rows.map((r) => {
            const cx = (x0Scale(r.round) ?? 0) + x0Scale.bandwidth() / 2;
            const cy = yDiscount(r.discount);
            return (
              <g key={`dot-${r.round}`}>
                <circle cx={cx} cy={cy} r={5} fill="#f59e0b" fillOpacity={0.2} />
                <circle
                  cx={cx}
                  cy={cy}
                  r={3}
                  fill="#fbbf24"
                  stroke="#0f172a"
                  strokeWidth={1.5}
                />
              </g>
            );
          })}
          <AxisBottom
            top={innerH}
            scale={x0Scale}
            stroke={theme.axis}
            hideAxisLine
            hideTicks
            tickLabelProps={{
              fill: theme.axisLabel,
              fontSize: 10,
              textAnchor: "middle",
              letterSpacing: "0.08em",
              style: { textTransform: "uppercase" },
            }}
          />
          <AxisLeft
            scale={yScale}
            hideAxisLine
            hideTicks
            numTicks={4}
            tickLabelProps={{
              fill: theme.axisLabel,
              fontSize: 10,
              textAnchor: "end",
              dx: -4,
              dy: "0.3em",
            }}
          />
          <AxisRight
            left={innerW}
            scale={yDiscount}
            hideAxisLine
            hideTicks
            numTicks={4}
            tickFormat={(v) => `${v}%`}
            tickLabelProps={{
              fill: "#fbbf24",
              fontSize: 10,
              textAnchor: "start",
              dx: 4,
              dy: "0.3em",
            }}
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
            <TooltipHeader>Round {tooltipData.row.round.slice(1)}</TooltipHeader>
            <TooltipRow
              label="Agreed"
              value={formatNumber(tooltipData.row.agreed)}
              swatchGradient="linear-gradient(90deg,#34d399,#059669)"
              swatch="#10b981"
            />
            <TooltipRow
              label="Walked"
              value={formatNumber(tooltipData.row.walked)}
              swatchGradient="linear-gradient(90deg,#fb7185,#be123c)"
              swatch="#f43f5e"
            />
            <TooltipRow
              label="Avg discount"
              value={formatPercent(tooltipData.row.discount)}
              swatch="#f59e0b"
            />
          </ChartTooltip>
        </TooltipInPortal>
      )}
    </div>
  );
}

function LegendSwatch({
  gradId,
  color,
  label,
  dashed,
  patternId,
}: {
  gradId?: string;
  color?: string;
  label: string;
  dashed?: boolean;
  patternId?: string;
}) {
  return (
    <span className="flex items-center gap-1.5 text-xs uppercase tracking-[0.08em] text-slate-400">
      <svg width={22} height={6} aria-hidden>
        {patternId && (
          <defs>
            <PatternLines
              id={`${patternId}-inline`}
              height={3}
              width={3}
              stroke="rgba(255,255,255,0.5)"
              strokeWidth={0.8}
              orientation={["diagonal"]}
            />
          </defs>
        )}
        <line
          x1={0}
          x2={22}
          y1={3}
          y2={3}
          stroke={gradId ? `url(#${gradId})` : color}
          strokeWidth={4}
          strokeDasharray={dashed ? "3 2" : undefined}
          strokeLinecap="round"
        />
      </svg>
      {label}
    </span>
  );
}
