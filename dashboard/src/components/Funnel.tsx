// Horizontal bar funnel — Total → Qualified → Matched → Negotiated → Booked.
// Layout via .funnel / .funnel__row / .funnel__bar / .funnel__fill in dashboard.css.
import type { AggView } from "@/lib/agg";

type Stage = { name: string; value: number; retain: number };

export function Funnel({ agg }: { agg: AggView }) {
  const stages: Stage[] = [
    { name: "Total calls", value: agg.total, retain: 1 },
    {
      name: "Qualified",
      value: agg.qualified,
      retain: agg.total ? agg.qualified / agg.total : 0,
    },
    {
      name: "Matched",
      value: agg.matched,
      retain: agg.qualified ? agg.matched / agg.qualified : 0,
    },
    {
      name: "Negotiated",
      value: agg.negotiated,
      retain: agg.matched ? agg.negotiated / agg.matched : 0,
    },
    {
      name: "Booked",
      value: agg.booked,
      retain: agg.negotiated ? agg.booked / agg.negotiated : 0,
    },
  ];
  const max = stages[0].value || 1;
  return (
    <div className="funnel">
      {stages.map((s, i) => (
        <div className="funnel__row" key={s.name}>
          <div className="funnel__label">
            <div className="name">{s.name}</div>
            <div className="meta">
              {i === 0 ? `${s.value} total` : `${(s.retain * 100).toFixed(0)}% retained`}
            </div>
          </div>
          <div className="funnel__bar">
            <div
              className="funnel__fill"
              data-stage="good"
              style={{ width: `${(s.value / max) * 100}%` }}
            >
              <span>{s.value.toLocaleString()}</span>
              <span
                style={{
                  marginLeft: "auto",
                  marginRight: 14,
                  opacity: 0.85,
                  fontSize: 12,
                }}
              >
                {((s.value / max) * 100).toFixed(0)}% of total
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
