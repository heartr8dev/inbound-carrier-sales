// Top lanes table + state-flow chord diagram.
//
// The chord is the showstopper here. We aggregate every recent call by
// (origin_state → destination_state) into an n×n flow matrix, then feed it
// through `@visx/chord` (`d3-chord` under the hood). Top N states keep the
// ribbon density readable; everything else collapses into "Other".
//
// Visual recipe:
//   * Outer arcs (`@visx/shape` Arc) — each state of origin gets a unique
//     2-stop gradient sampled from a curated jewel-tone hue rotation.
//   * Inner ribbons — gradient interpolates from origin color → destination
//     color along the path. Each ribbon owns a one-off `<linearGradient>`
//     whose x1/y1/x2/y2 are computed from the source/target arc midpoints.
//   * Hover an arc → ribbons that don't touch it fade to 8% opacity; the
//     arc gets a soft outer-glow filter.
//   * Hover a ribbon → both endpoint arcs glow; tooltip "Origin → Dest: N".
//   * Center text: "Lane Flow" + total carriers, small caps tracking wide.
//
// We also keep the existing lane table — moved beside the chord on wide
// viewports so each gets ~50% real estate.
import { useMemo, useState } from "react";
import { Arc } from "@visx/shape";
import { Group } from "@visx/group";
import { ParentSize } from "@visx/responsive";
import { Chord, Ribbon } from "@visx/chord";
import { useTooltip, useTooltipInPortal } from "@visx/tooltip";
import { localPoint } from "@visx/event";
import type { components } from "@/types/api";
import { EmptyState } from "@/components/Loading";
import { formatNumber } from "@/lib/formatters";
import { ChartTooltip, TooltipHeader, TooltipRow } from "@/components/Tooltip";

type LoadMatchingSection = components["schemas"]["LoadMatchingSection"];
type RecentCallItem = components["schemas"]["RecentCallItem"];

interface LoadMatchingProps {
  data: LoadMatchingSection;
  recentCalls: RecentCallItem[];
}

// 8 jewel-tone hues evenly spaced around the wheel, slightly desaturated so
// adjacent ribbons read as distinct rather than primary-loud.
const STATE_PALETTE: Array<{ from: string; to: string; line: string }> = [
  { from: "#a5b4fc", to: "#4338ca", line: "#312e81" }, // indigo
  { from: "#c4b5fd", to: "#7c3aed", line: "#4c1d95" }, // violet
  { from: "#f0abfc", to: "#a21caf", line: "#701a75" }, // fuchsia
  { from: "#fda4af", to: "#be123c", line: "#9f1239" }, // rose
  { from: "#fcd34d", to: "#d97706", line: "#92400e" }, // amber
  { from: "#bef264", to: "#65a30d", line: "#3f6212" }, // lime
  { from: "#6ee7b7", to: "#047857", line: "#064e3b" }, // emerald
  { from: "#67e8f9", to: "#0891b2", line: "#155e75" }, // cyan
];

/** Extract a 2-letter US state code from a "City, ST" string. */
function stateOf(addr?: string | null): string | null {
  if (!addr) return null;
  const m = addr.trim().match(/,\s*([A-Za-z]{2})\b\s*$/);
  return m ? m[1].toUpperCase() : null;
}

interface ChordData {
  labels: string[];
  matrix: number[][];
  totalFlow: number;
}

function buildChordData(
  recentCalls: RecentCallItem[],
  topLanes: LoadMatchingSection["top_lanes"],
  topN = 8,
): ChordData {
  const flows = new Map<string, Map<string, number>>();
  function bump(o: string, d: string, n: number) {
    let row = flows.get(o);
    if (!row) {
      row = new Map();
      flows.set(o, row);
    }
    row.set(d, (row.get(d) ?? 0) + n);
  }
  // Top-lane aggregates from the metrics endpoint = primary signal.
  for (const lane of topLanes ?? []) {
    const o = stateOf(lane.origin);
    const d = stateOf(lane.destination);
    if (!o || !d) continue;
    bump(o, d, lane.count);
  }
  // Recent calls supply finer-grained pairs (one per call).
  for (const c of recentCalls ?? []) {
    const o = stateOf(c.origin_requested);
    const d = stateOf(c.destination_requested);
    if (!o || !d) continue;
    bump(o, d, 1);
  }

  // Sum total per state (in + out) and pick top N.
  const totals = new Map<string, number>();
  for (const [o, row] of flows) {
    for (const [d, n] of row) {
      totals.set(o, (totals.get(o) ?? 0) + n);
      totals.set(d, (totals.get(d) ?? 0) + n);
    }
  }
  const sorted = Array.from(totals.entries()).sort((a, b) => b[1] - a[1]);
  const top = sorted.slice(0, topN).map(([k]) => k);
  const hasOther = sorted.length > topN;
  const labels = hasOther ? [...top, "Other"] : top;
  const idx = new Map(labels.map((l, i) => [l, i]));
  const n = labels.length;
  const matrix: number[][] = Array.from({ length: n }, () =>
    Array(n).fill(0),
  );
  let totalFlow = 0;
  for (const [o, row] of flows) {
    const oi = idx.get(o) ?? (hasOther ? idx.get("Other")! : -1);
    if (oi < 0) continue;
    for (const [d, count] of row) {
      const di = idx.get(d) ?? (hasOther ? idx.get("Other")! : -1);
      if (di < 0) continue;
      matrix[oi][di] += count;
      totalFlow += count;
    }
  }
  return { labels, matrix, totalFlow };
}

