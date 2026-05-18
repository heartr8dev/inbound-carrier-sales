// Donut + failure-reason bar list (FMCSA pass rate + top failures).
import { Donut } from "@/components/Donut";
import type { AggView } from "@/lib/agg";

export function VettingCard({ agg }: { agg: AggView }) {
  const passed = Math.max(0, agg.total - agg.totalFailed);
  const maxFail = agg.failReasons[0]?.count ?? 1;
  return (
    <div className="donut-card">
      <Donut value={passed} total={agg.total} color="var(--good)" />
      <div>
        <div style={{ marginBottom: 12 }}>
          <div className="t-overline">FMCSA verification</div>
          <div style={{ fontSize: 13, color: "var(--fg-3)", marginTop: 4 }}>
            <span style={{ color: "var(--good)" }}>{passed} passed</span>
            <span> · </span>
            <span style={{ color: "var(--bad)" }}>{agg.totalFailed} failed</span>
          </div>
        </div>
        <div className="fail-list">
          {agg.failReasons.map((f) => (
            <div className="fail-row" key={f.reason}>
              <div className="label">{f.reason}</div>
              <div className="count">{f.count}</div>
              <div className="meter">
                <i style={{ width: `${(f.count / maxFail) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
