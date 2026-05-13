// Refined tooltip surface used by every chart.
//
// Built on @visx/tooltip's `TooltipWithBounds` for collision avoidance, but
// wrapped with a custom dark glass surface and CSS-keyframe fade-in.
import type { ReactNode } from "react";
import { TooltipWithBounds, defaultStyles } from "@visx/tooltip";
import clsx from "clsx";

interface ChartTooltipProps {
  top?: number;
  left?: number;
  children: ReactNode;
  className?: string;
}

const surfaceStyle: React.CSSProperties = {
  ...defaultStyles,
  background: "transparent",
  padding: 0,
  border: "none",
  boxShadow: "none",
  pointerEvents: "none",
};

export function ChartTooltip({
  top,
  left,
  children,
  className,
}: ChartTooltipProps) {
  return (
    <TooltipWithBounds top={top} left={left} style={surfaceStyle}>
      <div
        className={clsx(
          "animate-tooltip-in min-w-[120px] rounded-lg border border-white/10",
          "bg-slate-950/95 px-3 py-2 shadow-2xl shadow-black/60 backdrop-blur-md",
          "text-xs text-slate-100",
          className,
        )}
      >
        {children}
      </div>
    </TooltipWithBounds>
  );
}

interface TooltipRowProps {
  label: ReactNode;
  value: ReactNode;
  swatch?: string;
  swatchGradient?: string;
  emphasis?: boolean;
}

export function TooltipRow({
  label,
  value,
  swatch,
  swatchGradient,
  emphasis,
}: TooltipRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-0.5">
      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] text-slate-400">
        {(swatch || swatchGradient) && (
          <span
            aria-hidden
            className="h-2 w-2 rounded-full"
            style={{
              background: swatchGradient ?? swatch,
              boxShadow: `0 0 0 1px ${swatch ?? "rgba(255,255,255,0.15)"}`,
            }}
          />
        )}
        {label}
      </span>
      <span
        className={clsx(
          "tabular-nums",
          emphasis ? "text-sm font-semibold text-slate-50" : "text-xs text-slate-200",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function TooltipHeader({ children }: { children: ReactNode }) {
  return (
    <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
      {children}
    </p>
  );
}
