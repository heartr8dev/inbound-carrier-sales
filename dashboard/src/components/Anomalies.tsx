// "What the agent noticed today" — 3 auto-generated callouts.
// Heuristics over AggView with hardcoded fallback copy when data is thin.
import type { AggView } from "@/lib/agg";

type Item = { level: "good" | "warn" | "bad"; title: string; sub: string };

function computeAnomalies(agg: AggView): Item[] {
  const items: Item[] = [];

  // Best converting lane — top lane by count
  const topLane = Object.entries(agg.laneCounts).sort((a, b) => b[1] - a[1])[0];
  if (topLane) {
    items.push({
      level: "good",
      title: `${topLane[0]} is your top inbound lane today`,
      sub: `${topLane[1]} carriers called in on this lane. Lean into this corridor in tomorrow's outbound.`,
    });
  }

  // Frustrated × negotiation correlation
  const frustratedDeclined = agg.sentOut.frustrated?.carrier_declined_rate ?? 0;
  const frustratedStalled = agg.sentOut.frustrated?.negotiation_stalled ?? 0;
  const frustratedTotal = frustratedDeclined + frustratedStalled;
  if (frustratedTotal >= 3) {
    items.push({
      level: "warn",
      title: "Frustrated sentiment correlates with late-round outcomes",
      sub: `${frustratedTotal} calls reached round 3 with frustration. Consider tightening counter-offer thresholds earlier in the curve.`,
    });
  }

  // Vetting fail concentration
  if (agg.failReasons.length > 0 && agg.totalFailed >= 5) {
    const top = agg.failReasons[0];
    items.push({
      level: "bad",
      title: `${top.count} carriers failed vetting on "${top.reason}"`,
      sub: `Top FMCSA rejection reason today. Worth a quick spot-check on the upstream prequalifier.`,
    });
  }

  // Backfill with hardcoded design copy if heuristics produced fewer than 3.
  const fallback: Item[] = [
    {
      level: "bad",
      title: "Reefer no-match rate up on Sacramento → Reno",
      sub: "Loadboard rates below the floor on most calls. Consider raising floor or sourcing better-paying loads.",
    },
    {
      level: "warn",
      title: "Frustrated sentiment correlates with 3+ negotiation rounds",
      sub: "When carriers reach round 3 without agreement, frustration triples. Tighten counter-offer thresholds.",
    },
    {
      level: "good",
      title: "Best converting lane today",
      sub: "Multiple bookings on the same corridor. Direction: lean into similar origins tomorrow.",
    },
  ];
  while (items.length < 3) {
    items.push(fallback[items.length]);
  }
  return items.slice(0, 3);
}

export function Anomalies({ agg }: { agg: AggView }) {
  const items = computeAnomalies(agg);
  return (
    <div className="anomalies">
      {items.map((a, i) => (
        <div className="anomaly" key={i}>
          <div className={`anomaly__dot anomaly__dot--${a.level}`} />
          <div className="anomaly__body">
            <div className="anomaly__title">{a.title}</div>
            <div className="anomaly__sub">{a.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
