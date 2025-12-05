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

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
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

  // Execute buy order
  buy: (symbol, quantity) => api.post('/portfolio/buy', { symbol, quantity }),

  // Execute sell order
  sell: (symbol, quantity) => api.post('/portfolio/sell', { symbol, quantity }),

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

  // Get orderbook
  // BACKEND STATUS: NOT IMPLEMENTED - Returns 404
  // NOTE 2025-12-04: market-data-service does not have orderbook endpoint
  // TODO: Implement /api/v1/orderbook/{symbol} in market-data-service if needed
  getOrderbook: (symbol) => api.get(`/market/orderbook/${symbol}`),
}

// Trading signals endpoints
export const tradingAPI = {
  // Get trading signal for a symbol
  getSignal: (symbol, interval = 60) =>
    api.get(`/trading/signals/${symbol}`, { params: { interval } }),

  // Get multiple signals
  getMultipleSignals: (symbols, interval = 60) =>
    Promise.all(symbols.map(symbol => tradingAPI.getSignal(symbol, interval))),

  // Get trading bot status (maps to /api/v1/trading/status)
  getStatus: () => api.get('/trading/status'),

  // Get trading positions
  getPositions: (status = 'open') =>
    api.get('/trading/positions', { params: { status } }),

  // Get trading performance metrics
  getPerformance: () => api.get('/trading/performance'),
}

// System health endpoint
export const systemAPI = {
  // Check system health
  getHealth: () => api.get('/health'),
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

  // Get ML-based trading signal
  // BACKEND STATUS: NOT IMPLEMENTED - Returns 404
  // NOTE 2025-12-04: ml-prediction-service does not have signal endpoint
  // Available endpoints: /predict/price, /predict/trend, /predict/volatility
  // TODO: Implement /api/v1/predict/signal/{symbol} in ml-prediction-service if needed
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

  // Retrain existing model
  retrainModel: (symbol, interval = 60, lookbackDays = 90) =>
    api.post(`/ml/models/retrain/${symbol}`, null, {
      params: { interval, lookback_days: lookbackDays }
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
// NOTE 2025-12-04: These endpoints are NOT YET IMPLEMENTED in the backend trading-engine.
// The frontend will display error messages until these are implemented.
// Current backend endpoints available at /api/v1/signals/{symbol} provide Phase 1 signals only.
export const enhancedTradingAPI = {
  // Get Phase 3 enhanced signal (includes ML + Sentiment + MTF)
  // BACKEND STATUS: NOT IMPLEMENTED - Returns 404
  // TODO: Implement /api/v1/signals/enhanced/{symbol} in trading-engine
  getEnhancedSignal: (symbol, interval = 60) =>
    api.get(`/trading/signals/enhanced/${symbol}`, { params: { interval } }),

  // Get Phase 1 vs Phase 3 comparison
  // BACKEND STATUS: NOT IMPLEMENTED - Returns 404
  // TODO: Implement /api/v1/signals/compare/{symbol} in trading-engine
  getSignalComparison: (symbol, interval = 60) =>
    api.get(`/trading/signals/compare/${symbol}`, { params: { interval } }),
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

export default api
