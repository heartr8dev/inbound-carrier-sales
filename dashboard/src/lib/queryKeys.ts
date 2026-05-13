// Centralized TanStack Query key factories.
// Keeping these in one place avoids string drift between hooks and invalidations.
import type { components } from "@/types/api";

type MetricsPeriod = components["schemas"]["MetricsResponse"]["period"];
type CallOutcome = components["schemas"]["CallOutcome"];
type CarrierSentiment = components["schemas"]["CarrierSentiment"];

export interface CallsListFilters {
  page?: number;
  page_size?: number;
  from?: string;
  to?: string;
  outcome?: CallOutcome;
  sentiment?: CarrierSentiment;
}

export const queryKeys = {
  metrics: (period: MetricsPeriod) => ["metrics", period] as const,
  calls: (filters: CallsListFilters) => ["calls", filters] as const,
} as const;
