import { useQuery } from '@tanstack/react-query'
import { tradingAPI } from '../services/api'

/**
 * Custom hook for fetching trading signal for a single symbol
 * Auto-refetches every 30 seconds for updated signals
 *
 * FIXED 2026-08-20: 5s → 30s. The signals endpoint takes ~8s per symbol, so
 * any interval below that aborts in-flight requests (nginx 499 storm).
 */
export function useSignal(symbol, interval = 60) {
  return useQuery({
    queryKey: ['signal', symbol, interval],
    queryFn: () => tradingAPI.getSignal(symbol, interval),
    refetchInterval: 30000, // Refetch every 30 seconds (endpoint latency ~8s)
    enabled: !!symbol, // Only run if symbol is provided
  })
}

/**
 * Custom hook for fetching trading signals for multiple symbols
 * Returns an object with symbol as key and signal data as value
 *
 * FIXED 2026-08-20: 5s → 30s. At ~8s endpoint latency per symbol a 5s
 * interval aborted every batch before it completed (nginx 499 storm).
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
    refetchInterval: 30000, // Refetch every 30 seconds (endpoint latency ~8s/symbol)
    enabled: symbols.length > 0,
  })
}
