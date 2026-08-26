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
 * FIXED 2026-08-20: Fetch in parallel with Promise.allSettled — the previous
 * sequential for-loop over 11 symbols outlived its own 5s refetch interval,
 * so every cycle aborted in-flight requests (nginx 499 storm). Per-symbol
 * error isolation is preserved: a failed symbol is logged and dropped.
 */
export function useMultipleTickers(symbols = []) {
  return useQuery({
    queryKey: ['tickers', symbols],
    queryFn: async () => {
      // Fetch all tickers in parallel; allSettled keeps per-symbol isolation
      const results = await Promise.allSettled(
        symbols.map(symbol => marketAPI.getTicker(symbol))
      )
      // Convert array to object with symbol as key, skipping failures
      // API returns { success: true, data: {...}, source: "..." } format
      return results.reduce((acc, result, index) => {
        if (result.status === 'fulfilled' && result.value != null) {
          acc[symbols[index]] = result.value
        } else if (result.status === 'rejected') {
          console.warn(`[useMultipleTickers] Failed to fetch ${symbols[index]}:`, result.reason?.message)
        }
        return acc
      }, {})
    },
    refetchInterval: 10000, // Refetch every 10 seconds (was 5s — see 2026-08-20 fix above)
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
