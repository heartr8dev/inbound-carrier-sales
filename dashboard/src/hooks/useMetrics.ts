// TanStack Query hook for the dashboard /metrics endpoint.
// Polls every 30s and refetches on window focus so wall-mounted dashboards
// stay live without manual refresh.
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import type { components } from "@/types/api";

type MetricsResponse = components["schemas"]["MetricsResponse"];
type MetricsPeriod = MetricsResponse["period"];

export function useMetrics(period: MetricsPeriod) {
  return useQuery<MetricsResponse>({
    queryKey: queryKeys.metrics(period),
    queryFn: () => apiGet<MetricsResponse>("/metrics", { period }),
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}
