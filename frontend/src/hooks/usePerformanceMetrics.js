/**
 * usePerformanceMetrics.js - Performance Metrics Hook (REST polling)
 *
 * Provides performance metrics, equity curve, drawdown series, returns
 * distribution, and trade statistics via REST polling against the
 * trading-engine analytics endpoints.
 *
 * The hook used to support a WebSocket path against `/ws/metrics`, but
 * the gateway never had that endpoint implemented (only `/ws` exists)
 * — every connection failed silently and fell through to REST polling
 * anyway. The WebSocket scaffolding was stripped 2026-04-29 (audit
 * follow-up); if/when a server-side metrics push is added, reintroduce
 * a WebSocket layer deliberately rather than reviving this dead path.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11 (WebSocket scaffolding removed 2026-04-29)
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import { useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  analyticsAPI,
  calculateEquityCurve,
  calculateDrawdownSeries,
  calculateReturnsDistribution,
  calculatePerformanceMetrics,
} from '../services/analyticsApi'

// ============================================================================
// MAIN PERFORMANCE METRICS HOOK
// ============================================================================

/**
 * usePerformanceMetrics - Comprehensive performance metrics hook
 *
 * Provides:
 * - Real-time performance summary (Sharpe, Sortino, VaR, etc.)
 * - Equity curve data for charting
 * - Drawdown series for visualization
 * - Returns distribution for histogram
 * - Trade statistics
 *
 * @param {Object} options - Hook options
 * @param {string} options.period - Time period ('1d', '7d', '30d', '90d', 'all')
 * @param {number} options.pollingInterval - REST API polling interval in ms
 * @returns {Object} Performance metrics data and status
 */
