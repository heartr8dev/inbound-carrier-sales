// Shared color palette + chart-token theme so every visx chart speaks the same
// visual language as the surrounding Tailwind UI.
//
// Solid colors here back-stop the gradient defs in `gradients.ts`: a chart
// will use a gradient `url(#…)` for fill but still uses solid tokens here for
// strokes, axis ticks, dots and legends.
import type { components } from "@/types/api";

type CallOutcome = components["schemas"]["CallOutcome"];
type CarrierSentiment = components["schemas"]["CarrierSentiment"];
type EquipmentType = components["schemas"]["EquipmentType"];

export const theme = {
  // Surfaces
  bgBase: "#020617", // slate-950
  bgCard: "rgba(15, 23, 42, 0.4)", // slate-900/40 — glassmorphic
  bgCardSolid: "#0f172a", // slate-900
  border: "rgba(255, 255, 255, 0.06)", // hairline
  borderStrong: "rgba(255, 255, 255, 0.12)",

  // Text
  textPrimary: "#f8fafc", // slate-50
  textSecondary: "#cbd5e1", // slate-300
  textMuted: "#64748b", // slate-500
  textDim: "#475569", // slate-600

  // Semantic — saturated mid-stops so 1-color charts feel solid.
  positive: "#10b981", // emerald-500
  positiveDim: "#065f46", // emerald-800
  negative: "#f43f5e", // rose-500
  negativeDim: "#9f1239", // rose-800
  neutral: "#6366f1", // indigo-500
  neutralDim: "#3730a3", // indigo-800

  // Accents
  accent: "#06b6d4", // cyan-500
  warning: "#f59e0b", // amber-500
  highlight: "#a78bfa", // violet-400

  // Chart gridlines / axes — hairline whites instead of solid slate.
  axis: "rgba(255, 255, 255, 0.06)",
  axisLabel: "#94a3b8", // slate-400
  axisLabelMuted: "#64748b", // slate-500
  grid: "rgba(255, 255, 255, 0.05)",
  gridStrong: "rgba(255, 255, 255, 0.08)",
} as const;

// Categorical palette for n-way splits — kept for legacy chip backstops.
export const categorical = [
  theme.neutral,
  theme.positive,
  theme.accent,
  theme.highlight,
  theme.warning,
  theme.negative,
  "#ec4899", // pink-500
  "#84cc16", // lime-500
];

export const outcomeColors: Record<CallOutcome, string> = {
  booked: theme.positive,
  transferred_to_rep: theme.neutral,
  no_matching_loads: theme.warning,
  carrier_declined_rate: theme.highlight,
  carrier_failed_vetting: theme.negative,
  negotiation_stalled: "#ec4899",
  carrier_hung_up: theme.textMuted,
};

export const sentimentColors: Record<CarrierSentiment, string> = {
  positive: theme.positive,
  neutral: theme.neutral,
  skeptical: theme.warning,
  frustrated: "#fb923c", // orange-400
  hostile: theme.negative,
};

export const equipmentColors: Record<EquipmentType, string> = {
  dry_van: theme.neutral,
  reefer: theme.accent,
  flatbed: theme.warning,
  step_deck: theme.highlight,
  power_only: "#84cc16",
};

export const outcomeLabels: Record<CallOutcome, string> = {
  booked: "Booked",
  transferred_to_rep: "Transferred",
  no_matching_loads: "No Match",
  carrier_declined_rate: "Declined",
  carrier_failed_vetting: "Failed Vetting",
  negotiation_stalled: "Stalled",
  carrier_hung_up: "Hung Up",
};

export const sentimentLabels: Record<CarrierSentiment, string> = {
  positive: "Positive",
  neutral: "Neutral",
  skeptical: "Skeptical",
  frustrated: "Frustrated",
  hostile: "Hostile",
};

export const equipmentLabels: Record<EquipmentType, string> = {
  dry_van: "Dry Van",
  reefer: "Reefer",
  flatbed: "Flatbed",
  step_deck: "Step Deck",
  power_only: "Power Only",
};

// Typography scale tokens — purely advisory references to the Tailwind classes
// in use. Documenting here so changes stay coherent across components.
//
// display-2xl  → text-5xl font-semibold tracking-tight tabular-nums   (KPI hero)
// display-xl   → text-4xl font-semibold tracking-tight tabular-nums   (donut center)
// h1           → text-xl  font-semibold tracking-tight                (page title)
// h2           → text-sm  font-semibold tracking-tight                (card title)
// label        → text-xs  font-medium uppercase tracking-[0.14em]     (KPI label)
// micro        → text-[10px] uppercase tracking-[0.16em] text-slate-500
//
// Numeric values everywhere use `tabular-nums` so columns line up.
