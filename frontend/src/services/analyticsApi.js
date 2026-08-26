/**
 * analyticsApi.js - Analytics API Integration Layer
 *
 * Purpose: Provides API methods for fetching performance analytics data
 * including equity curves, drawdown data, returns distribution, and correlation metrics.
 *
 * Features:
 * - RESTful API endpoints for performance metrics
 * - WebSocket connection for real-time updates
 * - Error handling and retry logic
 * - Data transformation utilities
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import axios from 'axios'
import { PAPER_DEFAULT_BALANCE } from '../utils/balance'

// ============================================================================
// API CLIENT CONFIGURATION
// ============================================================================

/**
 * Create axios instance with default configuration for analytics endpoints
 * Timeout increased for complex calculations that may take longer
 */
const analyticsClient = axios.create({
  baseURL: '/api',
  timeout: 30000, // 30 seconds for complex analytics queries
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for auth (future enhancement)
analyticsClient.interceptors.request.use(
  (config) => config,
  (error) => {
    console.error('[analyticsApi] Request error:', error)
    return Promise.reject(error)
  }
)

// Throttle error logging: at most once per distinct URL+status per minute
// so polled endpoints that fail don't flood the console.
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

// Response interceptor for error handling and data extraction
analyticsClient.interceptors.response.use(
  (response) => {
    // Extract data from response wrapper if present
    return response.data
  },
  (error) => {
    const url = error.config?.url || 'unknown'
    const status = error.response?.status ?? 'network'
    if (shouldLogError(url, status)) {
      console.error('[analyticsApi] Response error:', error.response?.data || error.message)
    }
    return Promise.reject(error)
  }
)

// ============================================================================
// PERFORMANCE METRICS API
// ============================================================================

/**
 * analyticsAPI - Performance Analytics Endpoints
 *
 * Provides access to:
 * - Summary metrics (Sharpe, Sortino, Max DD, etc.)
 * - Equity curve data
 * - Drawdown history
 * - Returns distribution
 * - Asset correlation matrix
 * - Trade statistics
 */
export const analyticsAPI = {
  /**
   * Get comprehensive performance summary
   * Includes all key metrics: Sharpe, Sortino, VaR, CVaR, Max Drawdown
   *
   * @param {Object} params - Query parameters
   * @param {string} params.period - Time period ('1d', '7d', '30d', '90d', 'all')
   * @returns {Promise<Object>} Performance summary data
   */
  getPerformanceSummary: (params = {}) =>
    analyticsClient.get('/trading/performance', { params }),

  /**
   * Get equity curve data for charting
   * Returns time-series data of portfolio value over time
   *
   * @param {Object} params - Query parameters
   * @param {string} params.period - Time period ('1d', '7d', '30d', '90d', 'all')
   * @param {string} params.interval - Data interval ('1m', '5m', '15m', '1h', '4h', '1d')
   * @returns {Promise<Array>} Equity curve data points
   */
  getEquityCurve: (params = { period: '30d', interval: '1h' }) =>
    analyticsClient.get('/trading/equity-curve', { params }),

  /**
   * Get drawdown history data
   * Returns drawdown values over time for visualization
   *
   * @param {Object} params - Query parameters
   * @param {string} params.period - Time period ('7d', '30d', '90d', 'all')
   * @returns {Promise<Array>} Drawdown history data
   */
  getDrawdownHistory: (params = { period: '30d' }) =>
    analyticsClient.get('/trading/drawdown', { params }),

  /**
   * Get returns distribution data
   * Returns histogram data for returns distribution visualization
   *
   * @param {Object} params - Query parameters
   * @param {string} params.period - Time period
   * @param {number} params.bins - Number of histogram bins (default: 20)
   * @returns {Promise<Object>} Returns distribution data
   */
  getReturnsDistribution: (params = { period: '30d', bins: 20 }) =>
    analyticsClient.get('/trading/returns-distribution', { params }),

  /**
   * Get asset correlation matrix
   * Returns correlation coefficients between traded assets
   *
   * @param {Object} params - Query parameters
   * @param {string} params.period - Lookback period for correlation calculation
   * @param {Array<string>} params.symbols - Symbols to include in correlation
   * @returns {Promise<Object>} Correlation matrix data
   */
  getCorrelationMatrix: (params = { period: '30d' }) =>
    analyticsClient.get('/trading/correlations', { params }),

  /**
   * Get detailed trade statistics
   * Returns win rate, profit factor, avg win/loss, etc.
   *
   * @param {Object} params - Query parameters
   * @param {string} params.period - Time period
   * @param {string} params.symbol - Optional symbol filter
   * @returns {Promise<Object>} Trade statistics
   */
  getTradeStatistics: (params = {}) =>
    analyticsClient.get('/trading/statistics', { params }),

  /**
   * Get trade history with P&L details
   * Returns list of closed trades for analysis
   *
   * @param {Object} params - Query parameters
   * @param {number} params.limit - Maximum number of trades
   * @param {number} params.offset - Pagination offset
   * @param {string} params.status - Trade status filter ('CLOSED', 'ALL')
   * @returns {Promise<Object>} Trade history data
   */
  getTradeHistory: (params = { limit: 1000, status: 'CLOSED' }) =>
    analyticsClient.get('/trading/trades/history', { params }),

  /**
   * Get real-time portfolio metrics
   * Returns current portfolio value and key metrics
   *
   * @returns {Promise<Object>} Real-time portfolio data
   */
  getPortfolioMetrics: () =>
    analyticsClient.get('/portfolio'),

  /**
   * Get trading status including performance summary
   *
   * @returns {Promise<Object>} Trading status data
   */
  getTradingStatus: () =>
    analyticsClient.get('/trading/status'),
}


// ============================================================================
// DATA TRANSFORMATION UTILITIES
// ============================================================================

/**
 * Transform raw trade data into equity curve data points
 *
 * @param {Array} trades - Array of trade objects
 * @param {number} initialBalance - Starting balance
 * @returns {Array} Equity curve data points
 */
export function calculateEquityCurve(trades, initialBalance = PAPER_DEFAULT_BALANCE) {
  // Guard against non-array payloads (e.g. an error object) before spreading/sorting
  if (!Array.isArray(trades) || trades.length === 0) {
    return [{ timestamp: Date.now(), equity: initialBalance, pnl: 0 }]
  }

  // Sort trades by close time
  const sortedTrades = [...trades].sort(
    (a, b) => new Date(a.closed_at || a.timestamp) - new Date(b.closed_at || b.timestamp)
  )

  let cumulativeEquity = initialBalance
  const equityCurve = [
    {
      timestamp: sortedTrades[0]?.closed_at || Date.now(),
      equity: initialBalance,
      pnl: 0,
      tradeCount: 0,
    },
  ]

  sortedTrades.forEach((trade, index) => {
    const pnl = parseFloat(trade.realized_pnl || 0)
    cumulativeEquity += pnl

    equityCurve.push({
      timestamp: trade.closed_at || trade.timestamp,
      equity: cumulativeEquity,
      pnl: pnl,
      cumulativePnl: cumulativeEquity - initialBalance,
      tradeCount: index + 1,
    })
  })

  return equityCurve
}

/**
 * Calculate drawdown series from equity curve
 *
 * @param {Array} equityCurve - Equity curve data points
 * @returns {Array} Drawdown data points
 */
export function calculateDrawdownSeries(equityCurve) {
  if (!equityCurve || equityCurve.length === 0) {
    return []
  }

  let peak = equityCurve[0].equity
  const drawdownSeries = []

  equityCurve.forEach((point) => {
    // Update peak if current equity is higher
    if (point.equity > peak) {
      peak = point.equity
    }

    // Calculate drawdown from peak
    const drawdown = peak > 0 ? (peak - point.equity) / peak : 0
    const drawdownValue = point.equity - peak

    drawdownSeries.push({
      timestamp: point.timestamp,
      drawdown: drawdown, // Percentage (0 to 1)
      drawdownPercent: drawdown * 100, // Percentage (0 to 100)
      drawdownValue: drawdownValue, // Absolute value (negative)
      equity: point.equity,
      peak: peak,
    })
  })

  return drawdownSeries
}

/**
 * Calculate returns distribution for histogram
 *
 * @param {Array} trades - Array of trade objects
 * @param {number} bins - Number of histogram bins
 * @returns {Object} Returns distribution data
 */
export function calculateReturnsDistribution(trades, bins = 20) {
  if (!trades || trades.length === 0) {
    return { bins: [], stats: null }
  }

  // Extract returns from trades
  const returns = trades
    .filter((t) => t.realized_pnl != null)
    .map((t) => parseFloat(t.realized_pnl))

  if (returns.length === 0) {
    return { bins: [], stats: null }
  }

  // Calculate statistics
  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length
  const stdDev = Math.sqrt(variance)
  const min = Math.min(...returns)
  const max = Math.max(...returns)
  const sortedReturns = [...returns].sort((a, b) => a - b)
  const median = sortedReturns[Math.floor(returns.length / 2)]

  // Calculate skewness
  const skewness =
    returns.reduce((sum, r) => sum + Math.pow((r - mean) / stdDev, 3), 0) / returns.length

  // Calculate kurtosis
  const kurtosis =
    returns.reduce((sum, r) => sum + Math.pow((r - mean) / stdDev, 4), 0) / returns.length - 3

  // Create histogram bins
  const binWidth = (max - min) / bins
  const histogram = []

  for (let i = 0; i < bins; i++) {
    const binStart = min + i * binWidth
    const binEnd = binStart + binWidth
    const count = returns.filter((r) => r >= binStart && (i === bins - 1 ? r <= binEnd : r < binEnd))
      .length

    histogram.push({
      binStart,
      binEnd,
      binMid: (binStart + binEnd) / 2,
      count,
      frequency: count / returns.length,
    })
  }

  return {
    bins: histogram,
    stats: {
      count: returns.length,
      mean,
      median,
      stdDev,
      variance,
      min,
      max,
      skewness,
      kurtosis,
      range: max - min,
    },
  }
}

/**
 * Calculate performance metrics from trade history
 *
 * @param {Array} trades - Array of trade objects
 * @param {number} initialBalance - Starting balance used as the equity-curve baseline (defaults to PAPER_DEFAULT_BALANCE — $10,000 per ADR-029)
 * @returns {Object} Performance metrics
 */
export function calculatePerformanceMetrics(trades, initialBalance = PAPER_DEFAULT_BALANCE) {
  if (!trades || trades.length === 0) {
    return null
  }

  const pnls = trades
    .filter((t) => t.realized_pnl != null)
    .map((t) => parseFloat(t.realized_pnl))

  if (pnls.length === 0) {
    return null
  }

  // Basic stats
  const totalTrades = pnls.length
  const winningTrades = pnls.filter((p) => p > 0).length
  const losingTrades = pnls.filter((p) => p < 0).length
  const winRate = (winningTrades / totalTrades) * 100

  // P&L stats
  const totalPnL = pnls.reduce((sum, p) => sum + p, 0)
  const avgPnL = totalPnL / totalTrades
  const avgWin =
    winningTrades > 0
      ? pnls.filter((p) => p > 0).reduce((sum, p) => sum + p, 0) / winningTrades
      : 0
  const avgLoss =
    losingTrades > 0
      ? Math.abs(pnls.filter((p) => p < 0).reduce((sum, p) => sum + p, 0)) / losingTrades
      : 0

  // Profit factor
  const grossProfit = pnls.filter((p) => p > 0).reduce((sum, p) => sum + p, 0)
  const grossLoss = Math.abs(pnls.filter((p) => p < 0).reduce((sum, p) => sum + p, 0))
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0

  // Risk metrics
  const variance = pnls.reduce((sum, p) => sum + Math.pow(p - avgPnL, 2), 0) / totalTrades
  const stdDev = Math.sqrt(variance)

  // Downside deviation (for Sortino)
  const downsidePnls = pnls.filter((p) => p < 0)
  const downsideVariance =
    downsidePnls.length > 0
      ? downsidePnls.reduce((sum, p) => sum + Math.pow(p, 2), 0) / downsidePnls.length
      : 0
  const downsideDev = Math.sqrt(downsideVariance)

  // Sharpe Ratio (assuming risk-free rate = 0 for crypto)
  const sharpeRatio = stdDev !== 0 ? avgPnL / stdDev : 0

  // Sortino Ratio
  const sortinoRatio = downsideDev !== 0 ? avgPnL / downsideDev : 0

  // Max Drawdown — computed against equity curve, not raw cumulative P&L.
  // Tracks running peak of equity and the worst peak-to-trough percentage seen,
  // bounding maxDrawdownPercent to the 0–100 range.
  let cumulativePnL = 0
  let equity = initialBalance
  let peakEquity = initialBalance
  let maxDrawdown = 0
  let maxDrawdownPercent = 0

  pnls.forEach((pnl) => {
    cumulativePnL += pnl
    equity = initialBalance + cumulativePnL
    if (equity > peakEquity) peakEquity = equity
    const drawdown = peakEquity - equity
    const drawdownPercent = peakEquity > 0 ? (drawdown / peakEquity) * 100 : 0
    if (drawdown > maxDrawdown) maxDrawdown = drawdown
    if (drawdownPercent > maxDrawdownPercent) maxDrawdownPercent = drawdownPercent
  })

  // VaR 95% - sort P&Ls and find 5th percentile
  const sortedPnLs = [...pnls].sort((a, b) => a - b)
  const var95Index = Math.floor(totalTrades * 0.05)
  const var95 = Math.abs(sortedPnLs[var95Index] || 0)

  // CVaR 95% - average of losses beyond VaR
  const lossesBeforeVar = sortedPnLs.slice(0, var95Index + 1)
  const cvar95 =
    lossesBeforeVar.length > 0
      ? Math.abs(lossesBeforeVar.reduce((sum, p) => sum + p, 0) / lossesBeforeVar.length)
      : 0

  // Expectancy
  const expectancy = winRate / 100 * avgWin - (1 - winRate / 100) * avgLoss

  // Recovery factor
  const recoveryFactor = maxDrawdown > 0 ? totalPnL / maxDrawdown : 0

  return {
    // Trade counts
    totalTrades,
    winningTrades,
    losingTrades,
    winRate,

    // P&L metrics
    totalPnL,
    avgPnL,
    avgWin,
    avgLoss,
    grossProfit,
    grossLoss,
    profitFactor,

    // Risk metrics
    stdDev,
    variance,
    downsideDev,

    // Risk-adjusted returns
    sharpeRatio,
    sortinoRatio,

    // Drawdown
    maxDrawdown,
    maxDrawdownPercent,

    // VaR metrics
    var95,
    cvar95,

    // Other metrics
    expectancy,
    recoveryFactor,
  }
}

export default analyticsAPI
