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

// Request interceptor for logging and auth (future enhancement)
analyticsClient.interceptors.request.use(
  (config) => {
    console.log(`[analyticsApi] ${config.method?.toUpperCase()} ${config.url}`)
    return config
  },
  (error) => {
    console.error('[analyticsApi] Request error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor for error handling and data extraction
analyticsClient.interceptors.response.use(
  (response) => {
    // Extract data from response wrapper if present
    return response.data
  },
  (error) => {
    console.error('[analyticsApi] Response error:', error.response?.data || error.message)
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
// WEBSOCKET CONNECTION FOR REAL-TIME UPDATES
// ============================================================================

/**
 * WebSocketManager - Manages WebSocket connection for real-time metrics
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Message parsing and event dispatching
 * - Connection state management
 * - Heartbeat/ping-pong handling
 */
export class WebSocketManager {
  constructor(options = {}) {
    // WebSocket connection URL (default to trading engine WebSocket)
    this.url = options.url || `ws://${window.location.host}/ws/metrics`

    // Connection state
    this.ws = null
    this.isConnected = false
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = options.maxReconnectAttempts || 10
    this.reconnectDelay = options.reconnectDelay || 1000

    // Event listeners
    this.listeners = new Map()

    // Heartbeat configuration
    this.heartbeatInterval = options.heartbeatInterval || 30000
    this.heartbeatTimer = null

    // Bind methods to preserve context
    this.connect = this.connect.bind(this)
    this.disconnect = this.disconnect.bind(this)
    this.handleOpen = this.handleOpen.bind(this)
    this.handleClose = this.handleClose.bind(this)
    this.handleError = this.handleError.bind(this)
    this.handleMessage = this.handleMessage.bind(this)
  }

  /**
   * Connect to WebSocket server
   *
   * @returns {Promise<void>} Resolves when connected
   */
  connect() {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        console.log('[WebSocketManager] Already connected')
        resolve()
        return
      }

      console.log(`[WebSocketManager] Connecting to ${this.url}`)

      try {
        this.ws = new WebSocket(this.url)

        this.ws.onopen = (event) => {
          this.handleOpen(event)
          resolve()
        }

        this.ws.onclose = this.handleClose
        this.ws.onerror = (event) => {
          this.handleError(event)
          reject(new Error('WebSocket connection failed'))
        }
        this.ws.onmessage = this.handleMessage
      } catch (error) {
        console.error('[WebSocketManager] Connection error:', error)
        reject(error)
      }
    })
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect() {
    console.log('[WebSocketManager] Disconnecting')

    // Clear heartbeat timer
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }

    // Close WebSocket connection
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    this.isConnected = false
    this.reconnectAttempts = 0
  }

  /**
   * Handle WebSocket open event
   *
   * @param {Event} event - Open event
   */
  handleOpen(event) {
    console.log('[WebSocketManager] Connected')
    this.isConnected = true
    this.reconnectAttempts = 0

    // Start heartbeat
    this.startHeartbeat()

    // Emit connection event
    this.emit('connected', { timestamp: Date.now() })
  }

  /**
   * Handle WebSocket close event
   *
   * @param {CloseEvent} event - Close event
   */
  handleClose(event) {
    console.log(`[WebSocketManager] Disconnected: ${event.code} - ${event.reason}`)
    this.isConnected = false

    // Stop heartbeat
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }

    // Emit disconnection event
    this.emit('disconnected', { code: event.code, reason: event.reason })

    // Attempt reconnection if not intentionally closed
    if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.scheduleReconnect()
    }
  }

  /**
   * Handle WebSocket error event
   *
   * @param {Event} event - Error event
   */
  handleError(event) {
    console.error('[WebSocketManager] Error:', event)
    this.emit('error', { error: event })
  }

  /**
   * Handle incoming WebSocket message
   *
   * @param {MessageEvent} event - Message event
   */
  handleMessage(event) {
    try {
      const data = JSON.parse(event.data)

      // Handle different message types
      switch (data.type) {
        case 'pong':
          // Heartbeat response received
          console.log('[WebSocketManager] Heartbeat acknowledged')
          break

        case 'metrics':
          // Performance metrics update
          this.emit('metrics', data.payload)
          break

        case 'equity':
          // Equity curve update
          this.emit('equity', data.payload)
          break

        case 'drawdown':
          // Drawdown update
          this.emit('drawdown', data.payload)
          break

        case 'trade':
          // New trade notification
          this.emit('trade', data.payload)
          break

        default:
          // Generic data event
          this.emit('data', data)
      }
    } catch (error) {
      console.error('[WebSocketManager] Message parse error:', error)
    }
  }

  /**
   * Send message to WebSocket server
   *
   * @param {Object} data - Data to send
   */
  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    } else {
      console.warn('[WebSocketManager] Cannot send - not connected')
    }
  }

  /**
   * Subscribe to a specific metric channel
   *
   * @param {string} channel - Channel name to subscribe
   */
  subscribe(channel) {
    this.send({
      type: 'subscribe',
      channel,
    })
  }

  /**
   * Unsubscribe from a metric channel
   *
   * @param {string} channel - Channel name to unsubscribe
   */
  unsubscribe(channel) {
    this.send({
      type: 'unsubscribe',
      channel,
    })
  }

  /**
   * Start heartbeat timer
   */
  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping', timestamp: Date.now() })
    }, this.heartbeatInterval)
  }

  /**
   * Schedule reconnection attempt
   */
  scheduleReconnect() {
    this.reconnectAttempts++
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      30000 // Max delay of 30 seconds
    )

    console.log(
      `[WebSocketManager] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    )

    setTimeout(() => {
      this.connect().catch(() => {
        // Reconnection failed, will retry if attempts remaining
      })
    }, delay)
  }

  /**
   * Add event listener
   *
   * @param {string} event - Event name
   * @param {Function} callback - Event handler
   */
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event).add(callback)
  }

  /**
   * Remove event listener
   *
   * @param {string} event - Event name
   * @param {Function} callback - Event handler to remove
   */
  off(event, callback) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).delete(callback)
    }
  }

  /**
   * Emit event to all listeners
   *
   * @param {string} event - Event name
   * @param {*} data - Event data
   */
  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach((callback) => {
        try {
          callback(data)
        } catch (error) {
          console.error(`[WebSocketManager] Event handler error for ${event}:`, error)
        }
      })
    }
  }
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
export function calculateEquityCurve(trades, initialBalance = 10000) {
  if (!trades || trades.length === 0) {
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
 * @returns {Object} Performance metrics
 */
export function calculatePerformanceMetrics(trades) {
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

  // Max Drawdown
  let cumulativePnL = 0
  let peak = 0
  let maxDrawdown = 0

  pnls.forEach((pnl) => {
    cumulativePnL += pnl
    if (cumulativePnL > peak) peak = cumulativePnL
    const drawdown = peak - cumulativePnL
    if (drawdown > maxDrawdown) maxDrawdown = drawdown
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
    maxDrawdownPercent: peak > 0 ? (maxDrawdown / peak) * 100 : 0,

    // VaR metrics
    var95,
    cvar95,

    // Other metrics
    expectancy,
    recoveryFactor,
  }
}

export default analyticsAPI
