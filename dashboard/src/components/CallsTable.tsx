// Recent-calls table — CSS grid with display:contents rows. Click a row → onPick.
import { OutcomeTag, SentimentTag } from "@/components/Tag";
import { fmtMoney } from "@/lib/formatters";
import type { components } from "@/types/api";
import { formatDistanceToNowStrict, parseISO } from "date-fns";

type Call = components["schemas"]["RecentCallItem"];

function timeAgo(iso: string): string {
  try {
    return formatDistanceToNowStrict(parseISO(iso)) + " ago";
  } catch {
    return "—";
  }
}

const EQUIP_LABEL: Record<NonNullable<Call["equipment_type_requested"]>, string> = {
  dry_van: "Dry Van",
  reefer: "Reefer",
  flatbed: "Flatbed",
  step_deck: "Step Deck",
  power_only: "Power Only",
};

export function CallsTable({
  calls,
  activeId,
  onPick,
}: {
  calls: Call[];
  activeId?: string;
  onPick: (call: Call) => void;
}) {
  return (
    <div className="table-wrap">
      <div className="card__head">
        <div>
          <h3 className="card__title">Recent calls</h3>
          <div className="card__sub">Click a row to reveal transcript and extracted fields</div>
        </div>
        <div className="card__aside">{calls.length} calls</div>
      </div>
      <div className="table-scroll">
        <div className="table">
          <div className="th">When</div>
          <div className="th">Carrier</div>
          <div className="th">Lane</div>
          <div className="th">Equip</div>
          <div className="th right">Loadboard</div>
          <div className="th right">Final</div>
          <div className="th right">Rounds</div>
          <div className="th">Outcome</div>
          <div className="th">Sentiment</div>
          {calls.slice(0, 25).map((c) => {
            const equip = c.equipment_type_requested
              ? EQUIP_LABEL[c.equipment_type_requested]
              : "—";
            return (
              <div
                key={c.call_id}
                className="row"
                data-active={activeId === c.call_id}
                onClick={() => onPick(c)}
              >
                <div className="td muted mono">{timeAgo(c.created_at)}</div>
                <div className="td">
                  <div className="carrier-cell">
                    <div className="name">
                      {c.carrier_company ?? c.carrier_name ?? "Unknown carrier"}
                    </div>
                    <div className="mc">{c.carrier_mc ? `MC ${c.carrier_mc}` : "—"}</div>
                  </div>
                </div>
                <div className="td">
                  <div className="lane-cell">
                    <span>{c.origin_requested ?? "—"}</span>
                    <span className="arrow">→</span>
                    <span>{c.destination_requested ?? "—"}</span>
                  </div>
                </div>
                <div className="td">{equip}</div>
                <div className="td mono right">
                  {c.loadboard_rate ? fmtMoney(c.loadboard_rate) : "—"}
                </div>
                <div
                  className="td mono right"
                  style={{ color: c.final_agreed_rate ? "var(--good)" : "var(--fg-4)" }}
                >
                  {c.final_agreed_rate ? fmtMoney(c.final_agreed_rate) : "—"}
                </div>
                <div className="td mono right">{c.negotiation_rounds}</div>
                <div className="td">
                  <OutcomeTag outcome={c.outcome} />
                </div>
                <div className="td">
                  <SentimentTag sentiment={c.sentiment} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
