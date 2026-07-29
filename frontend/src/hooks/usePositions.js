import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

// Create axios instance with base configuration
// UPDATED 2025-11-30: Increased timeout from 10s to 15s for positions endpoint
// which needs to fetch live prices from market-data-service
const api = axios.create({
  baseURL: '/api',
  timeout: 15000, // Increased from 10s to allow for market data price fetching
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

// Response interceptor to extract data
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const url = error.config?.url || 'unknown'
    const status = error.response?.status ?? 'network'
    if (shouldLogError(url, status)) {
      console.error('[usePositions API] Error:', error.response?.data || error.message)
    }
    return Promise.reject(error)
  }
)

/**
 * Custom hook for fetching trading positions from trading-engine
 * Auto-refetches every 10 seconds for real-time updates
 *
 * UPDATED 2025-11-27: Added console.log debugging for data flow troubleshooting
 * UPDATED 2025-11-30: Increased interval from 5s to 10s to prevent request overload
 */
export function usePositions() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: () => api.get('/trading/positions'),
    refetchInterval: 10000, // Refetch every 10 seconds (was 5s, increased to reduce load)
    staleTime: 8000, // Consider data fresh for 8 seconds
    retry: 2,
    retryDelay: 1000,
  })
}

/**
 * Custom hook for fetching trading bot status
 * Auto-refetches every 15 seconds
 *
 * UPDATED 2025-11-27: Added console.log debugging for data flow troubleshooting
 * UPDATED 2025-11-29: Fixed endpoint path to match backend /api/v1/trading/status
 * UPDATED 2025-11-30: Increased interval from 5s to 15s to prevent request overload
 */
export function useTradingStatus() {
  return useQuery({
    queryKey: ['trading', 'status'],
    queryFn: () => api.get('/trading/status'),
    refetchInterval: 15000, // Refetch every 15 seconds (was 5s, increased to reduce load)
    staleTime: 12000, // Consider data fresh for 12 seconds
    retry: 2,
    retryDelay: 1000,
  })
}

/**
 * Custom hook for fetching performance metrics from trading-engine
 * Auto-refetches every 10 seconds for real-time updates
 *
 * UPDATED 2025-11-28: Now fetches from trading-engine for correct balance tracking
 * UPDATED 2025-11-30: Increased interval from 5s to 10s to prevent request overload
 */
export function usePerformance() {
  return useQuery({
    queryKey: ['performance'],
    queryFn: () => api.get('/trading/performance'),
    refetchInterval: 10000, // Refetch every 10 seconds (was 5s, increased to reduce load)
    staleTime: 8000, // Consider data fresh for 8 seconds
    retry: 2,
    retryDelay: 1000,
  })
}
