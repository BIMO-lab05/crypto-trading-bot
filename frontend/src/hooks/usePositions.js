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

// Response interceptor to extract data
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('[usePositions API] Error:', error.response?.data || error.message)
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
    queryFn: async () => {
      console.log('[usePositions] Fetching trading positions...')
      const response = await api.get('/trading/positions')
      console.log('[usePositions] Received data:', response)
      return response
    },
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
    queryFn: async () => {
      console.log('[useTradingStatus] Fetching trading status...')
      const response = await api.get('/trading/trading/status')
      console.log('[useTradingStatus] Received data:', response)
      return response
    },
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
    queryFn: async () => {
      console.log('[usePerformance] Fetching performance metrics...')
      const response = await api.get('/trading/performance')
      console.log('[usePerformance] Received data:', response)
      return response
    },
    refetchInterval: 10000, // Refetch every 10 seconds (was 5s, increased to reduce load)
    staleTime: 8000, // Consider data fresh for 8 seconds
    retry: 2,
    retryDelay: 1000,
  })
}
