// Bottom-right glass toast that pops in when a new call event arrives.
//
// Stays for 2.5s, then fades out. Multiple events stack vertically with
// stagger. Honors prefers-reduced-motion: skips slide/fade and just appears
// momentarily.
import { useEffect, useState } from "react";
import type { LiveEvent } from "@/hooks/useLiveEvents";

interface LiveEventToastProps {
  events: LiveEvent[];
  onDismiss: (call_id: string) => void;
}

const DISPLAY_MS = 2_500;

const OUTCOME_LABEL: Record<string, string> = {
  booked: "Booked",
  transferred_to_rep: "Transferred",
  no_matching_loads: "No match",
  carrier_declined_rate: "Rate declined",
  carrier_failed_vetting: "Vetting failed",
  negotiation_stalled: "Stalled",
  carrier_hung_up: "Hung up",
};

const OUTCOME_TONE: Record<string, string> = {
  booked: "border-emerald-400/40 bg-emerald-500/10 text-emerald-200",
  transferred_to_rep: "border-sky-400/40 bg-sky-500/10 text-sky-200",
  no_matching_loads: "border-slate-400/40 bg-slate-500/10 text-slate-200",
  carrier_declined_rate: "border-amber-400/40 bg-amber-500/10 text-amber-200",
  carrier_failed_vetting: "border-rose-400/40 bg-rose-500/10 text-rose-200",
  negotiation_stalled: "border-fuchsia-400/40 bg-fuchsia-500/10 text-fuchsia-200",
  carrier_hung_up: "border-slate-400/40 bg-slate-500/10 text-slate-300",
};

export function LiveEventToast({ events, onDismiss }: LiveEventToastProps) {
  // Auto-dismiss each event after DISPLAY_MS. Keying on call_id avoids
  // re-scheduling for the same toast on re-renders.
  useEffect(() => {
    const ids = events.map((e) => e.data.call_id).filter(Boolean) as string[];
    const timers = ids.map((id) =>
      window.setTimeout(() => onDismiss(id), DISPLAY_MS),
    );
    return () => {
      for (const t of timers) window.clearTimeout(t);
    };
  }, [events, onDismiss]);

  if (events.length === 0) return null;

  // Respect reduced motion: render a tighter, animation-free variant.
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-30 flex flex-col-reverse gap-2"
      aria-live="polite"
    >
      {events.slice(0, 4).map((evt) => {
        const outcome = (evt.data.outcome as string | undefined) ?? "unknown";
        const label = OUTCOME_LABEL[outcome] ?? outcome;
        const tone = OUTCOME_TONE[outcome] ?? OUTCOME_TONE.no_matching_loads;
        const company =
          (evt.data.carrier_company as string | null | undefined) ??
          (evt.data.carrier_mc ? `MC ${evt.data.carrier_mc}` : "Carrier");
        return (
          <Toast
            key={(evt.data.call_id as string | undefined) ?? `evt-${evt.ts}`}
            label={label}
            company={company}
            tone={tone}
            reduceMotion={reduceMotion}
          />
        );
      })}
    </div>
  );
}

function Toast({
  label,
  company,
  tone,
  reduceMotion,
}: {
  label: string;
  company: string;
  tone: string;
  reduceMotion: boolean;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // Defer one frame so the enter transition has a "from" state to animate.
    const id = window.requestAnimationFrame(() => setMounted(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  return (
    <div
      className={[
        "pointer-events-auto flex items-center gap-2 rounded-xl border px-3 py-2 text-xs shadow-glass backdrop-blur-xl",
        tone,
        reduceMotion
          ? "opacity-100"
          : "transform transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
        !reduceMotion && (mounted ? "translate-x-0 opacity-100" : "translate-x-4 opacity-0"),
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em]">
        {label}
      </span>
      <span className="text-slate-100/70">·</span>
      <span className="max-w-[180px] truncate text-slate-100">{company}</span>
    </div>
  );
}