export function LoadMatching({ data, recentCalls }: LoadMatchingProps) {
  const lanes = useMemo(
    () => (data.top_lanes ?? []).slice(0, 8),
    [data.top_lanes],
  );

  const chord = useMemo(
    () => buildChordData(recentCalls, data.top_lanes ?? []),
    [recentCalls, data.top_lanes],
  );

  if (lanes.length === 0 && chord.labels.length === 0) {
    return <EmptyState title="No matching data yet" />;
  }

  const maxLaneCount = Math.max(1, ...lanes.map((l) => l.count));

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Top lanes by volume
        </p>
        {lanes.length === 0 ? (
          <p className="text-xs text-slate-500">No lane data yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-[0.12em] text-slate-500">
                <th className="pb-2 font-medium">Origin</th>
                <th className="pb-2 font-medium">Destination</th>
                <th className="pb-2 text-right font-medium">Calls</th>
              </tr>
            </thead>
            <tbody>
              {lanes.map((lane, i) => {
                const pct = (lane.count / maxLaneCount) * 100;
                return (
                  <tr
                    key={`${lane.origin}-${lane.destination}-${i}`}
                    className="group relative border-t border-white/[0.04] text-slate-200 transition-colors hover:bg-white/[0.02]"
                  >
                    <td className="py-2 pr-2 text-slate-100">
                      {lane.origin || "—"}
                    </td>
                    <td className="py-2 pr-2 text-slate-300">
                      <span className="text-slate-500">→</span>{" "}
                      {lane.destination || "—"}
                    </td>
                    <td className="relative py-2 text-right num-mono text-slate-50">
                      <span className="relative z-10">
                        {formatNumber(lane.count)}
                      </span>
                      <span
                        aria-hidden
                        className="absolute right-0 top-1/2 h-1 -translate-y-1/2 rounded-full"
                        style={{
                          width: `${pct * 0.7}%`,
                          maxWidth: "80%",
                          background:
                            "linear-gradient(90deg, transparent, rgba(99,102,241,0.45))",
                          opacity: 0.5,
                          marginRight: "44px",
                        }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="lg:col-span-3">
        <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          State-to-state flow
        </p>
        {chord.labels.length < 2 ? (
          <p className="text-xs text-slate-500">
            Not enough cross-state data yet.
          </p>
        ) : (
          <div style={{ width: "100%", height: 360 }}>
            <ParentSize>
              {({ width, height }) =>
                width === 0 || height === 0 ? null : (
                  <ChordInner
                    width={width}
                    height={height}
                    chord={chord}
                  />
                )
              }
            </ParentSize>
          </div>
        )}
      </div>
    </div>
  );
}

interface ChordInnerProps {
  width: number;
  height: number;
  chord: ChordData;
}

interface ArcTooltip {
  kind: "arc";
  index: number;
  label: string;
  total: number;
}
interface RibbonTooltip {
  kind: "ribbon";
  src: string;
  tgt: string;
  count: number;
}
type ChordTooltip = ArcTooltip | RibbonTooltip;

function ChordInner({ width, height, chord }: ChordInnerProps) {
  const size = Math.min(width, height);
  const outerRadius = size / 2 - 30;
  const innerRadius = outerRadius - 10;
  const cx = width / 2;
  const cy = height / 2;
  const [hoverState, setHoverState] = useState<{
    type: "arc" | "ribbon";
    index?: number;
    src?: number;
    tgt?: number;
  } | null>(null);

  const {
    showTooltip,
    hideTooltip,
    tooltipData,
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
  } = useTooltip<ChordTooltip>();
  const { containerRef, TooltipInPortal } = useTooltipInPortal({
    detectBounds: true,
    scroll: true,
  });

  const totalsByState = useMemo(() => {
    return chord.labels.map((_, i) => {
      let t = 0;
      for (let j = 0; j < chord.matrix.length; j++) {
        t += chord.matrix[i][j] + chord.matrix[j][i];
      }
      return t;
    });
  }, [chord]);

  /**
   * Updates the tooltip to follow the cursor. Shared by `onMouseEnter` and
   * `onMouseMove` so we don't repeat the localPoint + showTooltip dance on
   * every interactive primitive.
   */
  const trackTooltip = (
    e: React.MouseEvent<SVGElement>,
    payload: ChordTooltip,
  ) => {
    const p = localPoint(e);
    if (!p) return;
    showTooltip({
      tooltipData: payload,
      tooltipLeft: p.x,
      tooltipTop: p.y,
    });
  };
  const clearTooltip = () => {
    setHoverState(null);
    hideTooltip();
  };

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          <filter id="chord-arc-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Group top={cy} left={cx}>
          <Chord
            matrix={chord.matrix}
            padAngle={0.025}
            sortGroups={(a, b) => b - a}
            sortSubgroups={(a, b) => b - a}
          >
            {({ chords }) => {
              return (
                <g>
                  {/* Ribbons first so arcs draw above */}
                  {chords.map((c, i) => {
                    const srcIdx = c.source.index;
                    const tgtIdx = c.target.index;
                    const srcPal = STATE_PALETTE[srcIdx % STATE_PALETTE.length];
                    const tgtPal = STATE_PALETTE[tgtIdx % STATE_PALETTE.length];
                    const gradId = `chord-r-${srcIdx}-${tgtIdx}-${i}`;
                    // gradient endpoints: midangles of the two arcs, projected
                    // onto inner radius.
                    const aSrc = (c.source.startAngle + c.source.endAngle) / 2;
                    const aTgt = (c.target.startAngle + c.target.endAngle) / 2;
                    const x1 = Math.sin(aSrc) * innerRadius;
                    const y1 = -Math.cos(aSrc) * innerRadius;
                    const x2 = Math.sin(aTgt) * innerRadius;
                    const y2 = -Math.cos(aTgt) * innerRadius;
                    const isOnHoveredArc =
                      hoverState?.type === "arc" &&
                      (hoverState.index === srcIdx ||
                        hoverState.index === tgtIdx);
                    const isHoveredRibbon =
                      hoverState?.type === "ribbon" &&
                      hoverState.src === srcIdx &&
                      hoverState.tgt === tgtIdx;
                    const dim =
                      (hoverState?.type === "arc" && !isOnHoveredArc) ||
                      (hoverState?.type === "ribbon" && !isHoveredRibbon);
                    const op = isHoveredRibbon ? 0.95 : dim ? 0.08 : 0.55;
                    return (
                      <g key={`ribbon-${i}`}>
                        <defs>
                          <linearGradient
                            id={gradId}
                            gradientUnits="userSpaceOnUse"
                            x1={x1}
                            y1={y1}
                            x2={x2}
                            y2={y2}
                          >
                            <stop offset="0%" stopColor={srcPal.to} />
                            <stop offset="100%" stopColor={tgtPal.to} />
                          </linearGradient>
                        </defs>
                        <Ribbon
                          chord={c}
                          radius={innerRadius}
                          fill={`url(#${gradId})`}
                          fillOpacity={op}
                          stroke={tgtPal.line}
                          strokeOpacity={0.35}
                          strokeWidth={0.5}
                          style={{
                            transition:
                              "fill-opacity 220ms ease, stroke-opacity 220ms ease",
                            cursor: "pointer",
                          }}
                          onMouseEnter={(e) => {
                            setHoverState({
                              type: "ribbon",
                              src: srcIdx,
                              tgt: tgtIdx,
                            });
                            trackTooltip(e, {
                              kind: "ribbon",
                              src: chord.labels[srcIdx],
                              tgt: chord.labels[tgtIdx],
                              count: chord.matrix[srcIdx][tgtIdx],
                            });
                          }}
                          onMouseMove={(e) =>
                            trackTooltip(e, {
                              kind: "ribbon",
                              src: chord.labels[srcIdx],
                              tgt: chord.labels[tgtIdx],
                              count: chord.matrix[srcIdx][tgtIdx],
                            })
                          }
                          onMouseLeave={clearTooltip}
                        />
                      </g>
                    );
                  })}

                  {/* Outer arcs */}
                  {chords.groups.map((g, i) => {
                    const pal = STATE_PALETTE[i % STATE_PALETTE.length];
                    const arcGradId = `chord-arc-${i}`;
                    const isHovered =
                      (hoverState?.type === "arc" && hoverState.index === i) ||
                      (hoverState?.type === "ribbon" &&
                        (hoverState.src === i || hoverState.tgt === i));
                    const dim =
                      hoverState !== null &&
                      hoverState.type === "arc" &&
                      hoverState.index !== i;
                    return (
                      <g key={`arc-${i}`}>
                        <defs>
                          <linearGradient
                            id={arcGradId}
                            x1="0%"
                            y1="0%"
                            x2="100%"
                            y2="100%"
                          >
                            <stop offset="0%" stopColor={pal.from} />
                            <stop offset="100%" stopColor={pal.to} />
                          </linearGradient>
                        </defs>
                        <Arc
                          data={g}
                          innerRadius={innerRadius}
                          outerRadius={outerRadius}
                          startAngle={g.startAngle}
                          endAngle={g.endAngle}
                          padAngle={0.01}
                          fill={`url(#${arcGradId})`}
                          stroke={pal.line}
                          strokeWidth={0.5}
                          style={{
                            transition:
                              "opacity 220ms ease, filter 220ms ease",
                            opacity: dim ? 0.45 : 1,
                            filter: isHovered
                              ? "url(#chord-arc-glow)"
                              : undefined,
                            cursor: "pointer",
                          }}
                          onMouseEnter={(e) => {
                            setHoverState({ type: "arc", index: i });
                            trackTooltip(e, {
                              kind: "arc",
                              index: i,
                              label: chord.labels[i],
                              total: totalsByState[i],
                            });
                          }}
                          onMouseMove={(e) =>
                            trackTooltip(e, {
                              kind: "arc",
                              index: i,
                              label: chord.labels[i],
                              total: totalsByState[i],
                            })
                          }
                          onMouseLeave={clearTooltip}
                        />
                        {/* Arc label */}
                        {(() => {
                          const ang = (g.startAngle + g.endAngle) / 2 - Math.PI / 2;
                          const r = outerRadius + 12;
                          const x = Math.cos(ang) * r;
                          const y = Math.sin(ang) * r;
                          const rot = (ang * 180) / Math.PI;
                          // keep label readable: flip if on the left side
                          const rotated = ang > Math.PI / 2 || ang < -Math.PI / 2
                            ? rot + 180
                            : rot;
                          return (
                            <text
                              x={x}
                              y={y}
                              transform={`rotate(${rotated}, ${x}, ${y})`}
                              dy="0.33em"
                              textAnchor={
                                ang > Math.PI / 2 || ang < -Math.PI / 2
                                  ? "end"
                                  : "start"
                              }
                              fontSize={10}
                              fontWeight={600}
                              fill={isHovered ? "#f8fafc" : "#cbd5e1"}
                              letterSpacing="0.08em"
                              style={{
                                fontFamily:
                                  "JetBrains Mono, ui-monospace, monospace",
                                transition: "fill 220ms ease",
                                pointerEvents: "none",
                              }}
                            >
                              {chord.labels[i]}
                            </text>
                          );
                        })()}
                      </g>
                    );
                  })}

                  {/* Center label */}
                  <text
                    textAnchor="middle"
                    dy="-0.4em"
                    fontSize={9}
                    letterSpacing="0.18em"
                    fill="#64748b"
                    style={{
                      textTransform: "uppercase",
                      pointerEvents: "none",
                    }}
                  >
                    Lane Flow
                  </text>
                  <text
                    textAnchor="middle"
                    dy="1.2em"
                    fontSize={22}
                    fontWeight={600}
                    fill="#f8fafc"
                    style={{
                      fontFamily: "JetBrains Mono, ui-monospace, monospace",
                      pointerEvents: "none",
                    }}
                  >
                    {formatNumber(chord.totalFlow)}
                  </text>
                  <text
                    textAnchor="middle"
                    dy="3em"
                    fontSize={9}
                    letterSpacing="0.16em"
                    fill="#64748b"
                    style={{
                      textTransform: "uppercase",
                      pointerEvents: "none",
                    }}
                  >
                    {chord.totalFlow === 1 ? "carrier" : "carriers"}
                  </text>
                </g>
              );
            }}
          </Chord>
        </Group>
      </svg>
      {tooltipOpen && tooltipData && (
        <TooltipInPortal
          top={tooltipTop}
          left={tooltipLeft}
          style={{ position: "absolute", pointerEvents: "none" }}
        >
          <ChartTooltip>
            {tooltipData.kind === "arc" ? (
              <>
                <TooltipHeader>State {tooltipData.label}</TooltipHeader>
                <TooltipRow
                  label="Total flow"
                  value={formatNumber(tooltipData.total)}
                  swatch={
                    STATE_PALETTE[tooltipData.index % STATE_PALETTE.length].to
                  }
                  emphasis
                />
              </>
            ) : (
              <>
                <TooltipHeader>
                  {tooltipData.src} → {tooltipData.tgt}
                </TooltipHeader>
                <TooltipRow
                  label="Calls"
                  value={formatNumber(tooltipData.count)}
                  emphasis
                />
              </>
            )}
          </ChartTooltip>
        </TooltipInPortal>
      )}
    </div>
  );
}
