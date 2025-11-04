import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portfolioAPI } from '../services/api'

/**
 * Custom hook for fetching and managing portfolio data
 * Auto-refetches every 5 seconds for real-time updates
 */
export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: portfolioAPI.getPortfolio,
    refetchInterval: 5000, // Refetch every 5 seconds
  })
}

/**
 * Custom hook for portfolio performance metrics
 */
export function usePortfolioPerformance() {
  return useQuery({
    queryKey: ['portfolio', 'performance'],
    queryFn: portfolioAPI.getPerformance,
    refetchInterval: 10000, // Refetch every 10 seconds
  })
}

/**
 * Custom hook for trade history
 */
export function useTradeHistory(params = {}) {
  return useQuery({
    queryKey: ['trades', params],
    queryFn: () => portfolioAPI.getTradeHistory(params),
    refetchInterval: 10000,
  })
}

/**
 * Custom hook for executing buy orders
 */
export function useBuyOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ symbol, quantity }) => portfolioAPI.buy(symbol, quantity),
    onSuccess: () => {
      // Invalidate portfolio data to trigger refetch
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['trades'] })
    },
  })
}

/**
 * Custom hook for executing sell orders
 */
export function useSellOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ symbol, quantity }) => portfolioAPI.sell(symbol, quantity),
    onSuccess: () => {
      // Invalidate portfolio data to trigger refetch
      queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      queryClient.invalidateQueries({ queryKey: ['trades'] })
    },
  })
}

/**
 * Custom hook for emergency stop functionality
 */
export function useEmergencyStop() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: portfolioAPI.emergencyStop,
    onSuccess: () => {
      // Invalidate all data
      queryClient.invalidateQueries()
    },
  })
}
