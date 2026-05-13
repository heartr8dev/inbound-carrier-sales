// Sticky 4-card KPI bar at the top of the dashboard.
//
// Each tile:
//   • Top-left semantic icon in a tinted pill
//   • Delta vs prior period as a colored pill with arrow (top-right)
//   • Display number (4xl tabular-nums) — count-up animated on change
//   • Tiny “vs prior period” caption
//   • Sparkline (60px) of the timeseries trend with gradient stroke + 6% area
//   • Voronoi overlay on the sparkline: cursor reveals "hour N: V calls"
import clsx from "clsx";
import { useCallback, useMemo, useState } from "react";
import { LinePath, AreaClosed } from "@visx/shape";
import { scaleLinear } from "@visx/scale";
import { ParentSize } from "@visx/responsive";
import { curveMonotoneX } from "@visx/curve";
import { LinearGradient } from "@visx/gradient";
import { voronoi as buildVoronoi } from "@visx/voronoi";
import { localPoint } from "@visx/event";
import type { components } from "@/types/api";
import {
  formatCurrency,
  formatDelta,
  formatNumber,
  formatPercent,
  toNumber,
} from "@/lib/formatters";
import { useCountUp } from "@/hooks/useCountUp";
import {
  PhoneIcon,
  DollarIcon,
  CheckIcon,
  RefreshIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  MinusIcon,
} from "@/components/icons";

type KpiBarData = components["schemas"]["KPIBar"];
type TimeseriesSection = components["schemas"]["TimeseriesSection"];

interface KpiBarProps {
  data: KpiBarData;
  prior?: KpiBarData | null;
  loading?: boolean;
  timeseries?: TimeseriesSection | null;
}

interface KpiSpec {
  key: string;
  label: string;
  rawValue: number;
  format: (n: number) => string;
  delta: { text: string; sign: "up" | "down" | "flat" };
  upIsGood: boolean;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  tone: "info" | "success" | "warning" | "accent";
  sparkKey: "calls" | "booked";
}

function deltaToneClasses(
  sign: "up" | "down" | "flat",
  upIsGood: boolean,
): { fg: string; bg: string; ring: string } {
  if (sign === "flat") {
    return {
      fg: "text-slate-400",
      bg: "bg-white/[0.04]",
      ring: "ring-white/10",
    };
  }
  const isPositive = (sign === "up") === upIsGood;
  return isPositive
    ? {
        fg: "text-emerald-300",
        bg: "bg-emerald-500/10",
        ring: "ring-emerald-500/30",
      }
    : {
        fg: "text-rose-300",
        bg: "bg-rose-500/10",
        ring: "ring-rose-500/30",
      };
}

const toneStyles: Record<
  KpiSpec["tone"],
  { icon: string; gradId: string; gradStops: [string, string] }
> = {
  info: {
    icon: "text-indigo-300 bg-indigo-500/15 ring-indigo-500/25",
    gradId: "spark-info",
    gradStops: ["#a5b4fc", "#6366f1"],
  },
  success: {
    icon: "text-emerald-300 bg-emerald-500/15 ring-emerald-500/25",
    gradId: "spark-success",
    gradStops: ["#34d399", "#10b981"],
  },
  warning: {
    icon: "text-amber-300 bg-amber-500/15 ring-amber-500/25",
    gradId: "spark-warning",
    gradStops: ["#fbbf24", "#f59e0b"],
  },
  accent: {
    icon: "text-cyan-300 bg-cyan-500/15 ring-cyan-500/25",
    gradId: "spark-accent",
    gradStops: ["#67e8f9", "#06b6d4"],
  },
};

