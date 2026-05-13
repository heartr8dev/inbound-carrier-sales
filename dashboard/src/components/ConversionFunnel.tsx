// Sankey-style conversion funnel.
//
// Visual upgrades over the baseline:
//   • Each node uses a gradient fill that fades down the funnel from emerald
//     (top-of-funnel) into amber→rose (where carriers drop off).
//   • Links are rendered with a horizontal gradient — source-stage color
//     fading into target-stage color — at 26% opacity.
//   • Hover state: the focused link goes to 92% opacity, others fade to 12%.
//     Implemented entirely in React state — no external animation lib.
//   • Stage labels split into 3 lines: uppercase micro-label, count, and a
//     pill showing the retained-from-prior-stage percentage.
import { useMemo, useState } from "react";
import { ParentSize } from "@visx/responsive";
import { Sankey } from "@visx/sankey";
import { Group } from "@visx/group";
import { LinearGradient } from "@visx/gradient";
import type { components } from "@/types/api";
import { EmptyState } from "@/components/Loading";
import { formatNumber } from "@/lib/formatters";

type FunnelSection = components["schemas"]["FunnelSection"];

interface ConversionFunnelProps {
  data: FunnelSection;
  height?: number;
}

interface NodeDatum extends Record<string, unknown> {
  name: string;
}

interface LinkDatum extends Record<string, unknown> {
  source: number;
  target: number;
  value: number;
}

interface SankeyComputed {
  index: number;
  name?: string;
  x0?: number;
  x1?: number;
  y0?: number;
  y1?: number;
  value?: number;
}

interface SankeyLinkComputed {
  width?: number;
}

// Stage-to-stage gradient ramp: emerald → cyan → indigo → amber → rose.
// Tuned for 4–6 stages; longer funnels reuse the last gradient.
const stageStops = [
  ["#34d399", "#10b981"], // emerald
  ["#5eead4", "#14b8a6"], // teal
  ["#67e8f9", "#06b6d4"], // cyan
  ["#a5b4fc", "#6366f1"], // indigo
  ["#fcd34d", "#f59e0b"], // amber
  ["#fb7185", "#f43f5e"], // rose
] as const;

