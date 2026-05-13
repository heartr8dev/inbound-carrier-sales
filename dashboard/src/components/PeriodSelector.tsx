// Segmented period selector — Today / 7d / 30d / All.
//
// The active option is highlighted by a single absolutely-positioned “pill”
// that slides horizontally via a CSS transform transition. Each tab measures
// its own position with a ref so we don't need a layout library.
import clsx from "clsx";
import { useLayoutEffect, useRef, useState } from "react";
import type { components } from "@/types/api";

type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];

interface PeriodSelectorProps {
  value: MetricsPeriod;
  onPeriodChange: (next: MetricsPeriod) => void;
  className?: string;
}

const options: { value: MetricsPeriod; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "all", label: "All" },
];

export function PeriodSelector({
  value,
  onPeriodChange,
  className,
}: PeriodSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [pill, setPill] = useState<{ left: number; width: number } | null>(
    null,
  );

  useLayoutEffect(() => {
    const el = buttonRefs.current[value];
    const container = containerRef.current;
    if (!el || !container) return;
    const elRect = el.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    setPill({
      left: elRect.left - containerRect.left,
      width: elRect.width,
    });
  }, [value]);

  return (
    <div
      ref={containerRef}
      role="tablist"
      aria-label="Time period"
      className={clsx(
        "relative inline-flex items-center gap-0.5 rounded-xl border border-white/[0.06] bg-slate-900/60 p-1 backdrop-blur",
        className,
      )}
    >
      {pill && (
        <div
          aria-hidden
          className="absolute top-1 bottom-1 rounded-lg bg-gradient-to-br from-indigo-500/30 to-emerald-500/20 ring-1 ring-inset ring-white/10 shadow-[0_0_18px_-2px_rgba(99,102,241,0.45)] transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{
            transform: `translateX(${pill.left}px)`,
            width: pill.width,
          }}
        />
      )}
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            ref={(el) => {
              buttonRefs.current[option.value] = el;
            }}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onPeriodChange(option.value)}
            className={clsx(
              "relative z-10 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              active
                ? "text-white"
                : "text-slate-400 hover:text-slate-200",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
