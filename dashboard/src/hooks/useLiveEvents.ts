// Live SSE event hook.
//
// Opens an EventSource against /api/v1/calls/stream and:
//   * Invalidates the relevant TanStack Query keys whenever a `call.created`
//     event lands so cards refresh without waiting for the 30s polling tick.
//   * Tracks connection state (connecting / open / closed) and lets callers
//     render a live indicator + reconnect badges.
//   * Reconnects with exponential backoff (1s → 30s cap) on transport errors,
//     and forces a reconnect when the tab returns from hidden (browsers
//     suspend EventSource on hidden tabs in some configurations).
//   * Buffers the most recent N events for a corner toast component.
//
// The polling fallback in useMetrics/useCalls/useOutcomesByBucket stays
// intact — SSE is additive. If the stream is down, the dashboard still
// updates every 30s.
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY ?? "devkey-please-change";

export type LiveState = "connecting" | "open" | "closed";

export interface LiveEvent {
  type: string;
  ts: number;
  data: {
    call_id?: string;
    outcome?: string;
    sentiment?: string;
    carrier_company?: string | null;
    carrier_mc?: string | null;
    load_id_discussed?: string | null;
    final_agreed_rate?: string | null;
    created_at?: string;
    [k: string]: unknown;
  };
}

export interface UseLiveEventsResult {
  state: LiveState;
  /** Most recent event or null if none yet. */
  lastEvent: LiveEvent | null;
  /** Recent events queue (newest first, capped). Used by the toast. */
  recent: LiveEvent[];
  /** Lifetime count of events received since mount / reload. */
  eventCount: number;
  /** Acknowledge a recent event so the toast removes it. */
  ackEvent: (call_id: string) => void;
}

const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;
const RECENT_CAP = 8;

function buildStreamUrl(): string {
  // The base is "/api/v1" in compose / prod and goes through nginx, which we
  // configured with proxy_buffering off for this endpoint. URL constructor
  // handles both absolute and relative bases.
  const url = new URL(`${API_BASE}/calls/stream`, window.location.origin);
  url.searchParams.set("api_key", API_KEY);
  return url.toString();
}

export function useLiveEvents(): UseLiveEventsResult {
  const queryClient = useQueryClient();
  const [state, setState] = useState<LiveState>("connecting");
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [recent, setRecent] = useState<LiveEvent[]>([]);
  const [eventCount, setEventCount] = useState(0);

  // Hold the active EventSource + the next backoff in refs so the connect
  // closure can re-run without re-binding everything.
  const sourceRef = useRef<EventSource | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<number | null>(null);
  const cancelledRef = useRef<boolean>(false);

  const ackEvent = useCallback((call_id: string) => {
    setRecent((prev) => prev.filter((e) => e.data.call_id !== call_id));
  }, []);

  const connect = useCallback(() => {
    if (cancelledRef.current) return;
    // Close any prior stream before opening a new one — paranoia against
    // browser quirks where two ES objects to the same URL coexist.
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    setState("connecting");
    const es = new EventSource(buildStreamUrl());
    sourceRef.current = es;

    es.addEventListener("open", () => {
      backoffRef.current = INITIAL_BACKOFF_MS;
      setState("open");
    });

    es.addEventListener("hello", () => {
      // Server-side ack the stream is up. We treat this the same as `open`
      // but it confirms the SSE response actually flushed through nginx.
      setState("open");
    });

    es.addEventListener("call.created", (evt) => {
      try {
        const parsed = JSON.parse((evt as MessageEvent).data) as {
          type?: string;
          ts?: string;
          data?: LiveEvent["data"];
        };
        const live: LiveEvent = {
          type: parsed.type ?? "call.created",
          ts: Date.now(),
          data: parsed.data ?? {},
        };
        setLastEvent(live);
        setEventCount((c) => c + 1);
        setRecent((prev) => {
          const next = [live, ...prev];
          return next.slice(0, RECENT_CAP);
        });
        // Refresh anything that summarises calls. invalidateQueries with a
        // partial key matches every variant (period, filters, etc.).
        queryClient.invalidateQueries({ queryKey: ["metrics"] });
        queryClient.invalidateQueries({ queryKey: ["calls"] });
        queryClient.invalidateQueries({ queryKey: ["outcomes-by-bucket"] });
      } catch (err) {
        // Don't blow up the SSE loop on a malformed frame — log + skip.
        console.warn("[useLiveEvents] failed to parse call.created", err);
      }
    });

    es.addEventListener("error", () => {
      // EventSource auto-reconnects with the browser's policy on transient
      // network blips, but it does not back off — so for hard errors (auth
      // rejected, server down) we close it ourselves and schedule an
      // exponential retry instead.
      if (es.readyState === EventSource.CLOSED) {
        setState("closed");
        scheduleReconnect();
      } else if (es.readyState === EventSource.CONNECTING) {
        setState("connecting");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient]);

  const scheduleReconnect = useCallback(() => {
    if (cancelledRef.current) return;
    if (reconnectTimerRef.current != null) return;
    const delay = backoffRef.current;
    backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    cancelledRef.current = false;
    connect();

    const onVisibility = () => {
      if (document.hidden) return;
      // Returning from hidden — if the connection is closed (or stuck
      // connecting), force a fresh attempt immediately.
      const es = sourceRef.current;
      if (!es || es.readyState !== EventSource.OPEN) {
        if (reconnectTimerRef.current != null) {
          window.clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
        backoffRef.current = INITIAL_BACKOFF_MS;
        connect();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelledRef.current = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [connect]);

  return { state, lastEvent, recent, eventCount, ackEvent };
}
