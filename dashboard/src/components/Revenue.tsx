// Revenue stat-row + rate strip with dashed gap.
// Floor / Booked / Loadboard markers labeled below.
import { fmtMoney } from "@/lib/formatters";
import type { AggView } from "@/lib/agg";

export function Revenue({ agg }: { agg: AggView }) {
  const floor = Math.round(agg.avgLoadboard * 0.78);
  const min = floor;
  const max = agg.avgLoadboard || 1;
  // Clamp to [0, 100] so an outlier booked rate (above loadboard or below
  // floor) never overflows the rate-strip parent. The neumorphic well is
  // 100% wide; the fill must stay inside it.
  const at = (v: number) => {
    const pct = ((v - min) / Math.max(1, max - min)) * 100;
    return `${Math.max(0, Math.min(100, pct)).toFixed(1)}%`;
  };
  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <div className="stat__label">Avg loadboard</div>
          <div className="stat__value stat__value--display">{fmtMoney(agg.avgLoadboard)}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Avg booked</div>
          <div className="stat__value stat__value--display" style={{ color: "var(--good)" }}>
            {fmtMoney(agg.avgFinal)}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Margin preserved</div>
          <div className="stat__value stat__value--display">
            {agg.marginPreserved}
            <span style={{ fontSize: 18, color: "var(--fg-3)" }}>%</span>
          </div>
          <div className="stat__sub">{fmtMoney(agg.avgSaved)} avg saved per load</div>
        </div>
      </div>
      <div>
        <div className="rate-strip">
          <div
            className="rate-strip__fill"
            style={{ width: `calc(${at(agg.avgFinal)} - 4px)` }}
          />
          <div
            className="rate-strip__gap"
            style={{ left: at(agg.avgFinal), right: "4px" }}
          />
          <div className="rate-strip__marker" style={{ left: at(agg.avgFinal) }} />
        </div>
        <div className="rate-ends">
          <div className="rate-ends__group">
            <span className="rate-ends__label" style={{ color: "var(--fg-3)" }}>
              Floor
            </span>
            <span className="rate-ends__value">{fmtMoney(floor)}</span>
          </div>
          <div
            className="rate-ends__group"
            style={{ alignItems: "center", position: "relative", top: -2 }}
          >
            <span className="rate-ends__label" style={{ color: "var(--good)" }}>
              Booked
            </span>
            <span className="rate-ends__value" style={{ color: "var(--good)" }}>
              {fmtMoney(agg.avgFinal)}
            </span>
          </div>
          <div className="rate-ends__group rate-ends__group--right">
            <span className="rate-ends__label" style={{ color: "var(--warn)" }}>
              Loadboard
            </span>
            <span className="rate-ends__value">{fmtMoney(agg.avgLoadboard)}</span>
          </div>
        </div>
      </div>
    </>
  );
}
