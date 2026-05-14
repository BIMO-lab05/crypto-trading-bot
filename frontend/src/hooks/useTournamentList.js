import { useQuery } from '@tanstack/react-query'
import { tournamentAPI } from '../services/api'

/**
 * useTournamentList — React Query hook for the tournament snapshot index.
 *
 * Tournaments are cold batches; never auto-poll. See CONTEXT.md D-23.
 * Do NOT "fix" this to a 5-second poll — the dashboard-wide poll cadence
 * (matched by useSafetyState et al.) is deliberately inverted here:
 * the cache is held forever, window-focus does not trigger refetch,
 * mounting does not trigger refetch, and no recurring interval is wired.
 * The page-level refresh button (Wave 3) calls `query.refetch()` manually
 * when the operator asks for fresh data.
 *
 * Calls `GET /api/tournament/snapshots` (gateway reads committed JSON files
 * from a RO bind-mount per CONTEXT.md D-01). The axios response interceptor
 * (services/api.js line 34) strips `.data`, so the resolved value of
 * `tournamentAPI.listSnapshots()` is the response BODY directly — no
 * `.data.data` nesting.
 *
 * Response shape:
 *   {
 *     success: true,
 *     count: <int>,
 *     tournaments: [
 *       {
 *         tournament_id: <string>,
 *         exported_at: <ISO-8601>,
 *         n_rows: <int>,
 *         n_success: <int>,
 *         n_failed: <int>,
 *         architectures: ["GRU", ...],
 *         symbols: ["BTC", ...],
 *       },
 *       ...
 *     ]
 *   }
 *
 * @returns React Query result: { data, isLoading, isFetching, isError,
 *   isSuccess, error, refetch }
 */
export function useTournamentList() {
  return useQuery({
    queryKey: ['tournament-list'],
    queryFn: () => tournamentAPI.listSnapshots(),
    staleTime: Infinity, // D-23: tournaments are cold batches, never auto-poll
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: 2,
    retryDelay: 1000,
  })
}

export default useTournamentList
