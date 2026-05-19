import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

/**
 * useSafetyState — single source of truth for the operator safety strip.
 *
 * Polls /api/config/safety-state every 5 seconds, matching the StatusBar
 * cadence per D-11 (06-CONTEXT.md). Powers DASH-03 (Phase 6 success
 * criterion 2: operator sees safety state at first glance).
 *
 * The backend endpoint (Plan 06-02, gateway commit b33e7ae) returns the
 * D-08 schema:
 *
 *   {
 *     trading_mode: "PAPER" | "LIVE",
 *     paper_trading_mode: boolean,
 *     auto_trading_enabled: boolean,
 *     emergency_stop: { active: boolean, mtime: <ISO string or null> },
 *     ml_predictions_enabled: boolean,
 *     sentiment_analysis_enabled: boolean,
 *     kill_switch: {
 *       daily_loss_armed: boolean,
 *       daily_pnl_pct: number,
 *       tripped: boolean
 *     },
 *     last_updated_at: <ISO string>
 *   }
 *
 * The axios client (services/api.js) has baseURL '/api' and a response
 * interceptor that unwraps `.data`, so the resolved value of api.get is
 * the body itself — no `.data.data` nesting.
 *
 * @returns React Query result: { data, isLoading, isFetching, isError,
 *   isSuccess, error, refetch }
 */
export function useSafetyState() {
  return useQuery({
    queryKey: ['safety-state'],
    queryFn: async () => {
      return await api.get('/config/safety-state')
    },
    refetchInterval: 5000, // D-11: match StatusBar polling cadence
    staleTime: 5000, // D-11
    retry: 2,
    retryDelay: 1000,
  })
}

export default useSafetyState
