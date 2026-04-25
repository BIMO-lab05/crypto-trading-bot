import { useQuery } from '@tanstack/react-query'
import { marketAPI } from '../services/api'

/**
 * Custom hook for fetching real-time ticker data for a single symbol
 * Auto-refetches every 5 seconds for real-time price updates
 *
 * FIXED 2026-02-17: Reduced refresh interval for real-time prices
 */
export function useTicker(symbol) {
  return useQuery({
    queryKey: ['ticker', symbol],
    queryFn: async () => {
      const response = await marketAPI.getTicker(symbol)
      // API returns { success: true, data: {...}, source: "..." } format
      // Return the response as-is (axios interceptor already extracts .data)
      return response
    },
    refetchInterval: 5000, // Refetch every 5 seconds (REDUCED from 15s for real-time)
    staleTime: 3000, // Consider data fresh for 3 seconds
    retry: 2,
    retryDelay: 1000,
    enabled: !!symbol, // Only run if symbol is provided
  })
}

/**
 * Custom hook for fetching ticker data for multiple symbols
 *
 * FIXED 2026-02-17: Reduced refresh interval for real-time prices
 */
export function useMultipleTickers(symbols = []) {
  return useQuery({
    queryKey: ['tickers', symbols],
    queryFn: async () => {
      // Fetch tickers sequentially to avoid overwhelming the API
      const results = []
      for (const symbol of symbols) {
        try {
          const response = await marketAPI.getTicker(symbol)
          results.push(response)
        } catch (err) {
          console.warn(`[useMultipleTickers] Failed to fetch ${symbol}:`, err.message)
          results.push(null)
        }
      }
      // Convert array to object with symbol as key
      // API returns { success: true, data: {...}, source: "..." } format
      // Extract the data field from each response
      return results.reduce((acc, response, index) => {
        if (response) {
          acc[symbols[index]] = response
        }
        return acc
      }, {})
    },
    refetchInterval: 5000, // Refetch every 5 seconds (REDUCED from 20s for real-time)
    staleTime: 3000, // Consider data fresh for 3 seconds
    retry: 1, // Fewer retries for batch operations
    retryDelay: 2000,
    enabled: symbols.length > 0,
  })
}

/**
 * Custom hook for kline/candlestick data
 *
 * UPDATED 2025-11-30: Added staleTime and retry settings for consistency
 */
export function useKlines(symbol, interval = '60', params = {}) {
  return useQuery({
    queryKey: ['klines', symbol, interval, params],
    queryFn: async () => {
      const response = await marketAPI.getKlines(symbol, interval, params)
      // Extract data array from API response { success: true, data: [...] }
      const data = response?.data || response || []
      // API returns newest first, but charts need oldest first (chronological order)
      // Sort by timestamp ascending for proper chart display
      if (Array.isArray(data) && data.length > 0) {
        return [...data].sort((a, b) => {
          const timestampA = a.timestamp || a.open_time || 0
          const timestampB = b.timestamp || b.open_time || 0
          return timestampA - timestampB
        })
      }
      return data
    },
    refetchInterval: 60000, // Refetch every minute
    staleTime: 55000, // Consider data fresh for 55 seconds
    retry: 2,
    retryDelay: 1000,
    enabled: !!symbol,
  })
}

/**
 * Custom hook for orderbook data
 *
 * UPDATED 2025-11-30: Increased interval from 5s to 20s to prevent request overload
 */
export function useOrderbook(symbol) {
  return useQuery({
    queryKey: ['orderbook', symbol],
    queryFn: () => marketAPI.getOrderbook(symbol),
    refetchInterval: 20000, // Refetch every 20 seconds (was 5s, increased to reduce load)
    staleTime: 15000, // Consider data fresh for 15 seconds
    retry: 2,
    retryDelay: 1000,
    enabled: !!symbol,
  })
}
