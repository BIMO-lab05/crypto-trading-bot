import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

/**
 * useCarryIns — polls the PREFLIGHT carry-ins endpoint every 5 s.
 *
 * Matches the useSafetyState cadence per D-10-15 (06-CONTEXT.md D-11:
 * "cadence parity with useSafetyState").  Powers DASHLIVE-01 (Phase 10
 * success criterion: operator sees carry-in close states + 3-state banner).
 *
 * The axios client (services/api.js) has baseURL '/api' and a response
 * interceptor that unwraps `.data`, so the resolved value of api.get is
 * the body itself — no `.data.data` nesting.
 *
 * Response body shape (from services/api-gateway/app/routes/preflight_carry_ins.py
 * per D-10-04 + D-10-16):
 *
 *   {
 *     schema_version: 1,
 *     evaluated_at:  <ISO string>,
 *     overall:       "DO_NOT_FLIP" | "ALMOST" | "READY",
 *     carry_ins: [
 *       { id, state: "open"|"closed", closed_at, evidence_path, description }
 *       // five carry-ins: OP-01, OP-02, OP-03, OP-04, INFRA-02
 *     ],
 *     window: {
 *       first_all_pass_at:  <ISO string | null>,
 *       elapsed_seconds:    number,
 *       required_seconds:   number,
 *       remaining_seconds:  number
 *     },
 *     preflight_summary: { pass: number, fail: number, unknown: number },
 *     live_readiness: {
 *       // joined snapshot of /api/preflight/live-readiness at evaluation time
 *       schema_version: 1,
 *       overall:        "PASS" | "FAIL" | "UNKNOWN",
 *       evaluated_at:   <ISO string>,
 *       checks: [
 *         { check: string, status: "PASS" | "FAIL" | "UNKNOWN", detail: string }
 *       ]
 *     }
 *   }
 *
 * Per D-10-16 (LOAD-BEARING — do not paraphrase):
 *   useCarryIns().data is the AUTHORITATIVE source for `overall` and `window`.
 *   useLiveReadiness() is used for per-check detail rows only.
 *   If the two queries disagree (race between refetches), trust useCarryIns.
 *   The PathToLiveTile renders overall directly from this hook — it does NOT
 *   recompute the 3-state banner client-side (D-10-04).
 *
 * @returns React Query result: { data, isLoading, isFetching, isError,
 *   isSuccess, error, refetch }
 */
export function useCarryIns() {
  return useQuery({
    queryKey: ['preflight-carry-ins'],
    queryFn: async () => {
      return await api.get('/preflight/carry-ins')
    },
    refetchInterval: 5000, // D-10-15: cadence parity with useSafetyState
    staleTime: 5000, // D-10-15
    retry: 2,
    retryDelay: 1000,
  })
}

export default useCarryIns
