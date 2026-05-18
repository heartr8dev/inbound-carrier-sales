// Hand-rolled SVG sparkline — single line + soft area fill + end dot.
// Ported from /tmp/acme-design/acme-dash/project/charts.jsx Sparkline.
import { useId } from "react";

type SparklineProps = {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
};

export function Sparkline({
  data,
  width = 96,
  height = 36,
  color = "var(--brand)",
}: SparklineProps) {
  const gradId = useId();
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = Math.max(1, max - min);
  const step = width / (data.length - 1);
  const pts = data.map((d, i): [number, number] => [
    i * step,
    height - ((d - min) / range) * height * 0.85 - 4,
  ]);
  const path = pts
    .map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1))
    .join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradId})`} />
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.5" fill={color} />
    </svg>
  );
}
