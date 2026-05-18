// Sentiment × Outcome heatmap (CSS grid). Click a non-zero cell → onCellClick.
import { Fragment } from "react";
import { SentimentTag } from "@/components/Tag";
import type { AggView } from "@/lib/agg";
import type { components } from "@/types/api";

type Outcome = components["schemas"]["CallOutcome"];
type Sentiment = components["schemas"]["CarrierSentiment"];

const OUTCOME_LABEL: Record<Outcome, string> = {
  booked: "Booked",
  transferred_to_rep: "Transferred",
  no_matching_loads: "No Match",
  carrier_declined_rate: "Declined",
  negotiation_stalled: "Stalled",
  carrier_failed_vetting: "Failed Vetting",
  carrier_hung_up: "Hung Up",
};

const OUTCOME_CLASS: Record<Outcome, "good" | "warn" | "bad"> = {
  booked: "good",
  transferred_to_rep: "good",
  carrier_declined_rate: "warn",
  negotiation_stalled: "warn",
  no_matching_loads: "bad",
  carrier_failed_vetting: "bad",
  carrier_hung_up: "bad",
};

const SENTIMENT_ORDER: Sentiment[] = [
  "positive",
  "neutral",
  "skeptical",
  "frustrated",
  "hostile",
];

const OUTCOME_ORDER: Outcome[] = [
  "booked",
  "transferred_to_rep",
  "no_matching_loads",
  "carrier_declined_rate",
  "negotiation_stalled",
  "carrier_failed_vetting",
  "carrier_hung_up",
];

export function SentimentHeatmap({
  sentOut,
  onCellClick,
}: {
  sentOut: AggView["sentOut"];
  onCellClick?: (sentiment: Sentiment, outcome: Outcome) => void;
}) {
  let max = 0;
  for (const s of SENTIMENT_ORDER) {
    for (const o of OUTCOME_ORDER) {
      if (sentOut[s][o] > max) max = sentOut[s][o];
    }
  }

  const colorFor = (o: Outcome, v: number) => {
    if (v === 0) return "transparent";
    const t = Math.min(1, v / max);
    const base = {
      good: "var(--good)",
      warn: "var(--warn)",
      bad: "var(--bad)",
    }[OUTCOME_CLASS[o]];
    const pct = (8 + t * 60).toFixed(0);
    return `color-mix(in oklch, ${base} ${pct}%, transparent)`;
  };

  return (
    <div
      className="heatmap"
      style={{ gridTemplateColumns: `110px repeat(${OUTCOME_ORDER.length}, 1fr)` }}
    >
      <div></div>
      {OUTCOME_ORDER.map((o) => (
        <div
          key={o}
          className="col-label"
          style={{
            writingMode: "vertical-rl",
            transform: "rotate(180deg)",
            padding: "0 0 8px",
            alignSelf: "end",
            height: 70,
          }}
        >
          {OUTCOME_LABEL[o]}
        </div>
      ))}
      {SENTIMENT_ORDER.map((s) => (
        <Fragment key={s}>
          <div className="row-label">
            <SentimentTag sentiment={s} />
          </div>
          {OUTCOME_ORDER.map((o) => {
            const v = sentOut[s][o] ?? 0;
            return (
              <div
                key={o}
                className={"cell" + (v === 0 ? " zero" : "")}
                style={{
                  background: v === 0 ? "var(--surface-2)" : colorFor(o, v),
                }}
                onClick={() => v > 0 && onCellClick?.(s, o)}
              >
                {v || "·"}
              </div>
            );
          })}
        </Fragment>
      ))}
    </div>
  );
}
