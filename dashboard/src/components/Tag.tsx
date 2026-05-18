// Outcome / sentiment pill with a ::before colored dot.
// The CSS classes (.tag, .tag--booked, .tag--sentiment, etc) live in dashboard.css.
import type { components } from "@/types/api";

type Outcome = components["schemas"]["CallOutcome"];
type Sentiment = components["schemas"]["CarrierSentiment"];

const OUTCOME_LABEL: Record<Outcome, string> = {
  booked: "Booked",
  transferred_to_rep: "Transferred",
  no_matching_loads: "No Match",
  carrier_declined_rate: "Declined",
  carrier_failed_vetting: "Failed Vetting",
  negotiation_stalled: "Stalled",
  carrier_hung_up: "Hung Up",
};

const OUTCOME_CLASS: Record<Outcome, string> = {
  booked: "booked",
  transferred_to_rep: "transferred",
  no_matching_loads: "no-match",
  carrier_declined_rate: "declined",
  carrier_failed_vetting: "failed-vetting",
  negotiation_stalled: "stalled",
  carrier_hung_up: "hung-up",
};

const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: "Positive",
  neutral: "Neutral",
  skeptical: "Skeptical",
  frustrated: "Frustrated",
  hostile: "Hostile",
};

export function OutcomeTag({ outcome }: { outcome: Outcome }) {
  return <span className={`tag tag--${OUTCOME_CLASS[outcome]}`}>{OUTCOME_LABEL[outcome]}</span>;
}

export function SentimentTag({ sentiment }: { sentiment: Sentiment }) {
  return (
    <span className={`tag tag--sentiment tag--${sentiment}`}>{SENTIMENT_LABEL[sentiment]}</span>
  );
}

// Helpers for derived contexts where we have stringy labels rather than enums.
export function outcomeClassFromLabel(label: string): string {
  return label.toLowerCase().replace(/\s+/g, "-");
}
