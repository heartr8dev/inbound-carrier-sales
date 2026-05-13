// TanStack Query hook for paginated /calls listing with filters.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import { queryKeys, type CallsListFilters } from "@/lib/queryKeys";
import type { components } from "@/types/api";

type CallListResponse = components["schemas"]["CallListResponse"];

export function useCalls(filters: CallsListFilters = {}) {
  return useQuery<CallListResponse>({
    queryKey: queryKeys.calls(filters),
    queryFn: () =>
      apiGet<CallListResponse>(
        "/calls",
        filters as Record<string, unknown>,
      ),
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    placeholderData: keepPreviousData,
    retry: 1,
  });
}
