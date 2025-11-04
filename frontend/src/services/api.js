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

export default api
