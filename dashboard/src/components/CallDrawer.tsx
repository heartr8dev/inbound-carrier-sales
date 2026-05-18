// Call drill-down drawer — extracted fields KV grid + negotiation trail + transcript.
// Esc and overlay click both close. Uses real transcript_summary if present;
// otherwise generates a templated mock from buildTranscript (parity with design).
import { useEffect, useMemo } from "react";
import { OutcomeTag, SentimentTag } from "@/components/Tag";
import { fmtMoney } from "@/lib/formatters";
import { toNumber } from "@/lib/formatters";
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

type Turn = { who: "agent" | "carrier"; text: string };

function buildTranscript(c: Call): Turn[] {
  if (c.transcript_summary && c.transcript_summary.trim()) {
    // Treat the summary as one block from the agent so it renders cleanly.
    return [
      {
        who: "agent",
        text: c.transcript_summary,
      },
    ];
  }
  const t: Turn[] = [];
  const mc = c.carrier_mc ? `MC ${c.carrier_mc}` : "MC ???";
  const lane =
    c.origin_requested && c.destination_requested
      ? `${c.origin_requested} → ${c.destination_requested}`
      : "lane unknown";
  const equip = c.equipment_type_requested
    ? EQUIP_LABEL[c.equipment_type_requested].toLowerCase()
    : "equipment";

  t.push({ who: "agent", text: "Hi, this is Riley with Acme Logistics carrier sales. What's your MC number?" });
  t.push({ who: "carrier", text: mc + "." });

  if (c.outcome === "carrier_failed_vetting") {
    t.push({
      who: "agent",
      text: "Looks like FMCSA has a flag on that authority — I can't book against it. Worth getting that squared away and giving us a call back.",
    });
    t.push({ who: "carrier", text: "Alright, thanks anyway." });
    return t;
  }

  t.push({ who: "agent", text: "Authority looks good. What lane are you running today?" });
  t.push({
    who: "carrier",
    text: `I'm running ${equip}, ${lane}, picking up tomorrow.`,
  });

  if (c.outcome === "no_matching_loads") {
    t.push({
      who: "agent",
      text: "Not seeing anything on that exact lane right now. Want me to check a different pickup date or equipment?",
    });
    t.push({ who: "carrier", text: "Maybe a different day. I'll think about it." });
    return t;
  }

  const loadboard = toNumber(c.loadboard_rate);
  const final = toNumber(c.final_agreed_rate);

  t.push({
    who: "agent",
    text: `Got one — ${lane}, ${equip}, pickup tomorrow morning. Loadboard rate is ${fmtMoney(loadboard)}.`,
  });

  if (c.outcome === "carrier_hung_up") {
    t.push({ who: "carrier", text: "That's way too low." });
    t.push({ who: "agent", text: "I hear you. What number would work for you?" });
    t.push({ who: "carrier", text: "[Call ended.]" });
    return t;
  }

  if (c.negotiation_rounds >= 1) {
    t.push({
      who: "carrier",
      text: `That's not going to work. I need ${fmtMoney(Math.round(loadboard * 1.08))} to make it.`,
    });
    if (final) {
      t.push({ who: "agent", text: `I can come up to ${fmtMoney(final)}.` });
      t.push({
        who: "carrier",
        text: c.sentiment === "positive" ? "Deal — that works." : "Alright, I'll take it.",
      });
      t.push({
        who: "agent",
        text: "Booked. Transfer was successful — wrap up the conversation. Thanks for calling Acme!",
      });
    } else {
      t.push({
        who: "agent",
        text: `I can come up to ${fmtMoney(Math.round(loadboard * 0.97))}, but I can't go higher.`,
      });
      t.push({
        who: "carrier",
        text:
          c.outcome === "carrier_declined_rate"
            ? "That's not enough. Pass."
            : "Hmm. Let me think on it.",
      });
    }
  }
  return t;
}

type NegoStep = { price: number; who: string; color: string };