export function KpiBar({ data, prior, loading, timeseries }: KpiBarProps) {
  const points = useMemo(
    () => timeseries?.points ?? [],
    [timeseries],
  );

  const kpis: KpiSpec[] = useMemo(
    () => [
      {
        key: "calls",
        label: "Calls Today",
        rawValue: data.calls_today,
        format: (n: number) => formatNumber(Math.round(n)),
        delta: formatDelta(data.calls_today, prior?.calls_today ?? 0),
        upIsGood: true,
        Icon: PhoneIcon,
        tone: "info",
        sparkKey: "calls",
      },
      {
        key: "booked",
        label: "Booked Rate",
        rawValue: data.booked_rate_pct,
        format: (n: number) => formatPercent(n),
        delta: formatDelta(
          data.booked_rate_pct,
          prior?.booked_rate_pct ?? 0,
        ),
        upIsGood: true,
        Icon: CheckIcon,
        tone: "success",
        sparkKey: "booked",
      },
      {
        key: "margin",
        label: "Avg Margin Saved",
        rawValue: toNumber(data.avg_margin_saved_usd),
        format: (n: number) => formatCurrency(n),
        delta: formatDelta(
          toNumber(data.avg_margin_saved_usd),
          toNumber(prior?.avg_margin_saved_usd ?? 0),
        ),
        upIsGood: true,
        Icon: DollarIcon,
        tone: "accent",
        sparkKey: "booked",
      },
      {
        key: "rounds",
        label: "Avg Negotiation Rounds",
        rawValue: data.avg_negotiation_rounds,
        format: (n: number) => n.toFixed(1),
        delta: formatDelta(
          data.avg_negotiation_rounds,
          prior?.avg_negotiation_rounds ?? 0,
        ),
        upIsGood: false,
        Icon: RefreshIcon,
        tone: "warning",
        sparkKey: "calls",
      },
    ],
    [data, prior],
  );

  return (
    <div
      data-testid="kpi-bar"
      className="grid grid-cols-2 gap-4 sm:grid-cols-2 md:grid-cols-4"
    >
      {kpis.map((kpi) => (
        <KpiCard
          key={kpi.key}
          spec={kpi}
          loading={loading}
          points={points}
        />
      ))}
    </div>
  );
}

interface KpiCardProps {
  spec: KpiSpec;
  loading?: boolean;
  points: components["schemas"]["TimeseriesPoint"][];
}

function KpiCard({ spec, loading, points }: KpiCardProps) {
  const animated = useCountUp(spec.rawValue, 800);
  const display = spec.format(animated);
  const deltaTone = deltaToneClasses(spec.delta.sign, spec.upIsGood);
  const toneCfg = toneStyles[spec.tone];
  const DeltaIcon =
    spec.delta.sign === "up"
      ? ArrowUpIcon
      : spec.delta.sign === "down"
        ? ArrowDownIcon
        : MinusIcon;

  return (
    <div
      className={clsx(
        "group relative overflow-hidden rounded-2xl",
        "glass-surface px-5 py-4 hover:-translate-y-0.5",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-2xl",
        "before:bg-[radial-gradient(ellipse_400px_180px_at_100%_0%,rgba(255,255,255,0.04),transparent_60%)]",
        loading && "opacity-80",
      )}
    >
      <div className="relative z-10 flex items-start justify-between gap-3">
        <div
          className={clsx(
            "flex h-7 w-7 items-center justify-center rounded-lg ring-1 ring-inset",
            toneCfg.icon,
          )}
        >
          <spec.Icon size={14} />
        </div>
        <span
          className={clsx(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
            "text-[10px] font-semibold tabular-nums ring-1 ring-inset",
            deltaTone.bg,
            deltaTone.fg,
            deltaTone.ring,
          )}
        >
          <DeltaIcon size={10} />
          {spec.delta.text}
        </span>
      </div>
      <p className="relative z-10 mt-3 text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">
        {spec.label}
      </p>
      <p className="relative z-10 mt-1 num-mono text-4xl font-semibold leading-none tracking-tight tabular-nums text-slate-50">
        {display}
      </p>
      <p className="relative z-10 mt-1 text-[10px] uppercase tracking-[0.14em] text-slate-600">
        vs prior period
      </p>
      <div className="relative z-10 mt-3 h-[44px]">
        <Sparkline
          points={points}
          accessor={spec.sparkKey}
          gradId={toneCfg.gradId}
          stops={toneCfg.gradStops}
        />
      </div>
    </div>
  );
}

interface SparklineProps {
  points: components["schemas"]["TimeseriesPoint"][];
  accessor: "calls" | "booked";
  gradId: string;
  stops: [string, string];
}

