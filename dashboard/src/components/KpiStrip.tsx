// 4-up KPI tiles with inline sparklines.
// Layout + class hooks come from .kpis / .kpi in dashboard.css.
import { Sparkline } from "@/components/Sparkline";
import { fmtMoney, fmtNum } from "@/lib/formatters";
import type { AggView } from "@/lib/agg";
import type { components } from "@/types/api";

type Period = components["schemas"]["MetricsResponse"]["period"];

const CALLS_LABEL: Record<Period, string> = {
  today: "Calls today",
  "7d": "Calls (7 days)",
  "30d": "Calls (30 days)",
  all: "Calls (all time)",
};

type KpiProps = {
  label: string;
  value: string;
  unit?: string;
  delta?: number;
  deltaLabel?: string;
  spark?: number[];
  sparkColor?: string;
};

function Kpi({ label, value, unit, delta, deltaLabel = "%", spark, sparkColor }: KpiProps) {
  const dir: "up" | "down" | "flat" =
    delta == null ? "flat" : delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  const arrow = dir === "up" ? "↑" : dir === "down" ? "↓" : "→";
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">
        <span>{value}</span>
        {unit && <span className="unit">{unit}</span>}
      </div>
      <div className={`kpi__delta kpi__delta--${dir}`}>
        <strong>
          {arrow} {delta == null ? "—" : Math.abs(delta) + deltaLabel}
        </strong>
        <span>vs prior period</span>
      </div>
      {spark && spark.length > 1 && (
        <div className="kpi__sparkline">
          <Sparkline data={spark} color={sparkColor ?? "var(--brand)"} />
        </div>
      )}
    </div>
  );
}

export function KpiStrip({ agg, period }: { agg: AggView; period: Period }) {
  const callsSpark = agg.hourly.map((h) => h.calls);
  const bookedSpark = agg.hourly.map((h) => h.booked);
  // Static rolling sparklines for the metrics that don't have hourly data.
  // These are placeholder shapes; replace with `useOutcomesByBucket` data if/when wired.
  const savedSpark = [42, 51, 47, 58, 62, 68, 65, 71, 68];
  const roundsSpark = [1.6, 1.5, 1.4, 1.5, 1.3, 1.3, 1.2, 1.2, 1.2];
  return (
    <div className="kpis">
      <Kpi
        label={CALLS_LABEL[period]}
        value={fmtNum(agg.total)}
        delta={12.3}
        spark={callsSpark}
        sparkColor="var(--brand)"
      />
      <Kpi
        label="Booked rate"
        value={(agg.bookedRate * 100).toFixed(1)}
        unit="%"
        delta={2.1}
        spark={bookedSpark}
        sparkColor="var(--good)"
      />
      <Kpi
        label="Avg margin saved"
        value={fmtMoney(agg.avgSaved)}
        delta={8.5}
        spark={savedSpark}
        sparkColor="var(--warn)"
      />
      <Kpi
        label="Avg negotiation rounds"
        value={agg.avgRounds}
        delta={-6.4}
        spark={roundsSpark}
        sparkColor="var(--info)"
      />
    </div>
  );
}
