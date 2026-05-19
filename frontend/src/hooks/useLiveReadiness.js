import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

/**
 * useLiveReadiness — polls the PREFLIGHT live-readiness endpoint every 5 s.
 *
 * Matches the useSafetyState cadence per D-10-15 (06-CONTEXT.md D-11:
 * "cadence parity with useSafetyState").  Powers DASHLIVE-01 (Phase 10
 * success criterion: operator sees per-check PASS/FAIL/UNKNOWN detail rows).
 *
 * The axios client (services/api.js) has baseURL '/api' and a response
 * interceptor that unwraps `.data`, so the resolved value of api.get is
 * the body itself — no `.data.data` nesting.
 *
 * Response body shape (from services/trading-engine/app/handlers/preflight.py
 * + api-gateway proxy at main.py:1168-1231):
 *
 *   {
 *     schema_version: 1,
 *     overall:        "PASS" | "FAIL" | "UNKNOWN",
 *     evaluated_at:   <ISO string>,
 *     checks: [
 *       { check: string, status: "PASS" | "FAIL" | "UNKNOWN", detail: string },
 *       // six checks: cap, paper_mode, trading_mode, ack, emergency_stop, dsr_evidence
 *     ]
 *   }
 *
 * Per D-10-16 (load-bearing): this hook's data is used ONLY for per-check
 * detail rows when carryInsQuery.data.live_readiness?.checks is absent
 * (degraded payload). The banner overall + 24h window are read from
 * useCarryIns() — which is the authoritative source for overall and window.
 * If this hook and useCarryIns disagree (race between refetches), trust
 * useCarryIns.
 *
 * @returns React Query result: { data, isLoading, isFetching, isError,
 *   isSuccess, error, refetch }
 */
export function useLiveReadiness() {
  return useQuery({
    queryKey: ['preflight-live-readiness'],
    queryFn: async () => {
      return await api.get('/preflight/live-readiness')
    },
    refetchInterval: 5000, // D-10-15: cadence parity with useSafetyState
    staleTime: 5000, // D-10-15
    retry: 2,
    retryDelay: 1000,
  })
}

export default useLiveReadiness