function Sparkline({ points, accessor, gradId, stops }: SparklineProps) {
  if (!points || points.length < 2) {
    return (
      <div className="flex h-full items-center justify-center text-[10px] text-slate-700">
        no trend data
      </div>
    );
  }
  return (
    <ParentSize>
      {({ width, height }) => {
        if (width === 0 || height === 0) return null;
        return (
          <SparkInner
            width={width}
            height={height}
            points={points}
            accessor={accessor}
            gradId={gradId}
            stops={stops}
          />
        );
      }}
    </ParentSize>
  );
}

interface SparkInnerProps extends SparklineProps {
  width: number;
  height: number;
}

function SparkInner({
  width,
  height,
  points,
  accessor,
  gradId,
  stops,
}: SparkInnerProps) {
  const data = useMemo(
    () => points.map((p, i) => ({ i, v: p[accessor], t: p.bucket_start })),
    [points, accessor],
  );
  const maxV = Math.max(1, ...data.map((d) => d.v));
  const xs = useMemo(
    () =>
      scaleLinear<number>({
        domain: [0, data.length - 1],
        range: [0, width],
      }),
    [data.length, width],
  );
  const ys = useMemo(
    () =>
      scaleLinear<number>({
        domain: [0, maxV * 1.1],
        range: [height - 2, 2],
      }),
    [maxV, height],
  );

  // Voronoi for cursor lookup. Cheap to rebuild — sparklines have <= ~200 pts.
  const vor = useMemo(() => {
    const layout = buildVoronoi<{ i: number; v: number; t: string }>({
      x: (d) => xs(d.i),
      y: (d) => ys(d.v),
      width,
      height,
    });
    return layout(data);
  }, [data, xs, ys, width, height]);

  const [hover, setHover] = useState<{
    i: number;
    v: number;
    t: string;
    x: number;
    y: number;
  } | null>(null);

  const handleMove = useCallback(
    (e: React.MouseEvent<SVGRectElement>) => {
      const p = localPoint(e);
      if (!p) return;
      const hit = vor.find(p.x, p.y, 40);
      if (!hit) {
        setHover(null);
        return;
      }
      setHover({
        i: hit.data.i,
        v: hit.data.v,
        t: hit.data.t,
        x: xs(hit.data.i),
        y: ys(hit.data.v),
      });
    },
    [vor, xs, ys],
  );

  const tooltipDate = useMemo(() => {
    if (!hover) return null;
    const d = new Date(hover.t);
    if (Number.isNaN(d.getTime())) return null;
    const h = d.getUTCHours();
    return `${String(h).padStart(2, "0")}:00`;
  }, [hover]);

  return (
    <div className="relative h-full w-full">
      <svg width={width} height={height}>
        <LinearGradient
          id={gradId}
          from={stops[0]}
          to={stops[1]}
          vertical={false}
        />
        <LinearGradient
          id={`${gradId}-area`}
          from={stops[0]}
          to={stops[1]}
          fromOpacity={0.18}
          toOpacity={0}
          vertical
        />
        <AreaClosed
          data={data}
          x={(d) => xs(d.i) ?? 0}
          y={(d) => ys(d.v) ?? 0}
          yScale={ys}
          fill={`url(#${gradId}-area)`}
          curve={curveMonotoneX}
        />
        <LinePath
          data={data}
          x={(d) => xs(d.i) ?? 0}
          y={(d) => ys(d.v) ?? 0}
          stroke={`url(#${gradId})`}
          strokeWidth={1.75}
          strokeLinecap="round"
          curve={curveMonotoneX}
        />
        {hover && (
          <g pointerEvents="none">
            <line
              x1={hover.x}
              x2={hover.x}
              y1={0}
              y2={height}
              stroke="rgba(255,255,255,0.18)"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <circle
              cx={hover.x}
              cy={hover.y}
              r={2.6}
              fill={stops[1]}
              stroke="#0f172a"
              strokeWidth={1.2}
            />
          </g>
        )}
        <rect
          x={0}
          y={0}
          width={width}
          height={height}
          fill="transparent"
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      {hover && tooltipDate && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md border border-white/10 bg-slate-950/95 px-1.5 py-0.5 text-[10px] num-mono text-slate-100 shadow-xl shadow-black/60 backdrop-blur"
          style={{
            left: Math.max(20, Math.min(width - 20, hover.x)),
            top: Math.max(12, hover.y - 6),
          }}
        >
          {tooltipDate} · {hover.v}
        </div>
      )}
    </div>
  );
}
