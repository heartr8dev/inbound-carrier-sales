// 24-hour stacked-area call volume timeline with hover tooltip.
// Ported from /tmp/acme-design/acme-dash/project/charts.jsx CallTimeline.
import { useEffect, useRef, useState } from "react";
import type { HourBucket } from "@/lib/agg";

function useMeasure() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ w: width, h: height });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

export function CallTimeline({ hourly }: { hourly: HourBucket[] }) {
  const [ref, { w }] = useMeasure();
  const width = w || 600;
  const height = 220;
  const padL = 36;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const xs = hourly.map((_, i) => padL + (i / 23) * innerW);
  const maxCalls = Math.max(...hourly.map((h) => h.calls), 1);
  const yScale = (v: number) => padT + innerH - (v / maxCalls) * innerH;

  const buildArea = (key: "calls" | "booked") => {
    let path = `M ${xs[0]} ${padT + innerH}`;
    hourly.forEach((h, i) => {
      path += ` L ${xs[i]} ${yScale(h[key])}`;
    });
    path += ` L ${xs[xs.length - 1]} ${padT + innerH} Z`;
    return path;
  };
  const buildLine = (key: "calls" | "booked") => {
    let path = "";
    hourly.forEach((h, i) => {
      path += (i === 0 ? "M " : " L ") + xs[i] + " " + yScale(h[key]);
    });
    return path;
  };

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((p) => ({
    v: Math.round(maxCalls * p),
    y: yScale(maxCalls * p),
  }));

  const xTicks = [0, 4, 8, 12, 16, 20, 23].map((h) => ({
    label: h.toString().padStart(2, "0") + ":00",
    x: padL + (h / 23) * innerW,
  }));

  const [hover, setHover] = useState<number | null>(null);

  return (
    <div ref={ref} style={{ width: "100%", position: "relative" }}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const i = Math.round(((x - padL) / innerW) * 23);
          if (i >= 0 && i < 24) setHover(i);
        }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="calls-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="booked-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--good)" stopOpacity="0.55" />
            <stop offset="100%" stopColor="var(--good)" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={padL}
              x2={width - padR}
              y1={t.y}
              y2={t.y}
              stroke="var(--grid)"
              strokeDasharray={i === 0 ? undefined : "2 3"}
            />
            <text
              x={padL - 8}
              y={t.y + 4}
              textAnchor="end"
              fontSize="11"
              fill="var(--fg-3)"
              fontFamily="var(--font-mono)"
            >
              {t.v}
            </text>
          </g>
        ))}
        <path d={buildArea("calls")} fill="url(#calls-fill)" />
        <path d={buildLine("calls")} fill="none" stroke="var(--brand)" strokeWidth="1.6" strokeLinejoin="round" />
        <path d={buildArea("booked")} fill="url(#booked-fill)" />
        <path d={buildLine("booked")} fill="none" stroke="var(--good)" strokeWidth="1.6" strokeLinejoin="round" />
        {xTicks.map((t, i) => (
          <text
            key={i}
            x={t.x}
            y={height - 8}
            textAnchor="middle"
            fontSize="11"
            fill="var(--fg-3)"
            fontFamily="var(--font-mono)"
          >
            {t.label}
          </text>
        ))}
        {hover !== null && (
          <g>
            <line
              x1={xs[hover]}
              x2={xs[hover]}
              y1={padT}
              y2={padT + innerH}
              stroke="var(--fg-3)"
              strokeDasharray="2 3"
              opacity="0.5"
            />
            <circle cx={xs[hover]} cy={yScale(hourly[hover].calls)} r="4" fill="var(--surface-1)" stroke="var(--brand)" strokeWidth="2" />
            <circle cx={xs[hover]} cy={yScale(hourly[hover].booked)} r="4" fill="var(--surface-1)" stroke="var(--good)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover !== null && (
        <div
          style={{
            position: "absolute",
            left: Math.min(xs[hover] + 12, width - 160),
            top: 12,
            background: "var(--surface-1)",
            padding: "10px 14px",
            borderRadius: "var(--r-2)",
            boxShadow: "var(--neu-raised-sm)",
            fontSize: 12,
            pointerEvents: "none",
            minWidth: 140,
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--fg-1)",
              fontWeight: 600,
              marginBottom: 4,
            }}
          >
            {hover.toString().padStart(2, "0")}:00 UTC
          </div>
          <div style={{ color: "var(--fg-3)" }}>
            Calls{" "}
            <span style={{ float: "right", color: "var(--fg-1)", fontFamily: "var(--font-mono)" }}>
              {hourly[hover].calls}
            </span>
          </div>
          <div style={{ color: "var(--fg-3)" }}>
            Booked{" "}
            <span style={{ float: "right", color: "var(--good)", fontFamily: "var(--font-mono)" }}>
              {hourly[hover].booked}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
