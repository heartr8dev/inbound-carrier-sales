// Chord-like state-to-state flow. Two columns of state codes (origin / dest),
// curved bezier ribbons weighted by lane volume.
import type { LaneTuple } from "@/lib/agg";

export function LaneFlow({ lanes }: { lanes: LaneTuple[] }) {
  const topLanes = lanes.slice(0, 10);
  if (topLanes.length === 0) {
    return (
      <div style={{ padding: "var(--s-6)", color: "var(--fg-3)", fontSize: 13 }}>
        No lane data yet
      </div>
    );
  }
  const states = Array.from(new Set(topLanes.flatMap((l) => [l[3], l[4]])));
  const stateVol: Record<string, number> = {};
  topLanes.forEach((l) => {
    stateVol[l[3]] = (stateVol[l[3]] ?? 0) + l[2];
    stateVol[l[4]] = (stateVol[l[4]] ?? 0) + l[2];
  });
  states.sort((a, b) => stateVol[b] - stateVol[a]);

  const width = 280;
  const height = 320;
  const padY = 16;
  const stepY = (height - padY * 2) / Math.max(1, states.length - 1);
  const xL = 80;
  const xR = width - 80;
  const stateY: Record<string, number> = Object.fromEntries(
    states.map((s, i) => [s, padY + i * stepY]),
  );
  const maxVol = Math.max(...topLanes.map((l) => l[2]));

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="flow-grad" x1="0" x2="1">
          <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--warn)" stopOpacity="0.55" />
        </linearGradient>
      </defs>
      {topLanes.map((l, i) => {
        // Deterministic micro-jitter so overlapping ribbons remain visible.
        const jitterA = ((i * 31) % 7) / 7 - 0.5;
        const jitterB = ((i * 47) % 7) / 7 - 0.5;
        const y1 = stateY[l[3]] + jitterA * 2;
        const y2 = stateY[l[4]] + jitterB * 2;
        const sw = 1.5 + (l[2] / maxVol) * 6;
        const cx = (xL + xR) / 2;
        return (
          <path
            key={i}
            d={`M ${xL} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${xR} ${y2}`}
            stroke="url(#flow-grad)"
            strokeWidth={sw}
            fill="none"
            opacity="0.85"
          />
        );
      })}
      {states.map((s) => (
        <g key={s}>
          <circle cx={xL} cy={stateY[s]} r="4" fill="var(--brand)" />
          <text
            x={xL - 10}
            y={stateY[s] + 4}
            textAnchor="end"
            fontSize="11"
            fontFamily="var(--font-mono)"
            fill="var(--fg-2)"
            fontWeight="600"
          >
            {s}
          </text>
          <circle cx={xR} cy={stateY[s]} r="4" fill="var(--warn)" />
          <text
            x={xR + 10}
            y={stateY[s] + 4}
            fontSize="11"
            fontFamily="var(--font-mono)"
            fill="var(--fg-2)"
            fontWeight="600"
          >
            {s}
          </text>
        </g>
      ))}
      <text x={xL} y={height - 4} textAnchor="middle" fontSize="9" letterSpacing="0.18em" fontWeight="600" fill="var(--fg-3)">
        ORIGIN
      </text>
      <text x={xR} y={height - 4} textAnchor="middle" fontSize="9" letterSpacing="0.18em" fontWeight="600" fill="var(--fg-3)">
        DEST
      </text>
    </svg>
  );
}
