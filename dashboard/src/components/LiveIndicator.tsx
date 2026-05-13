// Header live-connection indicator.
//
// Three states the dashboard cares about:
//   * Live  — SSE stream is open. Green dot + slow pulse + ring animation,
//             label "Live · Updated {N}s ago" or "Just now".
//   * Connecting — initial / reconnecting. Amber dot, label "Connecting…".
//   * Polling fallback — SSE has been closed for a while; we fall back to
//             the 30s TanStack polling. Slate dot, label "Polling".
//
// The event count badge ("47 events") sits next to the indicator and resets
// on page reload — it's a "I see it, it's alive" signal during demos.
import { useEffect, useState } from "react";
import { formatRelativeTime } from "@/lib/formatters";
import type { LiveState } from "@/hooks/useLiveEvents";

interface LiveIndicatorProps {
  state: LiveState;
  lastEventTs: number | null;
  eventCount: number;
  /** ms since the EventSource closed; used to decide when to flip from
   *  "Connecting" → "Polling fallback". null when not closed. */
  closedSinceMs?: number | null;
}

export function LiveIndicator({
  state,
  lastEventTs,
  eventCount,
}: LiveIndicatorProps) {
  // Trigger a re-render every 15s so "Updated 12s ago" stays fresh without
  // anything else having to invalidate.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 15_000);
    return () => window.clearInterval(id);
  }, []);

  // Polling-fallback heuristic: SSE closed and we haven't recovered after
  // a short grace window. The actual recovery loop is in useLiveEvents.
  const [closedFor, setClosedFor] = useState<number>(0);
  useEffect(() => {
    if (state !== "closed") {
      setClosedFor(0);
      return;
    }
    const start = Date.now();
    const id = window.setInterval(() => {
      setClosedFor(Date.now() - start);
    }, 500);
    return () => window.clearInterval(id);
  }, [state]);

  const isLive = state === "open";
  const isPollingFallback = state === "closed" && closedFor > 5_000;

  // Pick dot + label colors.
  const dotColor = isLive
    ? "bg-emerald-400"
    : isPollingFallback
      ? "bg-slate-400"
      : "bg-amber-400";
  const ringClass = isLive ? "animate-pulse-ring" : "";

  let label: string;
  if (isLive) {
    if (lastEventTs == null) {
      label = "Live";
    } else {
      const ageMs = Date.now() - lastEventTs;
      if (ageMs < 4_000) label = "Live · Just now";
      else label = `Live · ${formatRelativeTime(new Date(lastEventTs))}`;
    }
  } else if (isPollingFallback) {
    label = "Polling";
  } else {
    label = "Connecting…";
  }

  const textTone = isLive
    ? "text-emerald-200"
    : isPollingFallback
      ? "text-slate-300"
      : "text-amber-200";

  return (
    <div
      className="hidden items-center gap-2 rounded-full border border-white/[0.06] bg-white/[0.02] px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] sm:flex"
      role="status"
      aria-live="polite"
      aria-label={`Connection state: ${label}`}
    >
      <span className="relative flex h-2 w-2 items-center justify-center">
        {isLive && (
          <span
            className={`absolute h-2 w-2 ${ringClass} rounded-full ${dotColor}`}
          />
        )}
        <span
          className={`relative h-1.5 w-1.5 rounded-full ${dotColor} ${
            isLive
              ? "shadow-[0_0_6px_rgba(16,185,129,0.6)] animate-pulse-soft"
              : ""
          }`}
        />
      </span>
      <span className={textTone}>{label}</span>
      {eventCount > 0 && (
        <span className="ml-1 rounded-full bg-white/[0.05] px-1.5 py-0.5 font-mono text-[9px] tracking-normal text-slate-300">
          {eventCount}
          <span className="ml-1 text-slate-500">evt</span>
        </span>
      )}
    </div>
  );
}
