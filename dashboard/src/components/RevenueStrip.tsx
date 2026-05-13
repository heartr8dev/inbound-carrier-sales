// Revenue summary — three KPI tiles plus a stacked horizontal beam.
//
// The beam was previously two side-by-side bars (loadboard vs booked); it's
// now a single full-width strip broken into segments:
//
//   FLOOR  →  PRESERVED MARGIN  →  BOOKED RATE  ─  GAP  ─  LOADBOARD CAP
//   (slate)    (emerald)            (cyan)         (rose)  (transparent)
//
// At a glance you can see how much margin the AI agent preserved versus the
// loadboard "anchor". Gradient stops, mono numerals, hover-glow.
import { useMemo, useState } from "react";
import type { components } from "@/types/api";
import { formatCurrency, formatPercent, toNumber } from "@/lib/formatters";

type RevenueSection = components["schemas"]["RevenueSection"];

interface RevenueStripProps {
  data: RevenueSection;
}

interface TileSpec {
  label: string;
  value: string;
  sub?: string;
  tone: "neutral" | "positive" | "accent";
}

const toneClasses: Record<TileSpec["tone"], string> = {
  neutral: "text-slate-100",
  positive:
    "text-transparent bg-clip-text bg-gradient-to-br from-emerald-300 to-emerald-500",
  accent:
    "text-transparent bg-clip-text bg-gradient-to-br from-cyan-300 to-cyan-500",
};

const toneRing: Record<TileSpec["tone"], string> = {
  neutral: "ring-white/[0.06]",
  positive: "ring-emerald-500/15",
  accent: "ring-cyan-500/15",
};

export function RevenueStrip({ data }: RevenueStripProps) {
  const loadboard = toNumber(data.avg_loadboard_rate);
  const booked = toNumber(data.avg_booked_rate);
  const marginPct = data.avg_margin_preserved_pct;
  const savings = loadboard - booked;

  const cards = useMemo<TileSpec[]>(
    () => [
      {
        label: "Avg Loadboard Rate",
        value: formatCurrency(loadboard),
        tone: "neutral",
      },
      {
        label: "Avg Booked Rate",
        value: formatCurrency(booked),
        tone: "positive",
      },
      {
        label: "Margin Preserved",
        value: formatPercent(marginPct),
        sub: savings > 0 ? `${formatCurrency(savings)} avg saved` : undefined,
        tone: "accent",
      },
    ],
    [loadboard, booked, marginPct, savings],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3">
        {cards.map((c) => (
          <div
            key={c.label}
            className={`rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 ring-1 ring-inset ${toneRing[c.tone]}`}
          >
            <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
              {c.label}
            </p>
            <p
              className={`mt-1.5 text-2xl font-semibold tabular-nums leading-none num-mono ${toneClasses[c.tone]}`}
            >
              {c.value}
            </p>
            {c.sub && (
              <p className="mt-1.5 text-[10px] uppercase tracking-[0.08em] text-slate-500">
                {c.sub}
              </p>
            )}
          </div>
        ))}
      </div>

      <RateBeam loadboard={loadboard} booked={booked} marginPct={marginPct} />
    </div>
  );
}

interface RateBeamProps {
  loadboard: number;
  booked: number;
  marginPct: number;
}

/**
 * A single full-width beam that splits the loadboard rate into:
 *   • Floor (lower bound of acceptable agent offers — taken as 80% loadboard)
 *   • Preserved margin (booked - floor)
 *   • Gap (loadboard - booked — what the carrier walked away with)
 *
 * Even when the floor isn't defined explicitly we still get a clean
 * stacked view because the segments are proportional, not absolute.
 */
function RateBeam({ loadboard, booked, marginPct }: RateBeamProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  if (loadboard <= 0) {
    return (
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-6 text-xs text-slate-500">
        Loadboard rate unavailable.
      </div>
    );
  }
  const floor = loadboard * 0.78; // visual baseline; the agent's "won't go below"
  const preservedMargin = Math.max(0, booked - floor);
  const gap = Math.max(0, loadboard - booked);
  const segments = [
    {
      key: "floor",
      label: "Floor",
      width: floor,
      gradient: "linear-gradient(90deg,#475569,#334155)",
      glow: "rgba(100,116,139,0.4)",
      text: formatCurrency(floor),
    },
    {
      key: "margin",
      label: "Preserved margin",
      width: preservedMargin,
      gradient: "linear-gradient(90deg,#34d399,#10b981)",
      glow: "rgba(16,185,129,0.5)",
      text: formatCurrency(preservedMargin),
    },
    {
      key: "booked",
      label: "Booked rate",
      width: 0.001 * loadboard, // razor line that marks where booked sits
      gradient: "linear-gradient(90deg,#67e8f9,#06b6d4)",
      glow: "rgba(6,182,212,0.7)",
      text: formatCurrency(booked),
      isMarker: true,
    },
    {
      key: "gap",
      label: "Gap to loadboard",
      width: gap,
      gradient:
        "linear-gradient(90deg,rgba(244,63,94,0.45),rgba(244,63,94,0.08))",
      glow: "rgba(244,63,94,0.5)",
      text: gap > 0 ? `−${formatCurrency(gap)}` : "—",
    },
  ];
  const total = segments.reduce((s, x) => s + x.width, 0);

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
      <div className="mb-1.5 flex items-center justify-between text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
        <span>Rate split</span>
        <span className="num-mono text-slate-300">
          loadboard {formatCurrency(loadboard)}
        </span>
      </div>
      <div className="relative h-9 overflow-hidden rounded-lg border border-white/[0.04] bg-slate-950/40">
        {(() => {
          let acc = 0;
          return segments.map((seg) => {
            const pct = (seg.width / total) * 100;
            const left = (acc / total) * 100;
            acc += seg.width;
            const isHov = hovered === seg.key;
            return (
              <div
                key={seg.key}
                onMouseEnter={() => setHovered(seg.key)}
                onMouseLeave={() => setHovered(null)}
                className="absolute top-0 h-full"
                style={{
                  left: `${left}%`,
                  width: `${pct}%`,
                  background: seg.gradient,
                  boxShadow: isHov ? `0 0 14px ${seg.glow}` : undefined,
                  transition: "box-shadow 200ms ease",
                  cursor: "pointer",
                }}
              />
            );
          });
        })()}
        {/* Booked-rate marker line */}
        <div
          aria-hidden
          className="pointer-events-none absolute top-0 h-full w-px"
          style={{
            left: `${((floor + preservedMargin) / total) * 100}%`,
            background:
              "linear-gradient(180deg,rgba(255,255,255,0.7),rgba(255,255,255,0.15))",
            boxShadow: "0 0 6px rgba(255,255,255,0.6)",
          }}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] uppercase tracking-[0.1em] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: "linear-gradient(135deg,#475569,#334155)" }}
          />
          Floor {formatCurrency(floor)}
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: "linear-gradient(135deg,#34d399,#059669)" }}
          />
          Margin <span className="num-mono text-emerald-200">
            {formatPercent(marginPct, 1)}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: "linear-gradient(135deg,#67e8f9,#06b6d4)" }}
          />
          Booked <span className="num-mono text-cyan-200">
            {formatCurrency(booked)}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{
              background:
                "linear-gradient(135deg,rgba(244,63,94,0.6),rgba(244,63,94,0.15))",
            }}
          />
          Gap <span className="num-mono text-rose-200">
            {gap > 0 ? formatCurrency(gap) : "—"}
          </span>
        </span>
      </div>
    </div>
  );
}
