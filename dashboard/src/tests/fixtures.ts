// Mock fixtures used across component tests.
import type { components } from "@/types/api";

type MetricsResponse = components["schemas"]["MetricsResponse"];
type RecentCallItem = components["schemas"]["RecentCallItem"];

export const mockKpi: MetricsResponse["kpi"] = {
  calls_today: 42,
  booked_rate_pct: 31.4,
  avg_margin_saved_usd: "187.50",
  avg_negotiation_rounds: 1.8,
};

export const mockRecentCall: RecentCallItem = {
  call_id: "call_test_1",
  carrier_mc: "123456",
  carrier_name: "Jane Doe",
  carrier_company: "Doe Trucking LLC",
  load_id_discussed: "LD-1001",
  loadboard_rate: "1850.00",
  final_agreed_rate: "1700.00",
  negotiation_rounds: 2,
  outcome: "booked",
  sentiment: "positive",
  origin_requested: "Dallas, TX",
  destination_requested: "Atlanta, GA",
  equipment_type_requested: "dry_van",
  transcript_summary:
    "Carrier called inbound, verified successfully, agreed on rate after two rounds.",
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
};
