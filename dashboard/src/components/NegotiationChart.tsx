// Grouped bars (agreed / walked) + dashed avg-discount line overlay.
import { useEffect, useRef, useState } from "react";
import type { RoundBucket } from "@/lib/agg";

function useMeasure() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

export function NegotiationChart({ byRound }: { byRound: RoundBucket[] }) {
  const [ref, { w }] = useMeasure();
  const width = w || 400;
  const height = 220;
  const padL = 36;
  const padR = 36;
  const padT = 20;
  const padB = 32;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const groupW = innerW / Math.max(1, byRound.length);
  const barW = Math.min(28, groupW * 0.32);
  const maxCount = Math.max(...byRound.flatMap((r) => [r.agreed, r.walked]), 1);
  const maxPct = Math.max(...byRound.map((r) => r.avgDiscount), 0.01);

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {[0, 0.5, 1].map((p, i) => (
          <line
            key={i}
            x1={padL}
            x2={width - padR}
            y1={padT + innerH - p * innerH}
            y2={padT + innerH - p * innerH}
            stroke="var(--grid)"
            strokeDasharray={i === 0 ? undefined : "2 3"}
          />
        ))}
        {byRound.map((r, i) => {
          const gx = padL + i * groupW + groupW / 2;
          const agreedH = (r.agreed / maxCount) * innerH;
          const walkedH = (r.walked / maxCount) * innerH;
          return (
            <g key={i}>
              <rect
                x={gx - barW - 2}
                y={padT + innerH - agreedH}
                width={barW}
                height={agreedH}
                fill="var(--good)"
                rx="3"
                opacity="0.85"
              />
              <rect
                x={gx + 2}
                y={padT + innerH - walkedH}
                width={barW}
                height={walkedH}
                fill="var(--warn)"
                rx="3"
                opacity="0.85"
              />
              <text
                x={gx - barW / 2 - 2}
                y={padT + innerH - agreedH - 6}
                textAnchor="middle"
                fontSize="11"
                fill="var(--fg-2)"
                fontFamily="var(--font-mono)"
              >
                {r.agreed}
              </text>
              <text
                x={gx + barW / 2 + 2}
                y={padT + innerH - walkedH - 6}
                textAnchor="middle"
                fontSize="11"
                fill="var(--fg-2)"
                fontFamily="var(--font-mono)"
              >
                {r.walked}
              </text>
              <text
                x={gx}
                y={height - 14}
                textAnchor="middle"
                fontSize="11"
                fill="var(--fg-3)"
                fontFamily="var(--font-sans)"
                fontWeight="600"
                letterSpacing="0.14em"
              >
                R{r.round}
              </text>
            </g>
          );
        })}
        <path
          d={byRound
            .map((r, i) => {
              const gx = padL + i * groupW + groupW / 2;
              const y = padT + innerH - (r.avgDiscount / maxPct) * innerH * 0.85;
              return (i === 0 ? "M " : " L ") + gx + " " + y;
            })
            .join("")}
          fill="none"
          stroke="var(--info)"
          strokeWidth="1.6"
          strokeDasharray="3 3"
        />
        {byRound.map((r, i) => {
          const gx = padL + i * groupW + groupW / 2;
          const y = padT + innerH - (r.avgDiscount / maxPct) * innerH * 0.85;
          return (
            <g key={"pt-" + i}>
              <circle cx={gx} cy={y} r="4" fill="var(--surface-1)" stroke="var(--info)" strokeWidth="1.8" />
              <text x={gx + 8} y={y + 4} fontSize="10" fill="var(--info)" fontFamily="var(--font-mono)">
                {(r.avgDiscount * 100).toFixed(1)}%
              </text>
            </g>
          );
        })}
        <text
          x={padL - 8}
          y={padT + 4}
          textAnchor="end"
          fontSize="11"
          fill="var(--fg-3)"
          fontFamily="var(--font-mono)"
        >
          {maxCount}
        </text>
        <text
          x={padL - 8}
          y={padT + innerH + 4}
          textAnchor="end"
          fontSize="11"
          fill="var(--fg-3)"
          fontFamily="var(--font-mono)"
        >
          0
        </text>
      </svg>
    </div>
  );
}
