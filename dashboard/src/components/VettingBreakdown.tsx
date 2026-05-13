// FMCSA vetting pass/fail summary + packed-circles of failure reasons.
//
// The donut moved out — pass rate now lives as a sticky header strip with the
// big pass percentage, total count and a pair of swatches. The interesting
// visual is the `@visx/hierarchy` `Pack` layout below: one large emerald
// "Passed" sphere surrounded by rose-tinted spheres sized by failure-reason
// count. Each circle:
//
//   * Radial gradient with a light spot in the upper-left for a 3D sphere feel
//   * Subtle outer ring at 30% opacity
//   * Soft drop-shadow
//   * Label inside the circle if there's room, below otherwise
//   * Hover scales 1.05 + adds an outer glow halo
//   * Tooltip shows full reason + count
//
// If there are zero failures we render a single ghosted dashed-stroke
// circle as the empty state.
import { useId, useMemo, useState } from "react";
import { Pack, hierarchy } from "@visx/hierarchy";
import { ParentSize } from "@visx/responsive";
import { useTooltip, useTooltipInPortal } from "@visx/tooltip";
import { localPoint } from "@visx/event";
import type { components } from "@/types/api";
import { EmptyState } from "@/components/Loading";
import { formatNumber, formatPercent } from "@/lib/formatters";
import { ChartTooltip, TooltipHeader, TooltipRow } from "@/components/Tooltip";

type VettingSection = components["schemas"]["VettingSection"];

interface VettingBreakdownProps {
  data: VettingSection;
}

type CircleKind = "pass" | "fail";

interface CircleDatum {
  id: string;
  kind: CircleKind;
  label: string;
  value: number;
  children?: CircleDatum[];
}

const PASS_PAL = { from: "#a7f3d0", to: "#059669", line: "#064e3b" };
const FAIL_PALS = [
  { from: "#fda4af", to: "#be123c", line: "#9f1239" },
  { from: "#fdba74", to: "#c2410c", line: "#7c2d12" },
  { from: "#fcd34d", to: "#a16207", line: "#713f12" },
  { from: "#f0abfc", to: "#a21caf", line: "#701a75" },
  { from: "#f87171", to: "#991b1b", line: "#7f1d1d" },
];

function prettifyReason(raw: string): string {
  return raw
    .split(/[_-]/g)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function VettingBreakdown({ data }: VettingBreakdownProps) {
  const pass = data.pass_count ?? 0;
  const fail = data.fail_count ?? 0;
  const total = pass + fail;
  const passPct = total > 0 ? (pass / total) * 100 : 0;

  const reasons = useMemo(() => {
    const rows = (data.top_failure_reasons ?? []).map((r) => {
      const reasonValue = (r["reason"] ?? r["name"] ?? "unknown") as string;
      const countValue = Number(r["count"] ?? 0);
      return { reason: prettifyReason(String(reasonValue)), count: countValue };
    });
    return rows.filter((r) => r.count > 0).sort((a, b) => b.count - a.count);
  }, [data]);

  const packData = useMemo<CircleDatum>(() => {
    const children: CircleDatum[] = [];
    // If the API didn't ship failure reasons but we still have fails, render
    // a single "Other failures" sphere so the visual stays alive.
    if (reasons.length === 0 && fail > 0) {
      children.push({
        id: "fail-other",
        kind: "fail",
        label: "Other failures",
        value: fail,
      });
    } else {
      reasons.forEach((r, i) =>
        children.push({
          id: `fail-${i}`,
          kind: "fail",
          label: r.reason,
          value: r.count,
        }),
      );
    }
    if (pass > 0) {
      children.unshift({
        id: "pass",
        kind: "pass",
        label: "Passed",
        value: pass,
      });
    }
    return {
      id: "root",
      kind: "pass",
      label: "root",
      value: 0,
      children,
    };
  }, [reasons, pass, fail]);

  if (total === 0 && reasons.length === 0) {
    return <EmptyState title="No vetting data yet" />;
  }

  return (
    <div className="grid grid-cols-1 gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
            Pass rate
          </p>
          <p className="mt-1 flex items-baseline gap-2">
            <span
              className="num-mono text-4xl font-semibold leading-none text-transparent bg-clip-text"
              style={{
                backgroundImage:
                  "linear-gradient(135deg,#34d399,#10b981,#059669)",
              }}
            >
              {formatPercent(passPct, 0)}
            </span>
            <span className="text-[10px] uppercase tracking-[0.14em] text-slate-500">
              of {formatNumber(total)} carriers
            </span>
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-300">
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{
                background: "linear-gradient(135deg,#34d399,#059669)",
                boxShadow: "0 0 6px rgba(16,185,129,0.6)",
              }}
            />
            <span className="text-slate-400">Passed</span>
            <span className="num-mono font-semibold text-slate-100">
              {formatNumber(pass)}
            </span>
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{
                background: "linear-gradient(135deg,#fb7185,#be123c)",
                boxShadow: "0 0 6px rgba(244,63,94,0.6)",
              }}
            />
            <span className="text-slate-400">Failed</span>
            <span className="num-mono font-semibold text-slate-100">
              {formatNumber(fail)}
            </span>
          </span>
        </div>
      </div>

      <div style={{ width: "100%", height: 280 }}>
        <ParentSize>
          {({ width, height }) =>
            width === 0 || height === 0 ? null : (
              <PackInner
                width={width}
                height={height}
                root={packData}
                hasFailures={fail > 0}
              />
            )
          }
        </ParentSize>
      </div>
    </div>
  );
}

