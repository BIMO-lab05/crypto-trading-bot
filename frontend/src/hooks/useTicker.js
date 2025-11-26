import { useQuery } from '@tanstack/react-query'
import { marketAPI } from '../services/api'

/**
 * Custom hook for fetching real-time ticker data for a single symbol
 * Auto-refetches every 3 seconds for real-time price updates
 */
export function useTicker(symbol) {
  return useQuery({
    queryKey: ['ticker', symbol],
    queryFn: () => marketAPI.getTicker(symbol),
    refetchInterval: 3000, // Refetch every 3 seconds for live prices
    enabled: !!symbol, // Only run if symbol is provided
  })
}

/**
 * Custom hook for fetching ticker data for multiple symbols
 */
export function useMultipleTickers(symbols = []) {
  return useQuery({
    queryKey: ['tickers', symbols],
    queryFn: async () => {
      const results = await Promise.all(
        symbols.map(symbol => marketAPI.getTicker(symbol))
      )
      // Convert array to object with symbol as key
      return results.reduce((acc, data, index) => {
        acc[symbols[index]] = data
        return acc
      }, {})
    },
    refetchInterval: 3000,
    enabled: symbols.length > 0,
  })
}

/**
 * Custom hook for kline/candlestick data
 */
export function useKlines(symbol, interval = '60', params = {}) {
  return useQuery({
    queryKey: ['klines', symbol, interval, params],
    queryFn: async () => {
      const response = await marketAPI.getKlines(symbol, interval, params)
      // Extract data array from API response { success: true, data: [...] }
      return response?.data || response || []
    },
    refetchInterval: 60000, // Refetch every minute
    enabled: !!symbol,
  })
}

/**
 * Custom hook for orderbook data
 */
export function useOrderbook(symbol) {
  return useQuery({
    queryKey: ['orderbook', symbol],
    queryFn: () => marketAPI.getOrderbook(symbol),
    refetchInterval: 5000, // Refetch every 5 seconds
    enabled: !!symbol,
  })
}
