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

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('[useAutoTrader API] Error:', error.response?.data || error.message)
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
    queryFn: async () => {
      console.log('[useAutoTraderStatus] Fetching auto trader status...')
      const response = await api.get('/trading/status')
      console.log('[useAutoTraderStatus] Received data:', response)
      return response
    },
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
    queryFn: async () => {
      console.log('[usePerformanceAnalytics] Fetching performance report...')
      const response = await api.get('/trading/performance')
      console.log('[usePerformanceAnalytics] Received data:', response)
      return response
    },
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

  const tradingEnhancements = statusData.trading_enhancements || {}
  const advancedEnhancements = statusData.advanced_enhancements || {}

  return {
    circuitBreaker: {
      state: tradingEnhancements.circuit_breaker?.state || 'unknown',
      failures: tradingEnhancements.circuit_breaker?.consecutive_failures || 0,
      threshold: tradingEnhancements.circuit_breaker?.failure_threshold || 5,
      lastFailure: tradingEnhancements.circuit_breaker?.last_failure_time,
    },
    killSwitch: {
      isActive: tradingEnhancements.kill_switch?.is_active || false,
      reason: tradingEnhancements.kill_switch?.reason,
      activatedAt: tradingEnhancements.kill_switch?.activated_at,
      thresholds: tradingEnhancements.kill_switch?.thresholds || {},
    },
    slippageManager: {
      maxSlippage: tradingEnhancements.slippage_manager?.max_slippage_percent || 0,
      stats: tradingEnhancements.slippage_manager?.stats || {
        total_trades: 0,
        avg_slippage: 0,
        max_slippage: 0,
      },
    },
    executionTimer: {
      mode: tradingEnhancements.execution_timer?.mode || 'paper',
      minInterval: tradingEnhancements.execution_timer?.min_interval_seconds || 60,
    },
    positionSizer: advancedEnhancements.position_sizer || null,
    smartExecutor: advancedEnhancements.smart_executor || null,
    performanceAnalytics: advancedEnhancements.performance_analytics || null,
  }
}

/**
 * Extract performance summary from auto trader status
 * @param {Object} statusData - The auto trader status data
 * @returns {Object} - Extracted performance summary
 */
export function extractPerformanceSummary(statusData) {
  if (!statusData?.performance_summary) return null

  const summary = statusData.performance_summary

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
