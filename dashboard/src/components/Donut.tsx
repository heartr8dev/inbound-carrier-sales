// Donut chart with center % + PASS RATE label.
// Ported from /tmp/acme-design/acme-dash/project/charts.jsx Donut.
type DonutProps = {
  value: number;
  total: number;
  color?: string;
  size?: number;
  stroke?: number;
  label?: string;
};

export function Donut({
  value,
  total,
  color = "var(--good)",
  size = 130,
  stroke = 14,
  label = "PASS RATE",
}: DonutProps) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = total ? value / total : 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--surface-2)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeDasharray={`${c * pct} ${c}`}
        strokeDashoffset={c / 4}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        strokeLinecap="round"
      />
      <text
        x={size / 2}
        y={size / 2 - 4}
        textAnchor="middle"
        fontFamily="var(--font-display)"
        fontSize="32"
        fontWeight="300"
        fill="var(--fg-1)"
      >
        {Math.round(pct * 100)}%
      </text>
      <text
        x={size / 2}
        y={size / 2 + 14}
        textAnchor="middle"
        fontSize="10"
        letterSpacing="0.14em"
        fill="var(--fg-3)"
        fontWeight="600"
        fontFamily="var(--font-sans)"
      >
        {label}
      </text>
    </svg>
  );
}
