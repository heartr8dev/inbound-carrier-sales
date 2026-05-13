// Expandable table of the most recent call logs.
//
// Polish:
//   • Zebra striping at 1% white alpha on even rows.
//   • Rows lift on hover (bg-white/[0.04]) with a left-edge gradient accent.
//   • Monospace `MC` chip in slate-mono font.
//   • Expanded panel uses CSS grid-template-rows trick for smooth slide-down.
//   • Chevron rotates 90° when open.
//   • Rates right-aligned tabular; final rate gets a small emerald glow.
import { useState } from "react";
import clsx from "clsx";
import type { components } from "@/types/api";
import {
  EquipmentChip,
  OutcomeChip,
  SentimentChip,
} from "@/components/Chip";
import { OutcomeGlyph } from "@/components/OutcomeGlyph";
import { outcomeColors } from "@/lib/theme";
import {
  formatCurrency,
  formatNumber,
  formatRelativeTime,
} from "@/lib/formatters";
import { EmptyState } from "@/components/Loading";
import { ChevronIcon } from "@/components/icons";

type RecentCallItem = components["schemas"]["RecentCallItem"];

interface RecentCallsProps {
  calls: RecentCallItem[];
}

export function RecentCalls({ calls }: RecentCallsProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (calls.length === 0) {
    return <EmptyState title="No calls logged yet" />;
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="overflow-x-auto" data-testid="recent-calls">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/[0.06] text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <th className="w-8 px-4 py-3"></th>
            <th className="px-3 py-3 font-medium">When</th>
            <th className="px-3 py-3 font-medium">Carrier</th>
            <th className="px-3 py-3 font-medium">Lane</th>
            <th className="px-3 py-3 font-medium">Equip</th>
            <th className="px-3 py-3 text-right font-medium">Loadboard</th>
            <th className="px-3 py-3 text-right font-medium">Final</th>
            <th className="px-3 py-3 text-right font-medium">Rounds</th>
            <th className="px-3 py-3 font-medium">Outcome</th>
            <th className="px-3 py-3 font-medium">Sentiment</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call, idx) => {
            const isExpanded = expanded.has(call.call_id);
            return (
              <RowGroup
                key={call.call_id}
                call={call}
                isExpanded={isExpanded}
                onToggle={() => toggle(call.call_id)}
                zebra={idx % 2 === 1}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RowGroup({
  call,
  isExpanded,
  onToggle,
  zebra,
}: {
  call: RecentCallItem;
  isExpanded: boolean;
  onToggle: () => void;
  zebra: boolean;
}) {
  const lane =
    call.origin_requested && call.destination_requested
      ? `${call.origin_requested} → ${call.destination_requested}`
      : (call.origin_requested ?? call.destination_requested ?? "—");

  return (
    <>
      <tr
        className={clsx(
          "group relative cursor-pointer border-b border-white/[0.04] text-slate-200",
          "transition-colors duration-150",
          zebra && "bg-white/[0.012]",
          "hover:bg-white/[0.04]",
          isExpanded && "bg-white/[0.05]",
        )}
        onClick={onToggle}
        data-testid={`call-row-${call.call_id}`}
        aria-expanded={isExpanded}
      >
        <td className="px-4 py-2.5 text-slate-500">
          <ChevronIcon open={isExpanded} size={12} />
        </td>
        <td className="px-3 py-2.5 text-xs text-slate-400">
          {formatRelativeTime(call.created_at)}
        </td>
        <td className="px-3 py-2.5">
          <div className="text-slate-100">
            {call.carrier_name ?? call.carrier_company ?? "—"}
          </div>
          {call.carrier_mc && (
            <div className="font-mono text-[10px] text-slate-500">
              MC {call.carrier_mc}
            </div>
          )}
        </td>
        <td className="px-3 py-2.5 text-slate-200">{lane}</td>
        <td className="px-3 py-2.5">
          {call.equipment_type_requested ? (
            <EquipmentChip equipment={call.equipment_type_requested} />
          ) : (
            <span className="text-slate-600">—</span>
          )}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums num-mono text-slate-200">
          {call.loadboard_rate ? formatCurrency(call.loadboard_rate) : "—"}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums num-mono">
          {call.final_agreed_rate ? (
            <span
              className="font-semibold text-emerald-300"
              style={{ textShadow: "0 0 12px rgba(16,185,129,0.35)" }}
            >
              {formatCurrency(call.final_agreed_rate)}
            </span>
          ) : (
            <span className="text-slate-600">—</span>
          )}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums num-mono text-slate-200">
          {formatNumber(call.negotiation_rounds)}
        </td>
        <td className="px-3 py-2.5">
          <span className="inline-flex items-center gap-1.5">
            <OutcomeGlyph
              outcome={call.outcome}
              color={outcomeColors[call.outcome]}
            />
            <OutcomeChip outcome={call.outcome} />
          </span>
        </td>
        <td className="px-3 py-2.5">
          <SentimentChip sentiment={call.sentiment} />
        </td>
      </tr>
      {/* Animated expand row using grid-template-rows trick */}
      <tr
        className={clsx(
          "border-b transition-colors",
          isExpanded ? "border-white/[0.06]" : "border-transparent",
        )}
        aria-hidden={!isExpanded}
        data-testid={isExpanded ? `call-row-expanded-${call.call_id}` : undefined}
      >
        <td colSpan={10} className="p-0">
          <div
            className="grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
            style={{
              gridTemplateRows: isExpanded ? "1fr" : "0fr",
            }}
          >
            <div className="overflow-hidden">
              <div className="border-l-2 border-indigo-500/40 bg-gradient-to-r from-indigo-500/[0.06] to-transparent px-6 py-4">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <DetailRow label="Call ID" value={call.call_id} mono />
                  <DetailRow
                    label="Load Discussed"
                    value={call.load_id_discussed ?? "—"}
                    mono
                  />
                  <DetailRow
                    label="Carrier Company"
                    value={call.carrier_company ?? "—"}
                  />
                </div>
                <div className="mt-4">
                  <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
                    Transcript Summary
                  </p>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-300">
                    {call.transcript_summary ?? "No summary available."}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </td>
      </tr>
    </>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
        {label}
      </p>
      <p
        className={clsx(
          "mt-0.5 text-xs text-slate-200",
          mono && "font-mono",
        )}
      >
        {value}
      </p>
    </div>
  );
}