export function usePerformanceMetrics(options = {}) {
  const {
    period = '30d',
    pollingInterval = 30000, // 30 second polling
  } = options

  // ============================================================================
  // REST API QUERIES
  // ============================================================================

  // Fetch performance summary from backend
  const {
    data: performanceSummary,
    isLoading: summaryLoading,
    isError: summaryError,
    error: summaryErrorDetails,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['analytics', 'performance', period],
    queryFn: () => analyticsAPI.getPerformanceSummary({ period }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
    retryDelay: 1000,
  })

  // Fetch trade history for client-side calculations
  const {
    data: tradeHistoryData,
    isLoading: historyLoading,
    isError: historyError,
    error: historyErrorDetails,
    refetch: refetchHistory,
  } = useQuery({
    queryKey: ['analytics', 'trades', period],
    queryFn: () => analyticsAPI.getTradeHistory({ limit: 1000, status: 'CLOSED' }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
    retryDelay: 1000,
  })

  // Fetch portfolio metrics
  const {
    data: portfolioData,
    isLoading: portfolioLoading,
    isError: portfolioError,
  } = useQuery({
    queryKey: ['analytics', 'portfolio'],
    queryFn: () => analyticsAPI.getPortfolioMetrics(),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
  })

  // ============================================================================
  // COMPUTED DATA FROM TRADE HISTORY
  // ============================================================================

  // Extract trades array from response
  const trades = useMemo(() => {
    return tradeHistoryData?.trades || tradeHistoryData || []
  }, [tradeHistoryData])

  // Get initial balance from portfolio. The portfolio-manager API returns
  // `total_value` and `cash_balance`; older shapes used `total_equity` /
  // `balance.total`. Fall back to the paper-trading default ($100) so the
  // equity curve and drawdown scale correctly when the API is unreachable.
  const initialBalance = useMemo(() => {
    const raw =
      portfolioData?.total_value ??
      portfolioData?.cash_balance ??
      portfolioData?.total_equity ??
      portfolioData?.balance?.total ??
      100
    const parsed = typeof raw === 'string' ? parseFloat(raw) : raw
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 100
  }, [portfolioData])

  // Calculate equity curve from trades
  const equityCurve = useMemo(() => {
    if (trades.length === 0) return []
    return calculateEquityCurve(trades, initialBalance)
  }, [trades, initialBalance])

  // Calculate drawdown series from equity curve
  const drawdownSeries = useMemo(() => {
    if (equityCurve.length === 0) return []
    return calculateDrawdownSeries(equityCurve)
  }, [equityCurve])

  // Calculate returns distribution
  const returnsDistribution = useMemo(() => {
    if (trades.length === 0) return { bins: [], stats: null }
    return calculateReturnsDistribution(trades, 20)
  }, [trades])

  // Calculate client-side metrics (supplement backend metrics)
  const calculatedMetrics = useMemo(() => {
    if (trades.length === 0) return null
    return calculatePerformanceMetrics(trades, initialBalance)
  }, [trades, initialBalance])

  // ============================================================================
  // MERGED METRICS (Backend + Calculated)
  // ============================================================================

  const metrics = useMemo(() => {
    // Start with backend performance summary
    const backendMetrics = performanceSummary?.metrics || performanceSummary || {}

    // Merge with calculated metrics (prefer backend values when available)
    return {
      // From backend
      sharpeRatio: backendMetrics.sharpe_ratio ?? calculatedMetrics?.sharpeRatio ?? null,
      sortinoRatio: backendMetrics.sortino_ratio ?? calculatedMetrics?.sortinoRatio ?? null,
      maxDrawdown: backendMetrics.max_drawdown ?? calculatedMetrics?.maxDrawdown ?? null,
      maxDrawdownPercent:
        backendMetrics.max_drawdown_percent ?? calculatedMetrics?.maxDrawdownPercent ?? null,
      var95: backendMetrics.var_95 ?? calculatedMetrics?.var95 ?? null,
      cvar95: backendMetrics.cvar_95 ?? calculatedMetrics?.cvar95 ?? null,

      // Trade statistics
      totalTrades: backendMetrics.total_trades ?? calculatedMetrics?.totalTrades ?? 0,
      winningTrades: backendMetrics.winning_trades ?? calculatedMetrics?.winningTrades ?? 0,
      losingTrades: backendMetrics.losing_trades ?? calculatedMetrics?.losingTrades ?? 0,
      winRate: backendMetrics.win_rate ?? calculatedMetrics?.winRate ?? 0,

      // P&L metrics
      totalPnL: backendMetrics.total_pnl ?? calculatedMetrics?.totalPnL ?? 0,
      avgPnL: backendMetrics.avg_pnl ?? calculatedMetrics?.avgPnL ?? 0,
      avgWin: backendMetrics.avg_win ?? calculatedMetrics?.avgWin ?? 0,
      avgLoss: backendMetrics.avg_loss ?? calculatedMetrics?.avgLoss ?? 0,
      profitFactor: backendMetrics.profit_factor ?? calculatedMetrics?.profitFactor ?? 0,

      // Additional metrics from calculations
      grossProfit: calculatedMetrics?.grossProfit ?? 0,
      grossLoss: calculatedMetrics?.grossLoss ?? 0,
      stdDev: calculatedMetrics?.stdDev ?? 0,
      expectancy: calculatedMetrics?.expectancy ?? 0,
      recoveryFactor: calculatedMetrics?.recoveryFactor ?? 0,

      // Timestamp
      lastUpdated: backendMetrics.timestamp || Date.now(),
    }
  }, [performanceSummary, calculatedMetrics])

  // ============================================================================
  // MANUAL REFRESH FUNCTION
  // ============================================================================

  const refresh = useCallback(async () => {
    console.log('[usePerformanceMetrics] Manual refresh triggered')
    await Promise.all([refetchSummary(), refetchHistory()])
  }, [refetchSummary, refetchHistory])

  // ============================================================================
  // RETURN VALUE
  // ============================================================================

  return {
    // Loading states
    isLoading: summaryLoading || historyLoading || portfolioLoading,
    isError: summaryError || historyError || portfolioError,
    error: summaryErrorDetails || historyErrorDetails,

    // Connection status. WebSocket support was removed when the
    // server-side `/ws/metrics` route turned out to never have been
    // implemented; this hook is now REST-polling only. Field kept for
    // back-compat with the dashboard's <ConnectionStatus> indicator.
    dataSource: 'rest',

    // Core metrics
    metrics,

    // Chart data
    equityCurve,
    drawdownSeries,
    returnsDistribution,

    // Raw data
    trades,
    tradeCount: trades.length,
    portfolioData,

    // Actions
    refresh,
  }
}

// ============================================================================
// SPECIALIZED HOOKS FOR SPECIFIC DATA TYPES
// ============================================================================

/**
 * useEquityCurve - Hook for fetching equity curve data
 *
 * @param {Object} options - Query options
 * @returns {Object} Equity curve data and status
 */
export function useEquityCurve(options = {}) {
  const { period = '30d', interval = '1h', pollingInterval = 60000 } = options

  // Try fetching from backend first
  const backendQuery = useQuery({
    queryKey: ['equity-curve', period, interval],
    queryFn: () => analyticsAPI.getEquityCurve({ period, interval }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
    // Don't throw on error - we'll fall back to calculated values
    throwOnError: false,
  })

  // Fallback: calculate from trade history
  const historyQuery = useQuery({
    queryKey: ['analytics', 'trades', period],
    queryFn: () => analyticsAPI.getTradeHistory({ limit: 1000, status: 'CLOSED' }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    enabled: !backendQuery.data || backendQuery.isError,
  })

  // Calculate equity curve from trades if backend doesn't provide it
  const calculatedCurve = useMemo(() => {
    const trades = historyQuery.data?.trades || historyQuery.data || []
    if (trades.length === 0) return []
    return calculateEquityCurve(trades, 10000)
  }, [historyQuery.data])

  return {
    data: backendQuery.data?.curve || backendQuery.data || calculatedCurve,
    isLoading: backendQuery.isLoading || historyQuery.isLoading,
    isError: backendQuery.isError && historyQuery.isError,
    error: backendQuery.error || historyQuery.error,
    dataSource: backendQuery.data ? 'backend' : 'calculated',
  }
}

/**
 * useDrawdownData - Hook for fetching drawdown data
 *
 * @param {Object} options - Query options
 * @returns {Object} Drawdown data and status
 */
export function useDrawdownData(options = {}) {
  const { period = '30d', pollingInterval = 60000 } = options

  // Try fetching from backend
  const backendQuery = useQuery({
    queryKey: ['drawdown', period],
    queryFn: () => analyticsAPI.getDrawdownHistory({ period }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
    throwOnError: false,
  })

  // Fallback: use equity curve hook and calculate drawdown
  const equityCurveData = useEquityCurve({ period, pollingInterval })

  const calculatedDrawdown = useMemo(() => {
    if (equityCurveData.data?.length > 0) {
      return calculateDrawdownSeries(equityCurveData.data)
    }
    return []
  }, [equityCurveData.data])

  return {
    data: backendQuery.data?.drawdown || backendQuery.data || calculatedDrawdown,
    isLoading: backendQuery.isLoading || equityCurveData.isLoading,
    isError: backendQuery.isError && equityCurveData.isError,
    error: backendQuery.error || equityCurveData.error,
    currentDrawdown: calculatedDrawdown[calculatedDrawdown.length - 1]?.drawdownPercent || 0,
    maxDrawdown: Math.max(...calculatedDrawdown.map((d) => d.drawdownPercent), 0),
    dataSource: backendQuery.data ? 'backend' : 'calculated',
  }
}

/**
 * useReturnsDistribution - Hook for returns distribution data
 *
 * @param {Object} options - Query options
 * @returns {Object} Returns distribution data and status
 */
export function useReturnsDistribution(options = {}) {
  const { period = '30d', bins = 20, pollingInterval = 60000 } = options

  // Try fetching from backend
  const backendQuery = useQuery({
    queryKey: ['returns-distribution', period, bins],
    queryFn: () => analyticsAPI.getReturnsDistribution({ period, bins }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
    throwOnError: false,
  })

  // Fallback: calculate from trade history
  const historyQuery = useQuery({
    queryKey: ['analytics', 'trades', period],
    queryFn: () => analyticsAPI.getTradeHistory({ limit: 1000, status: 'CLOSED' }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    enabled: !backendQuery.data || backendQuery.isError,
  })

  const calculatedDistribution = useMemo(() => {
    const trades = historyQuery.data?.trades || historyQuery.data || []
    if (trades.length === 0) return { bins: [], stats: null }
    return calculateReturnsDistribution(trades, bins)
  }, [historyQuery.data, bins])

  return {
    bins: backendQuery.data?.bins || calculatedDistribution.bins,
    stats: backendQuery.data?.stats || calculatedDistribution.stats,
    isLoading: backendQuery.isLoading || historyQuery.isLoading,
    isError: backendQuery.isError && historyQuery.isError,
    error: backendQuery.error || historyQuery.error,
    dataSource: backendQuery.data ? 'backend' : 'calculated',
  }
}

/**
 * useCorrelationMatrix - Hook for asset correlation data
 *
 * @param {Object} options - Query options
 * @returns {Object} Correlation matrix data and status
 */
export function useCorrelationMatrix(options = {}) {
  const {
    period = '30d',
    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT'],
    pollingInterval = 300000, // 5 minutes - correlations change slowly
  } = options

  return useQuery({
    queryKey: ['correlation-matrix', period, symbols.join(',')],
    queryFn: () => analyticsAPI.getCorrelationMatrix({ period, symbols: symbols.join(',') }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 30000,
    retry: 2,
    // Return empty matrix if API doesn't support it yet
    select: (data) => data || { matrix: [], symbols: [], timestamp: Date.now() },
  })
}

/**
 * useTradeStatistics - Hook for detailed trade statistics
 *
 * @param {Object} options - Query options
 * @returns {Object} Trade statistics data and status
 */
export function useTradeStatistics(options = {}) {
  const { period = '30d', symbol = null, pollingInterval = 30000 } = options

  return useQuery({
    queryKey: ['trade-statistics', period, symbol],
    queryFn: () => analyticsAPI.getTradeStatistics({ period, symbol }),
    refetchInterval: pollingInterval,
    staleTime: pollingInterval - 5000,
    retry: 2,
  })
}

// Default export
export default usePerformanceMetrics
