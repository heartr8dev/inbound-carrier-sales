// Shared multi-stop SVG gradient definitions.
//
// Each gradient is exposed three ways:
//  • `id` — stable string id you can reference with `url(#${id})` in any SVG.
//  • `from` / `to` — start and end hex stops, useful for CSS `linear-gradient()`
//    backgrounds (chips, pills, KPI tiles, etc).
//  • `<Defs />` — a single component that emits every `<linearGradient>` def
//    used by the dashboard. Mount once near the root so every chart can
//    reference them without re-declaring.
//
// Direction convention: vertical (top→bottom) for chart fills (area, bars,
// sankey nodes); horizontal for chips and segmented controls.
import type { components } from "@/types/api";

type CallOutcome = components["schemas"]["CallOutcome"];
type CarrierSentiment = components["schemas"]["CarrierSentiment"];
type EquipmentType = components["schemas"]["EquipmentType"];

export interface GradientStop {
  id: string;
  from: string;
  to: string;
  /** Optional mid-stop for tri-band gradients. */
  via?: string;
}

// Semantic gradients used across the whole dashboard.
export const gradients = {
  success: { id: "grad-success", from: "#34d399", via: "#10b981", to: "#059669" }, // emerald 400→600
  danger: { id: "grad-danger", from: "#fb7185", via: "#f43f5e", to: "#e11d48" }, // rose 400→600
  warning: { id: "grad-warning", from: "#fbbf24", via: "#f59e0b", to: "#d97706" }, // amber 400→600
  info: { id: "grad-info", from: "#818cf8", via: "#6366f1", to: "#4f46e5" }, // indigo 400→600
  neutral: { id: "grad-neutral", from: "#94a3b8", via: "#64748b", to: "#475569" }, // slate 400→600
  // Hero gradient used for KPI numbers / brand mark.
  brand: { id: "grad-brand", from: "#a5b4fc", via: "#818cf8", to: "#34d399" },
  // Accent gradient for sentiment / cyan-leaning charts.
  accent: { id: "grad-accent", from: "#67e8f9", via: "#22d3ee", to: "#0891b2" },
} as const satisfies Record<string, GradientStop>;

// Categorical 5-stop palette for outcome donuts and Sankey segments.
// Tuned to feel elegant rather than primary-saturated — desaturated jewels.
export const categoricalGradients: GradientStop[] = [
  { id: "grad-cat-0", from: "#a5b4fc", to: "#6366f1" }, // periwinkle
  { id: "grad-cat-1", from: "#5eead4", to: "#0d9488" }, // teal
  { id: "grad-cat-2", from: "#fcd34d", to: "#d97706" }, // amber
  { id: "grad-cat-3", from: "#f0abfc", to: "#a21caf" }, // fuchsia
  { id: "grad-cat-4", from: "#fda4af", to: "#be123c" }, // rose
];

// Sequential viridis-ish gradient for the sentiment heatmap. Five stops feel
// rich without being noisy.
export const sequentialStops = [
  { offset: "0%", color: "#0f172a", opacity: 1 }, // slate-900 (empty cell)
  { offset: "12%", color: "#1e293b", opacity: 1 }, // slate-800
  { offset: "30%", color: "#312e81", opacity: 1 }, // indigo-900
  { offset: "55%", color: "#6366f1", opacity: 1 }, // indigo-500
  { offset: "78%", color: "#22d3ee", opacity: 1 }, // cyan-400
  { offset: "100%", color: "#5eead4", opacity: 1 }, // teal-300
];

// Per-outcome gradient assignment for chips and Sankey.
export const outcomeGradients: Record<CallOutcome, GradientStop> = {
  booked: gradients.success,
  transferred_to_rep: gradients.info,
  no_matching_loads: gradients.warning,
  carrier_declined_rate: categoricalGradients[3],
  carrier_failed_vetting: gradients.danger,
  negotiation_stalled: categoricalGradients[4],
  carrier_hung_up: gradients.neutral,
};

export const sentimentGradients: Record<CarrierSentiment, GradientStop> = {
  positive: gradients.success,
  neutral: gradients.info,
  skeptical: gradients.warning,
  frustrated: categoricalGradients[2],
  hostile: gradients.danger,
};

export const equipmentGradients: Record<EquipmentType, GradientStop> = {
  dry_van: gradients.info,
  reefer: gradients.accent,
  flatbed: gradients.warning,
  step_deck: categoricalGradients[3],
  power_only: categoricalGradients[1],
};

/** Stable id for the sequential heatmap gradient. */
export const sequentialGradientId = "grad-sequential";

/** Stable id for the page-level background radial glow. */
export const backgroundGlowId = "grad-bg-glow";

/**
 * Page-wide SVG `<defs>` that emit every gradient used in the dashboard.
 * Rendered once at the App root and referenced by id from every chart.
 */
export function GradientDefs() {
  const all: GradientStop[] = [
    ...Object.values(gradients),
    ...categoricalGradients,
  ];
  return (
    <svg
      aria-hidden
      width={0}
      height={0}
      style={{ position: "absolute", pointerEvents: "none" }}
    >
      <defs>
        {all.map((g) => (
          <linearGradient
            key={g.id}
            id={g.id}
            x1="0%"
            y1="0%"
            x2="0%"
            y2="100%"
          >
            <stop offset="0%" stopColor={g.from} />
            {g.via && <stop offset="50%" stopColor={g.via} />}
            <stop offset="100%" stopColor={g.to} />
          </linearGradient>
        ))}
        {/* Horizontal-rotation variants for chip pills */}
        {all.map((g) => (
          <linearGradient
            key={`${g.id}-h`}
            id={`${g.id}-h`}
            x1="0%"
            y1="0%"
            x2="100%"
            y2="0%"
          >
            <stop offset="0%" stopColor={g.from} />
            {g.via && <stop offset="50%" stopColor={g.via} />}
            <stop offset="100%" stopColor={g.to} />
          </linearGradient>
        ))}
        {/* Sequential heatmap gradient */}
        <linearGradient
          id={sequentialGradientId}
          x1="0%"
          y1="100%"
          x2="0%"
          y2="0%"
        >
          {sequentialStops.map((s) => (
            <stop
              key={s.offset}
              offset={s.offset}
              stopColor={s.color}
              stopOpacity={s.opacity}
            />
          ))}
        </linearGradient>
      </defs>
    </svg>
  );
}

/**
 * Helper for CSS gradient strings (chips, pill backgrounds, button surfaces).
 */
export function cssGradient(
  g: GradientStop,
  angle = 135,
  opacity = 1,
): string {
  if (opacity >= 1) {
    return `linear-gradient(${angle}deg, ${g.from}, ${g.to})`;
  }
  return `linear-gradient(${angle}deg, ${g.from}${opacityHex(opacity)}, ${g.to}${opacityHex(opacity)})`;
}

function opacityHex(o: number): string {
  const v = Math.round(Math.max(0, Math.min(1, o)) * 255);
  return v.toString(16).padStart(2, "0");
}
