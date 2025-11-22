import axios from 'axios'

// Create axios instance with base configuration
// All requests will be proxied through Vite to http://localhost:8000
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
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

  // Get portfolio performance metrics
  getPerformance: () => api.get('/portfolio/performance'),

  // Get trade history
  getTradeHistory: (params) => api.get('/portfolio/trades', { params }),

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

  // Get kline/candlestick data
  getKlines: (symbol, interval, params) =>
    api.get(`/market/kline/${symbol}`, { params: { interval, ...params } }),

  // Get orderbook
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
  getMLSignal: (symbol, interval = 60) =>
    api.get(`/ml/predict/signal/${symbol}`, { params: { interval } }),

  // List all trained models
  getModels: () => api.get('/ml/models'),

  // Get specific model info
  getModelInfo: (symbol, interval = 60) =>
    api.get(`/ml/models/${symbol}`, { params: { interval } }),

  // Train a new model
  trainModel: (symbol, interval = 60, lookbackDays = 90) =>
    api.post('/ml/models/train', { symbol, interval, lookback_days: lookbackDays }),

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
  getAnalysis: (symbol, timeframes = '5m,15m,60m,240m') =>
    api.get(`/analysis/multi-timeframe/${symbol}`, { params: { timeframes } }),

  // Get timeframe-specific signal
  getTimeframeSignal: (symbol, interval) =>
    api.get(`/analysis/indicators/signal/${symbol}`, { params: { interval } }),
}

// Phase 3: Enhanced Trading Signals endpoints
export const enhancedTradingAPI = {
  // Get Phase 3 enhanced signal (includes ML + Sentiment + MTF)
  getEnhancedSignal: (symbol, interval = 60) =>
    api.get(`/trading/signals/enhanced/${symbol}`, { params: { interval } }),

  // Get Phase 1 vs Phase 3 comparison
  getSignalComparison: (symbol, interval = 60) =>
    api.get(`/trading/signals/compare/${symbol}`, { params: { interval } }),
}

export default api