export function ConversionFunnel({ data, height = 340 }: ConversionFunnelProps) {
  const [hoveredLink, setHoveredLink] = useState<number | null>(null);

  const graph = useMemo(() => {
    const stages = data.stages ?? [];
    const nodes: NodeDatum[] = stages.map((s) => ({ name: s.name }));
    const links: LinkDatum[] = [];
    for (let i = 0; i < stages.length - 1; i++) {
      const next = stages[i + 1];
      const value = Math.max(0, next.count);
      if (value > 0) {
        links.push({ source: i, target: i + 1, value });
      }
    }
    return { nodes, links };
  }, [data]);

  if (graph.nodes.length === 0 || graph.links.length === 0) {
    return (
      <EmptyState
        title="Funnel data not ready"
        description="Once calls log, the carrier conversion funnel will populate here."
      />
    );
  }

  const stages = data.stages ?? [];
  const totalIn = stages[0]?.count ?? 0;

  return (
    <div style={{ width: "100%", height }}>
      <ParentSize>
        {({ width, height: h }) => {
          if (width === 0 || h === 0) return null;
          const margin = { top: 18, right: 140, bottom: 18, left: 16 };
          const innerW = Math.max(0, width - margin.left - margin.right);
          const innerH = Math.max(0, h - margin.top - margin.bottom);
          return (
            <svg width={width} height={h}>
              <defs>
                {/* Per-node vertical gradient */}
                {graph.nodes.map((_, i) => {
                  const stop = stageStops[Math.min(i, stageStops.length - 1)];
                  return (
                    <LinearGradient
                      key={`fn-node-${i}`}
                      id={`fn-node-${i}`}
                      from={stop[0]}
                      to={stop[1]}
                      vertical
                    />
                  );
                })}
                {/* Per-link horizontal gradient (source color → target color) */}
                {graph.links.map((l, i) => {
                  const src = stageStops[Math.min(l.source, stageStops.length - 1)];
                  const tgt = stageStops[Math.min(l.target, stageStops.length - 1)];
                  return (
                    <LinearGradient
                      key={`fn-link-${i}`}
                      id={`fn-link-${i}`}
                      from={src[1]}
                      to={tgt[0]}
                      x1="0%"
                      x2="100%"
                      y1="0%"
                      y2="0%"
                    />
                  );
                })}
              </defs>
              <Group left={margin.left} top={margin.top}>
                <Sankey<NodeDatum, LinkDatum>
                  root={{ nodes: graph.nodes, links: graph.links }}
                  size={[innerW, innerH]}
                  nodeWidth={14}
                  nodePadding={22}
                >
                  {({ graph: g, createPath }) => (
                    <>
                      {/* Links first so nodes draw above */}
                      {g.links.map((link, i) => {
                        const computed = link as unknown as SankeyLinkComputed;
                        const isHover = hoveredLink === i;
                        const hasHover = hoveredLink != null;
                        const opacity = hasHover
                          ? isHover
                            ? 0.92
                            : 0.1
                          : 0.32;
                        const d = createPath(link) ?? "";
                        const pathId = `fn-link-path-${i}`;
                        // Particle count scales with flow volume — more
                        // carriers, more dots. Capped so wide channels don't
                        // overwhelm the eye.
                        const particleCount = Math.min(
                          5,
                          Math.max(2, Math.round((link.value as number) / 10)),
                        );
                        const dur = 5 + (i % 3); // staggered durations 5/6/7s
                        return (
                          <g key={`link-${i}`}>
                            <path
                              id={pathId}
                              d={d}
                              fill="none"
                              stroke={`url(#fn-link-${i})`}
                              strokeOpacity={opacity}
                              strokeWidth={Math.max(1, computed.width ?? 1)}
                              style={{
                                transition: "stroke-opacity 220ms ease",
                                cursor: "pointer",
                              }}
                              onMouseEnter={() => setHoveredLink(i)}
                              onMouseLeave={() => setHoveredLink(null)}
                            />
                            {/* Animated flow particles drifting source→target. */}
                            {Array.from({ length: particleCount }).map(
                              (_, pi) => {
                                const begin = `${(pi * dur) / particleCount}s`;
                                return (
                                  <circle
                                    key={`p-${i}-${pi}`}
                                    r={1.6}
                                    fill="#ffffff"
                                    opacity={hasHover && !isHover ? 0.05 : 0.55}
                                    style={{
                                      transition: "opacity 220ms ease",
                                      pointerEvents: "none",
                                    }}
                                  >
                                    <animateMotion
                                      dur={`${dur}s`}
                                      begin={begin}
                                      repeatCount="indefinite"
                                      rotate="auto"
                                    >
                                      <mpath href={`#${pathId}`} />
                                    </animateMotion>
                                    <animate
                                      attributeName="opacity"
                                      values="0;0.7;0.7;0"
                                      keyTimes="0;0.1;0.85;1"
                                      dur={`${dur}s`}
                                      begin={begin}
                                      repeatCount="indefinite"
                                    />
                                  </circle>
                                );
                              },
                            )}
                          </g>
                        );
                      })}
                      {g.nodes.map((node, i) => {
                        const n = node as unknown as SankeyComputed;
                        if (
                          n.x0 == null ||
                          n.x1 == null ||
                          n.y0 == null ||
                          n.y1 == null
                        )
                          return null;
                        const w = n.x1 - n.x0;
                        const h2 = n.y1 - n.y0;
                        const count = n.value ?? 0;
                        const retainedPct =
                          totalIn > 0
                            ? Math.round((count / totalIn) * 100)
                            : 0;
                        const prevCount = i > 0 ? stages[i - 1]?.count ?? 0 : 0;
                        const stepRetained =
                          prevCount > 0
                            ? Math.round((count / prevCount) * 100)
                            : null;
                        return (
                          <Group key={`node-${i}`}>
                            <rect
                              x={n.x0}
                              y={n.y0}
                              width={w}
                              height={Math.max(1, h2)}
                              fill={`url(#fn-node-${i})`}
                              rx={3}
                              style={{
                                filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.3))",
                              }}
                            />
                            {/* Label group anchored to the right of the node */}
                            <g transform={`translate(${n.x1 + 10}, ${(n.y0 + n.y1) / 2})`}>
                              <text
                                y={-14}
                                fontSize={9}
                                fontWeight={600}
                                letterSpacing="0.12em"
                                fill="#94a3b8"
                                style={{ textTransform: "uppercase" }}
                              >
                                {n.name ?? ""}
                              </text>
                              <text
                                y={4}
                                fontSize={15}
                                fontWeight={600}
                                fill="#f8fafc"
                                style={{ fontVariantNumeric: "tabular-nums" }}
                              >
                                {formatNumber(count)}
                              </text>
                              <g transform="translate(0, 12)">
                                <rect
                                  x={-2}
                                  y={2}
                                  rx={4}
                                  ry={4}
                                  width={
                                    stepRetained != null ? 70 : 56
                                  }
                                  height={14}
                                  fill="rgba(255,255,255,0.04)"
                                  stroke="rgba(255,255,255,0.06)"
                                />
                                <text
                                  y={12}
                                  fontSize={9}
                                  fill="#94a3b8"
                                  style={{
                                    fontVariantNumeric: "tabular-nums",
                                  }}
                                >
                                  {stepRetained != null
                                    ? `${stepRetained}% retained`
                                    : `${retainedPct}% of total`}
                                </text>
                              </g>
                            </g>
                          </Group>
                        );
                      })}
                    </>
                  )}
                </Sankey>
              </Group>
            </svg>
          );
        }}
      </ParentSize>
    </div>
  );
}
