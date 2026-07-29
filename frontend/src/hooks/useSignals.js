import { useQuery } from '@tanstack/react-query'
import { tradingAPI } from '../services/api'

/**
 * Custom hook for fetching trading signal for a single symbol
 * Auto-refetches every 10 seconds for updated signals
 */
export function useSignal(symbol, interval = 60) {
  return useQuery({
    queryKey: ['signal', symbol, interval],
    queryFn: () => tradingAPI.getSignal(symbol, interval),
    refetchInterval: 5000, // Refetch every 5 seconds
    enabled: !!symbol, // Only run if symbol is provided
  })
}

/**
 * Custom hook for fetching trading signals for multiple symbols
 * Returns an object with symbol as key and signal data as value
 */
export function useMultipleSignals(symbols = [], interval = 60) {
  return useQuery({
    queryKey: ['signals', symbols, interval],
    queryFn: async () => {
      // Use allSettled so a single failing symbol doesn't reject the whole
      // batch and blank the signals tile. Rejected entries are dropped.
      const results = await Promise.allSettled(
        symbols.map(symbol => tradingAPI.getSignal(symbol, interval))
      )
      // Convert array to object with symbol as key, skipping failures
      return results.reduce((acc, result, index) => {
        if (result.status === 'fulfilled' && result.value != null) {
          acc[symbols[index]] = result.value
        }
        return acc
      }, {})
    },
    refetchInterval: 5000, // Refetch every 5 seconds
    enabled: symbols.length > 0,
  })
}