interface PackInnerProps {
  width: number;
  height: number;
  root: CircleDatum;
  hasFailures: boolean;
}

interface CircleTooltip {
  label: string;
  value: number;
  kind: CircleKind;
}

function PackInner({ width, height, root, hasFailures }: PackInnerProps) {
  const filterId = useId().replace(/[:]/g, "");
  const [hovered, setHovered] = useState<string | null>(null);
  const {
    showTooltip,
    hideTooltip,
    tooltipData,
    tooltipOpen,
    tooltipLeft,
    tooltipTop,
  } = useTooltip<CircleTooltip>();
  const { containerRef, TooltipInPortal } = useTooltipInPortal({
    detectBounds: true,
    scroll: true,
  });

  const data = useMemo(
    () => hierarchy(root).sum((d) => (d.children ? 0 : d.value)),
    [root],
  );

  const trackTooltip = (
    e: React.MouseEvent<SVGElement>,
    payload: CircleTooltip,
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
          <filter id={`${filterId}-glow`} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id={`${filterId}-drop`} x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow
              dx="0"
              dy="2"
              stdDeviation="2.5"
              floodColor="rgba(0,0,0,0.45)"
            />
          </filter>
        </defs>
        <Pack root={data} size={[width, height]} padding={12}>
          {(pack) => {
            const nodes = pack.descendants().filter((d) => d.depth === 1);
            return (
              <g>
                {!hasFailures && (
                  <g
                    transform={`translate(${width / 2}, ${height / 2 + 70})`}
                    opacity={0.7}
                  >
                    <circle
                      r={38}
                      fill="none"
                      stroke="rgba(255,255,255,0.15)"
                      strokeDasharray="4 4"
                    />
                    <text
                      y={4}
                      textAnchor="middle"
                      fontSize={10}
                      letterSpacing="0.16em"
                      fill="#64748b"
                      style={{ textTransform: "uppercase" }}
                    >
                      zero failures
                    </text>
                  </g>
                )}
                {nodes.map((node, i) => {
                  const d = node.data;
                  const isHover = hovered === d.id;
                  const palette =
                    d.kind === "pass"
                      ? PASS_PAL
                      : FAIL_PALS[i % FAIL_PALS.length];
                  const gradId = `${filterId}-${d.id}`;
                  const tooLittle = node.r < 22;
                  return (
                    <g
                      key={d.id}
                      style={{
                        transition:
                          "transform 220ms cubic-bezier(0.16,1,0.3,1)",
                        transform: `translate(${node.x}px, ${node.y}px) scale(${isHover ? 1.05 : 1})`,
                        transformOrigin: `${node.x}px ${node.y}px`,
                        cursor: "pointer",
                      }}
                      onMouseEnter={(e) => {
                        setHovered(d.id);
                        trackTooltip(e, {
                          label: d.label,
                          value: d.value,
                          kind: d.kind,
                        });
                      }}
                      onMouseMove={(e) =>
                        trackTooltip(e, {
                          label: d.label,
                          value: d.value,
                          kind: d.kind,
                        })
                      }
                      onMouseLeave={() => {
                        setHovered(null);
                        hideTooltip();
                      }}
                    >
                      <defs>
                        <radialGradient
                          id={gradId}
                          cx="35%"
                          cy="30%"
                          r="65%"
                          fx="35%"
                          fy="30%"
                        >
                          <stop offset="0%" stopColor={palette.from} stopOpacity={0.95} />
                          <stop offset="60%" stopColor={palette.to} stopOpacity={0.95} />
                          <stop offset="100%" stopColor={palette.line} stopOpacity={1} />
                        </radialGradient>
                      </defs>
                      <circle
                        r={node.r}
                        fill={`url(#${gradId})`}
                        filter={
                          isHover
                            ? `url(#${filterId}-glow)`
                            : `url(#${filterId}-drop)`
                        }
                        style={{ transition: "filter 220ms ease" }}
                      />
                      {/* Outer ring */}
                      <circle
                        r={node.r}
                        fill="none"
                        stroke={palette.from}
                        strokeOpacity={0.3}
                        strokeWidth={1}
                      />
                      {/* Specular highlight (subtle) */}
                      <ellipse
                        cx={-node.r * 0.3}
                        cy={-node.r * 0.4}
                        rx={node.r * 0.4}
                        ry={node.r * 0.25}
                        fill="rgba(255,255,255,0.18)"
                        style={{ pointerEvents: "none" }}
                      />
                      {/* Label */}
                      {!tooLittle ? (
                        <g style={{ pointerEvents: "none" }}>
                          <text
                            textAnchor="middle"
                            dy="-0.2em"
                            fontSize={
                              d.kind === "pass"
                                ? Math.min(32, node.r * 0.5)
                                : Math.min(20, node.r * 0.35)
                            }
                            fontWeight={600}
                            fill="#f8fafc"
                            style={{
                              fontFamily:
                                "JetBrains Mono, ui-monospace, monospace",
                            }}
                          >
                            {formatNumber(d.value)}
                          </text>
                          <text
                            textAnchor="middle"
                            dy={d.kind === "pass" ? "1.5em" : "1.4em"}
                            fontSize={9}
                            letterSpacing="0.14em"
                            fill="rgba(255,255,255,0.85)"
                            style={{ textTransform: "uppercase" }}
                          >
                            {d.kind === "pass"
                              ? "Passed"
                              : truncate(d.label, 14)}
                          </text>
                        </g>
                      ) : (
                        <g style={{ pointerEvents: "none" }}>
                          <text
                            textAnchor="middle"
                            dy="0.33em"
                            fontSize={11}
                            fontWeight={600}
                            fill="#f8fafc"
                            style={{
                              fontFamily:
                                "JetBrains Mono, ui-monospace, monospace",
                            }}
                          >
                            {formatNumber(d.value)}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </g>
            );
          }}
        </Pack>
      </svg>
      {tooltipOpen && tooltipData && (
        <TooltipInPortal
          top={tooltipTop}
          left={tooltipLeft}
          style={{ position: "absolute", pointerEvents: "none" }}
        >
          <ChartTooltip>
            <TooltipHeader>
              {tooltipData.kind === "pass" ? "Vetting Passed" : tooltipData.label}
            </TooltipHeader>
            <TooltipRow
              label="Carriers"
              value={formatNumber(tooltipData.value)}
              swatch={tooltipData.kind === "pass" ? PASS_PAL.to : FAIL_PALS[0].to}
              emphasis
            />
          </ChartTooltip>
        </TooltipInPortal>
      )}
    </div>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}
