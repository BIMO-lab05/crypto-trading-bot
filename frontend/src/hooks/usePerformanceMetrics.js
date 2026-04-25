/**
 * usePerformanceMetrics.js - Real-Time Performance Metrics Hook
 *
 * Purpose: Custom React hook providing real-time performance metrics data
 * with WebSocket support for live updates and REST API fallback.
 *
 * Features:
 * - Real-time metrics via WebSocket
 * - REST API polling fallback
 * - Computed metrics from trade history
 * - Caching and data persistence
 * - Connection state management
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  analyticsAPI,
  WebSocketManager,
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
 * @param {boolean} options.enableWebSocket - Enable WebSocket for real-time updates
 * @param {number} options.pollingInterval - REST API polling interval in ms
 * @returns {Object} Performance metrics data and status
 */
export function usePerformanceMetrics(options = {}) {
  const {
    period = '30d',
    enableWebSocket = false, // WebSocket disabled by default until backend support
    pollingInterval = 30000, // 30 second polling
  } = options

  // Query client for cache management
  const queryClient = useQueryClient()

  // WebSocket connection state
  const [wsConnected, setWsConnected] = useState(false)
  const wsManagerRef = useRef(null)

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
  // WEBSOCKET CONNECTION (when enabled and backend supports it)
  // ============================================================================

  useEffect(() => {
    if (!enableWebSocket) return

    // Create WebSocket manager
    const wsManager = new WebSocketManager({
      url: `ws://${window.location.host}/ws/metrics`,
      maxReconnectAttempts: 5,
      reconnectDelay: 1000,
    })

    wsManagerRef.current = wsManager

    // Set up event handlers
    wsManager.on('connected', () => {
      console.log('[usePerformanceMetrics] WebSocket connected')
      setWsConnected(true)
      wsManager.subscribe('metrics')
      wsManager.subscribe('equity')
    })

    wsManager.on('disconnected', () => {
      console.log('[usePerformanceMetrics] WebSocket disconnected')
      setWsConnected(false)
    })

    wsManager.on('metrics', (data) => {
      // Update performance summary cache with real-time data
      queryClient.setQueryData(['analytics', 'performance', period], (old) => ({
        ...old,
        ...data,
      }))
    })

    wsManager.on('equity', (data) => {
      // Update trade history cache with new trade
      queryClient.setQueryData(['analytics', 'trades', period], (old) => {
        if (!old?.trades) return old
        return {
          ...old,
          trades: [...old.trades, data],
        }
      })
    })

    // Connect to WebSocket
    wsManager.connect().catch((error) => {
      console.warn('[usePerformanceMetrics] WebSocket connection failed, using REST polling')
    })

    // Cleanup on unmount
    return () => {
      wsManager.disconnect()
      wsManagerRef.current = null
    }
  }, [enableWebSocket, period, queryClient])

  // ============================================================================
  // COMPUTED DATA FROM TRADE HISTORY
  // ============================================================================

  // Extract trades array from response
  const trades = useMemo(() => {
    return tradeHistoryData?.trades || tradeHistoryData || []
  }, [tradeHistoryData])

  // Get initial balance from portfolio
  const initialBalance = useMemo(() => {
    return portfolioData?.total_equity || portfolioData?.balance?.total || 10000
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
    return calculatePerformanceMetrics(trades)
  }, [trades])

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

    // Connection status
    wsConnected,
    dataSource: wsConnected ? 'websocket' : 'rest',

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
