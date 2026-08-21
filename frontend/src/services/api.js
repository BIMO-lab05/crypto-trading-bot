import axios from 'axios'

/**
 * API Service Configuration
 *
 * UPDATED 2025-11-30: Increased timeout from 10s to 20s to prevent request failures
 * All requests are proxied through Vite to http://localhost:8000 (api-gateway)
 */
const api = axios.create({
  baseURL: '/api',
  timeout: 20000, // Increased from 10s to 20s to prevent timeout errors
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for adding auth tokens (future enhancement)
api.interceptors.request.use(
  (config) => {
    // Future: Add JWT token here
    // const token = localStorage.getItem('token')
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`
    // }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Throttle error logging: log at most once per distinct URL+status per minute
// so a broken polled endpoint doesn't flood the console.
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

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const url = error.config?.url || 'unknown'
    const status = error.response?.status ?? 'network'
    if (shouldLogError(url, status)) {
      console.error('API Error:', error.response?.data || error.message)
    }
    return Promise.reject(error)
  }
)

// Portfolio endpoints
export const portfolioAPI = {
  // Get current portfolio status
  getPortfolio: () => api.get('/portfolio'),

  // Get portfolio performance metrics (use trading engine for accurate P&L)
  getPerformance: () => api.get('/trading/performance'),

  // Get trade history from trading engine (closed positions with P&L)
  // UPDATED 2025-11-30: Changed from /portfolio/trades to /trading/trades/history
  // to get closed positions from database instead of empty transactions
  getTradeHistory: (params) => api.get('/trading/trades/history', { params }),

  // Execute buy order.
  // Gateway expects QUERY params (symbol, quantity, price) — not a JSON body.
  // All three are required by the gateway (validated, no defaults).
  buy: (symbol, quantity, price) =>
    api.post('/portfolio/buy', null, { params: { symbol, quantity, price } }),

  // Execute sell order (query params, same contract as buy)
  sell: (symbol, quantity, price) =>
    api.post('/portfolio/sell', null, { params: { symbol, quantity, price } }),

  // Emergency stop all trading
  emergencyStop: () => api.post('/portfolio/emergency-stop'),
}

// Market data endpoints
export const marketAPI = {
  // Get ticker data for a symbol
  getTicker: (symbol) => api.get(`/market/ticker/${symbol}`),

  // Get kline/candlestick data (note: backend uses 'klines' plural)
  getKlines: (symbol, interval, params) =>
    api.get(`/market/klines/${symbol}`, { params: { interval, ...params } }),
}

// Trading signals endpoints
export const tradingAPI = {
  // Get trading signal for a symbol
  getSignal: (symbol, interval = 60) =>
    api.get(`/trading/signals/${symbol}`, { params: { interval } }),

  // Get trading bot status (gateway route /api/trading/status — no v1 prefix)
  getStatus: () => api.get('/trading/status'),

  // Get trading positions
  getPositions: (status = 'open') =>
    api.get('/trading/positions', { params: { status } }),

  // Get trading performance metrics
  getPerformance: () => api.get('/trading/performance'),

  // Stage-by-stage signal rejection funnel (2026-08-21).
  // Gateway route /api/trading/signal-funnel -> engine /api/v1/trading/signal-funnel.
  getSignalFunnel: () => api.get('/trading/signal-funnel'),
}

// System health endpoint
export const systemAPI = {
  // Check system health.
  // The gateway serves /health at the root (NOT /api/health), so this must
  // bypass the shared instance's baseURL '/api'. Uses a bare axios call with
  // baseURL '' and unwraps .data to match the shared interceptor's behavior.
  getHealth: () =>
    axios.get('/health', { baseURL: '', timeout: 20000 }).then((res) => res.data),
}

// Phase 3: ML Prediction endpoints
export const mlAPI = {
  // Get price predictions for a symbol
  getPricePrediction: (symbol, interval = 60) =>
    api.get(`/ml/predict/price/${symbol}`, { params: { interval } }),

  // Get trend classification (BULLISH/BEARISH/NEUTRAL)
  getTrendPrediction: (symbol, interval = 60) =>
    api.get(`/ml/predict/trend/${symbol}`, { params: { interval } }),

  // Get volatility forecast
  getVolatilityPrediction: (symbol, interval = 60) =>
    api.get(`/ml/predict/volatility/${symbol}`, { params: { interval } }),

  // Get ML-based trading signal (gateway route /api/ml/predict/signal/{symbol})
  getMLSignal: (symbol, interval = 60) =>
    api.get(`/ml/predict/signal/${symbol}`, { params: { interval } }),

  // List all trained models
  getModels: () => api.get('/ml/models'),

  // Get specific model info
  getModelInfo: (symbol, interval = 60) =>
    api.get(`/ml/models/${symbol}`, { params: { interval } }),

  // Train a new model (API expects query parameters)
  trainModel: (symbol, interval = 60, lookbackDays = 90) =>
    api.post('/ml/models/train', null, {
      params: { symbol, interval, lookback_days: lookbackDays }
    }),
}

// Phase 3: Sentiment Analysis endpoints
export const sentimentAPI = {
  // Get news sentiment for a symbol
  getNewsSentiment: (symbol, hours = 24) =>
    api.get(`/sentiment/news/${symbol}`, { params: { hours } }),

  // Get social media sentiment
  getSocialSentiment: (symbol, hours = 24) =>
    api.get(`/sentiment/social/${symbol}`, { params: { hours } }),

  // Get combined sentiment (news + social)
  getCombinedSentiment: (symbol, hours = 24) =>
    api.get(`/sentiment/combined/${symbol}`, { params: { hours } }),

  // Get sentiment trend over time
  getSentimentTrend: (symbol, periods = 24) =>
    api.get(`/sentiment/trend/${symbol}`, { params: { periods } }),
}

// Phase 3: Multi-Timeframe Analysis endpoints
export const multiTimeframeAPI = {
  // Get multi-timeframe analysis
  // FIXED 2025-12-04: Backend expects numeric intervals (5,15,60,240), not strings (5m,15m,60m,240m)
  getAnalysis: (symbol, timeframes = '5,15,60,240') =>
    api.get(`/analysis/multi-timeframe/${symbol}`, { params: { timeframes } }),

  // Get timeframe-specific signal
  getTimeframeSignal: (symbol, interval) =>
    api.get(`/analysis/indicators/signal/${symbol}`, { params: { interval } }),
}

// Phase 3: Enhanced Trading Signals endpoints
export const enhancedTradingAPI = {
  // Get Phase 3 enhanced signal (includes ML + Sentiment + MTF)
  // Gateway route /api/trading/signals/{symbol} (no v1 prefix) already
  // includes all enhanced data.
  getEnhancedSignal: (symbol, interval = 60) =>
    api.get(`/trading/signals/${symbol}`, { params: { interval } }),
}

// Auto Trader & Trading Enhancements endpoints (FIXED - 2025-12-01)
// Updated to use correct backend endpoints
export const autoTraderAPI = {
  // Get trading status (includes auto trader info)
  getStatus: () => api.get('/trading/status'),

  // Start auto trading
  start: () => api.post('/trading/start'),

  // Stop auto trading
  stop: () => api.post('/trading/stop'),

  // Get performance metrics
  getPerformanceReport: () => api.get('/trading/performance'),

  // Force signal check - not available, use status instead
  forceSignalCheck: () => api.get('/trading/status'),
}

// Tournament endpoints (Phase 7, DASH-04). Gateway reads committed snapshot files from a RO bind-mount per CONTEXT.md D-01.
// Path shape is `/tournament/snapshots` (NO `/v1/` prefix per ADR-007). The shared `api` axios instance has
// baseURL '/api' and a response interceptor (line 34) that strips `.data`, so callers see the body directly.
export const tournamentAPI = {
  // List all committed snapshots (gateway reads ./services/tournament-harness/data/snapshots/*.json)
  listSnapshots: () => api.get('/tournament/snapshots'),
  // Merged snapshot + ensemble + significance for one tournament
  getSnapshot: (tournamentId) => api.get(`/tournament/snapshots/${tournamentId}`),
}

export default api
