import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

/**
 * Custom hooks for Auto Trader and Trading Enhancements data
 *
 * Created: 2025-11-30
 *
 * Provides real-time access to:
 * - Auto Trader status (running, strategy mode, etc.)
 * - Trading Enhancements (Circuit Breaker, Kill Switch, Slippage Manager, etc.)
 * - Advanced Enhancements (Position Sizer, Smart Executor, Performance Analytics)
 */

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Throttle error logging: at most once per distinct URL+status per minute
const errorLogTimestamps = new Map()
const ERROR_LOG_INTERVAL_MS = 60000
function shouldLogError(url, status) {
  const key = `${url}|${status}`
  const now = Date.now()
  const last = errorLogTimestamps.get(key)
  if (last !== undefined && now - last < ERROR_LOG_INTERVAL_MS) return false
  errorLogTimestamps.set(key, now)
  return true
}

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const url = error.config?.url || 'unknown'
    const status = error.response?.status ?? 'network'
    if (shouldLogError(url, status)) {
      console.error('[useAutoTrader API] Error:', error.response?.data || error.message)
    }
    return Promise.reject(error)
  }
)

/**
 * Custom hook for fetching auto trader status with all enhancements
 * Auto-refetches every 10 seconds for real-time updates
 */
export function useAutoTraderStatus() {
  return useQuery({
    queryKey: ['auto-trader', 'status'],
    queryFn: () => api.get('/trading/status'),
    refetchInterval: 10000,
    staleTime: 8000,
    retry: 2,
    retryDelay: 1000,
  })
}

/**
 * Custom hook for fetching performance analytics report
 * Includes Sharpe, Sortino, VaR, CVaR metrics
 * Auto-refetches every 30 seconds
 */
export function usePerformanceAnalytics() {
  return useQuery({
    queryKey: ['auto-trader', 'performance-report'],
    queryFn: () => api.get('/trading/performance'),
    refetchInterval: 30000,
    staleTime: 25000,
    retry: 2,
    retryDelay: 1000,
  })
}

/**
 * Extract trading enhancements data from auto trader status
 * @param {Object} statusData - The auto trader status data
 * @returns {Object} - Extracted trading enhancements
 */
export function extractTradingEnhancements(statusData) {
  if (!statusData) return null

  // /api/trading/status wraps everything in `status: {}`. Accept either the
  // wrapped envelope or the inner object directly so the hook is shape-agnostic.
  const inner = statusData.status || statusData
  const tradingEnhancements = inner.trading_enhancements || {}
  const advancedEnhancements = inner.advanced_enhancements || {}

  // Real API field names live under nested config/stats. Map them into the
  // flat shape the component expects, with sensible fallbacks.
  const cb = tradingEnhancements.circuit_breaker || {}
  const ks = tradingEnhancements.kill_switch || {}
  const sm = tradingEnhancements.slippage_manager || {}
  const et = tradingEnhancements.execution_timer || {}
  const ps = advancedEnhancements.position_sizer || null
  const se = advancedEnhancements.smart_executor || null

  // Slippage values from the API are already percent units (e.g. 0.15 means
  // 0.15%). Component multiplies by 100 for display, so we divide here so
  // the round-trip lands on the right number.
  const pctToFraction = (pct) => (pct == null ? 0 : Number(pct) / 100)

  return {
    circuitBreaker: {
      state: cb.state || 'unknown',
      failures: cb.stats?.consecutive_failures ?? cb.consecutive_failures ?? 0,
      threshold: cb.config?.failure_threshold ?? cb.failure_threshold ?? 5,
      lastFailure: cb.stats?.last_failure ?? cb.last_failure_time,
    },
    killSwitch: {
      isActive: ks.is_active || false,
      reason: ks.activation_reason ?? ks.reason,
      activatedAt: ks.activation_time ?? ks.activated_at,
      thresholds: ks.thresholds || {},
    },
    slippageManager: {
      // Component does (val * 100).toFixed(2)% — pass the fraction.
      maxSlippage: pctToFraction(sm.config?.base_tolerance_pct ?? sm.max_slippage_percent),
      stats: {
        total_trades: sm.stats?.total_trades ?? 0,
        avg_slippage: pctToFraction(sm.stats?.avg_slippage_pct ?? sm.stats?.avg_slippage ?? 0),
        max_slippage: pctToFraction(sm.stats?.max_slippage_pct ?? sm.stats?.max_slippage ?? 0),
        rejected_count: sm.stats?.rejected_count ?? 0,
        rejection_rate: sm.stats?.rejection_rate ?? 0,
      },
    },
    executionTimer: {
      mode: et.mode || 'paper',
      minInterval:
        et.config?.position_check_interval ??
        et.min_interval_seconds ??
        60,
    },
    positionSizer: ps
      ? {
          // Component reads max_position_pct / kelly_fraction / default_method.
          ...ps,
          default_method: ps.method ?? ps.default_method,
        }
      : null,
    smartExecutor: se
      ? {
          // Component reads default_algorithm / max_slices / slice_interval.
          ...se,
          slice_interval:
            se.slice_interval ??
            (se.twap_duration_minutes != null
              ? Math.round((se.twap_duration_minutes * 60) / Math.max(1, se.max_slices || 1))
              : 0),
        }
      : null,
    performanceAnalytics: advancedEnhancements.performance_analytics || null,
  }
}

/**
 * Extract performance summary from auto trader status
 * @param {Object} statusData - The auto trader status data
 * @returns {Object} - Extracted performance summary
 */
export function extractPerformanceSummary(statusData) {
  if (!statusData) return null
  const inner = statusData.status || statusData
  if (!inner.performance_summary) return null

  const summary = inner.performance_summary

  return {
    sharpeRatio: summary.sharpe_ratio,
    sortinoRatio: summary.sortino_ratio,
    maxDrawdown: summary.max_drawdown,
    var95: summary.var_95,
    cvar95: summary.cvar_95,
    totalTrades: summary.total_trades,
    winningTrades: summary.winning_trades,
    winRate: summary.win_rate,
  }
}
