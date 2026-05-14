import { useQuery } from '@tanstack/react-query'
import { tournamentAPI } from '../services/api'

/**
 * useTournamentSnapshot — React Query hook for one merged tournament snapshot.
 *
 * Tournaments are cold batches; never auto-poll. See CONTEXT.md D-23.
 * Do NOT "fix" this to a 5-second poll — the dashboard-wide poll cadence
 * (matched by useSafetyState et al.) is deliberately inverted here:
 * the cache is held forever, window-focus does not trigger refetch,
 * mounting does not trigger refetch, and no recurring interval is wired.
 * The page-level refresh button (Wave 3) calls `query.refetch()` manually
 * when the operator asks for fresh data.
 *
 * Gated on `enabled: !!tournamentId` so the hook doesn't fire when the
 * parent's URL param / selector state is still empty on first paint.
 *
 * Calls `GET /api/tournament/snapshots/{tournament_id}` (gateway merges
 * the snapshot JSON + optional `.ensemble.json` / `.significance.json`
 * sidecars per CONTEXT.md D-03 / D-05). The axios response interceptor
 * (services/api.js line 34) strips `.data`, so the resolved value of
 * `tournamentAPI.getSnapshot(...)` is the response BODY directly — no
 * `.data.data` nesting.
 *
 * Response shape:
 *   {
 *     success: true,
 *     snapshot:     <object — full snapshot JSON from disk>,
 *     ensemble:     <object | null>,        // null when sidecar absent
 *     significance: <object | null>,        // null when sidecar absent
 *   }
 *
 * @param {string|null|undefined} tournamentId — when falsy, the query is disabled
 * @returns React Query result: { data, isLoading, isFetching, isError,
 *   isSuccess, error, refetch }
 */
export function useTournamentSnapshot(tournamentId) {
  return useQuery({
    queryKey: ['tournament-snapshot', tournamentId],
    queryFn: () => tournamentAPI.getSnapshot(tournamentId),
    enabled: !!tournamentId,
    staleTime: Infinity, // D-23: tournaments are cold batches, never auto-poll
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: 2,
    retryDelay: 1000,
  })
}

export default useTournamentSnapshot