function buildNegotiation(c: Call): NegoStep[] {
  const loadboard = toNumber(c.loadboard_rate);
  const final = toNumber(c.final_agreed_rate);
  if (!c.negotiation_rounds || !loadboard) return [];
  const steps: NegoStep[] = [{ price: loadboard, who: "AGENT", color: "var(--fg-1)" }];
  const offerHigh = Math.round(loadboard * 1.08);
  steps.push({ price: offerHigh, who: "CARRIER", color: "var(--warn)" });
  if (c.negotiation_rounds >= 2) {
    steps.push({
      price: final ? Math.round((loadboard + final) / 2) : Math.round(loadboard * 1.02),
      who: "AGENT",
      color: "var(--fg-1)",
    });
  }
  if (c.negotiation_rounds >= 3 && !final) {
    steps.push({ price: Math.round(loadboard * 1.05), who: "CARRIER", color: "var(--warn)" });
  }
  if (final) {
    steps.push({ price: final, who: "BOOKED", color: "var(--good)" });
  }
  return steps;
}

export function CallDrawer({ call, onClose }: { call: Call; onClose: () => void }) {
  const transcript = useMemo(() => buildTranscript(call), [call]);
  const negotiation = useMemo(() => buildNegotiation(call), [call]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const equip = call.equipment_type_requested
    ? EQUIP_LABEL[call.equipment_type_requested]
    : "—";

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer__head">
          <div className="drawer__title-block">
            <div className="carrier">
              {call.carrier_company ?? call.carrier_name ?? "Unknown carrier"}
            </div>
            <div className="mc">
              {call.carrier_mc ? `MC ${call.carrier_mc}` : "no MC"} · {timeAgo(call.created_at)}
            </div>
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <OutcomeTag outcome={call.outcome} />
              <SentimentTag sentiment={call.sentiment} />
            </div>
          </div>
          <button className="drawer__close" type="button" onClick={onClose} aria-label="Close">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            >
              <path d="M6 6 L18 18 M18 6 L6 18" />
            </svg>
          </button>
        </div>

        <div>
          <div className="section-label">Extracted fields</div>
          <div className="kv-grid">
            <div className="kv">
              <div className="kv__label">Lane</div>
              <div className="kv__value sans">
                {call.origin_requested ?? "—"} → {call.destination_requested ?? "—"}
              </div>
            </div>
            <div className="kv">
              <div className="kv__label">Equipment</div>
              <div className="kv__value sans">{equip}</div>
            </div>
            <div className="kv">
              <div className="kv__label">Loadboard rate</div>
              <div className="kv__value">
                {call.loadboard_rate ? fmtMoney(call.loadboard_rate) : "—"}
              </div>
            </div>
            <div className="kv">
              <div className="kv__label">Final rate</div>
              <div
                className="kv__value"
                style={{
                  color: call.final_agreed_rate ? "var(--good)" : "var(--fg-4)",
                }}
              >
                {call.final_agreed_rate ? fmtMoney(call.final_agreed_rate) : "—"}
              </div>
            </div>
            <div className="kv">
              <div className="kv__label">Negotiation rounds</div>
              <div className="kv__value">{call.negotiation_rounds}</div>
            </div>
            <div className="kv">
              <div className="kv__label">FMCSA</div>
              <div
                className="kv__value sans"
                style={{
                  color:
                    call.outcome === "carrier_failed_vetting" ? "var(--bad)" : "var(--good)",
                }}
              >
                {call.outcome === "carrier_failed_vetting" ? "Failed" : "Pass"}
              </div>
            </div>
          </div>
        </div>

        {negotiation.length > 0 && (
          <div>
            <div className="section-label">Negotiation trail</div>
            <div className="nego-track">
              {negotiation.map((n, i) => (
                <span key={i} style={{ display: "contents" }}>
                  {i > 0 && <span className="nego-step__arrow">→</span>}
                  <div className="nego-step">
                    <span className="price" style={{ color: n.color }}>
                      {fmtMoney(n.price)}
                    </span>
                    <span className="who">{n.who}</span>
                  </div>
                </span>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="section-label">Transcript summary</div>
          <div className="transcript">
            {transcript.map((t, i) => (
              <div key={i} className={"turn turn--" + t.who}>
                <div className="turn__avatar">{t.who === "agent" ? "AI" : "C"}</div>
                <div className="turn__bubble">{t.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
