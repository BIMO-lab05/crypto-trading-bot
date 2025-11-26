import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

// Create axios instance with base configuration
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor to extract data
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

/**
 * Custom hook for fetching trading positions from trading-engine
 * Auto-refetches every 5 seconds for real-time updates
 */
export function usePositions() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: async () => {
      const response = await api.get('/trading/positions')
      return response
    },
    refetchInterval: 5000, // Refetch every 5 seconds
  })
}

/**
 * Custom hook for fetching trading bot status
 * Auto-refetches every 10 seconds
 */
export function useTradingStatus() {
  return useQuery({
    queryKey: ['trading', 'status'],
    queryFn: async () => {
      const response = await api.get('/trading/status')
      return response
    },
    refetchInterval: 10000, // Refetch every 10 seconds
  })
}

/**
 * Custom hook for fetching performance metrics from trading-engine
 * Auto-refetches every 30 seconds
 */
export function usePerformance() {
  return useQuery({
    queryKey: ['performance'],
    queryFn: async () => {
      const response = await api.get('/trading/performance')
      return response
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  })
}
