// Small colored badge for outcomes / sentiments / equipment.
//
// Visual recipe (premium SaaS chip):
//   • Subtle gradient background (horizontal, low-alpha) for depth.
//   • Hairline border tinted with the chip color.
//   • 6px dot swatch on the left in the saturated color.
//   • Color = mid-stop hex; gradient stops come from `gradients.ts`.
import clsx from "clsx";
import type { components } from "@/types/api";
import {
  outcomeColors,
  outcomeLabels,
  sentimentColors,
  sentimentLabels,
  equipmentColors,
  equipmentLabels,
} from "@/lib/theme";
import {
  outcomeGradients,
  sentimentGradients,
  equipmentGradients,
  cssGradient,
  type GradientStop,
} from "@/lib/gradients";

type CallOutcome = components["schemas"]["CallOutcome"];
type CarrierSentiment = components["schemas"]["CarrierSentiment"];
type EquipmentType = components["schemas"]["EquipmentType"];

interface ChipProps {
  color: string;
  gradient?: GradientStop;
  label: string;
  className?: string;
}

export function Chip({ color, gradient, label, className }: ChipProps) {
  const bg = gradient
    ? cssGradient(gradient, 90, 0.18)
    : `${color}26`;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5",
        "text-[11px] font-medium leading-5",
        className,
      )}
      style={{
        borderColor: `${color}55`,
        background: bg,
        color,
      }}
    >
      <span
        aria-hidden
        className="h-1.5 w-1.5 rounded-full"
        style={{
          backgroundColor: color,
          boxShadow: `0 0 0 1px ${color}40, 0 0 6px ${color}80`,
        }}
      />
      {label}
    </span>
  );
}

export function OutcomeChip({ outcome }: { outcome: CallOutcome }) {
  return (
    <Chip
      color={outcomeColors[outcome]}
      gradient={outcomeGradients[outcome]}
      label={outcomeLabels[outcome]}
    />
  );
}

export function SentimentChip({ sentiment }: { sentiment: CarrierSentiment }) {
  return (
    <Chip
      color={sentimentColors[sentiment]}
      gradient={sentimentGradients[sentiment]}
      label={sentimentLabels[sentiment]}
    />
  );
}

export function EquipmentChip({ equipment }: { equipment: EquipmentType }) {
  return (
    <Chip
      color={equipmentColors[equipment]}
      gradient={equipmentGradients[equipment]}
      label={equipmentLabels[equipment]}
    />
  );
}
