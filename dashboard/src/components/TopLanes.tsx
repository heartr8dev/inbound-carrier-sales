// Top lanes by call volume — horizontal bars with origin → destination labels.
import type { AggView } from "@/lib/agg";

export function TopLanes({ laneCounts }: { laneCounts: AggView["laneCounts"] }) {
  const sorted = Object.entries(laneCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  if (sorted.length === 0) {
    return (
      <div className="lanes">
        <div className="lane" style={{ minHeight: 56, alignItems: "center" }}>
          <div className="lane__text" style={{ color: "var(--fg-3)" }}>
            No lane data yet
          </div>
        </div>
      </div>
    );
  }
  const max = sorted[0][1];
  return (
    <div className="lanes">
      {sorted.map(([lane, count]) => {
        const [origin, destination] = lane.split(" → ");
        return (
          <div key={lane} className="lane">
            <div className="lane__bar" style={{ width: `${(count / max) * 100}%` }} />
            <div className="lane__text">
              <span>{origin}</span>
              <span className="lane__arrow">→</span>
              <span>{destination}</span>
            </div>
            <div className="lane__count">{count}</div>
          </div>
        );
      })}
    </div>
  );
}
