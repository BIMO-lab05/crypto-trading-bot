import { useQuery } from '@tanstack/react-query'
import { mlAPI, sentimentAPI, multiTimeframeAPI, enhancedTradingAPI } from '../services/api'

/**
 * Phase 3 AI-Enhanced Trading Hooks
 * Custom hooks for fetching ML predictions, sentiment analysis,
 * multi-timeframe analysis, and enhanced trading signals.
 *
 * All hooks include:
 * - Error handling with retry logic
 * - Stale time configuration
 * - Automatic refetch intervals
 * - Data normalization
 */

// Default query configuration for Phase 3 services
const defaultQueryConfig = {
  retry: 2,
  retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
}

/**
 * Custom hook for fetching ML price predictions
 * Endpoint: /api/ml/predict/price/{symbol}
 *
 * @param {string} symbol - Trading symbol (e.g., 'BTCUSDT')
 * @param {number} interval - Time interval in minutes (default: 60)
 * @returns {object} Query result with data, loading, and error states
 */
export function useMLPrediction(symbol, interval = 60) {
  return useQuery({
    queryKey: ['ml', 'prediction', symbol, interval],
    queryFn: async () => {
      const response = await mlAPI.getPricePrediction(symbol, interval)
      // Normalize response - API may return { data: ... } or direct data
      return response?.data || response
    },
    refetchInterval: 60000, // Refetch every minute
    staleTime: 30000, // Consider data fresh for 30 seconds
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching ML trend classification
 * Endpoint: /api/ml/predict/trend/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} interval - Time interval in minutes
 * @returns {object} Query result with trend classification
 */
export function useMLTrend(symbol, interval = 60) {
  return useQuery({
    queryKey: ['ml', 'trend', symbol, interval],
    queryFn: async () => {
      const response = await mlAPI.getTrendPrediction(symbol, interval)
      return response?.data || response
    },
    refetchInterval: 60000,
    staleTime: 30000,
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching sentiment analysis
 * Endpoint: /api/sentiment/combined/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} hours - Lookback period in hours (default: 24)
 * @returns {object} Query result with combined sentiment data
 */
export function useSentiment(symbol, hours = 24) {
  return useQuery({
    queryKey: ['sentiment', 'combined', symbol, hours],
    queryFn: async () => {
      const response = await sentimentAPI.getCombinedSentiment(symbol, hours)
      return response?.data || response
    },
    refetchInterval: 900000, // Refetch every 15 minutes
    staleTime: 300000, // Consider fresh for 5 minutes
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching news sentiment only
 * Endpoint: /api/sentiment/news/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} hours - Lookback period in hours
 * @returns {object} Query result with news sentiment
 */
export function useNewsSentiment(symbol, hours = 24) {
  return useQuery({
    queryKey: ['sentiment', 'news', symbol, hours],
    queryFn: async () => {
      const response = await sentimentAPI.getNewsSentiment(symbol, hours)
      return response?.data || response
    },
    refetchInterval: 900000,
    staleTime: 300000,
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching social media sentiment
 * Endpoint: /api/sentiment/social/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} hours - Lookback period in hours
 * @returns {object} Query result with social sentiment
 */
export function useSocialSentiment(symbol, hours = 24) {
  return useQuery({
    queryKey: ['sentiment', 'social', symbol, hours],
    queryFn: async () => {
      const response = await sentimentAPI.getSocialSentiment(symbol, hours)
      return response?.data || response
    },
    refetchInterval: 900000,
    staleTime: 300000,
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching multi-timeframe analysis
 * Endpoint: /api/analysis/multi-timeframe/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {string} timeframes - Comma-separated timeframes (default: '5m,15m,60m,240m')
 * @returns {object} Query result with multi-timeframe signals
 */
export function useMultiTimeframe(symbol, timeframes = '5m,15m,60m,240m') {
  return useQuery({
    queryKey: ['mtf', 'analysis', symbol, timeframes],
    queryFn: async () => {
      const response = await multiTimeframeAPI.getAnalysis(symbol, timeframes)
      return response?.data || response
    },
    refetchInterval: 60000, // Refetch every minute
    staleTime: 30000,
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching timeframe-specific signal
 * Endpoint: /api/analysis/indicators/signal/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} interval - Time interval in minutes
 * @returns {object} Query result with timeframe signal
 */
export function useTimeframeSignal(symbol, interval) {
  return useQuery({
    queryKey: ['analysis', 'signal', symbol, interval],
    queryFn: async () => {
      const response = await multiTimeframeAPI.getTimeframeSignal(symbol, interval)
      return response?.data || response
    },
    refetchInterval: 60000,
    staleTime: 30000,
    enabled: !!symbol && !!interval,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching Phase 3 enhanced trading signal
 * Combines ML, sentiment, and multi-timeframe signals
 * Endpoint: /api/trading/signals/enhanced/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} interval - Time interval in minutes
 * @returns {object} Query result with enhanced signal
 */
export function useEnhancedSignal(symbol, interval = 60) {
  return useQuery({
    queryKey: ['enhanced', 'signal', symbol, interval],
    queryFn: async () => {
      const response = await enhancedTradingAPI.getEnhancedSignal(symbol, interval)
      return response?.data || response
    },
    refetchInterval: 30000, // Refetch every 30 seconds
    staleTime: 15000,
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching signal comparison (Phase 1 vs Phase 3)
 * Endpoint: /api/trading/signals/compare/{symbol}
 *
 * @param {string} symbol - Trading symbol
 * @param {number} interval - Time interval in minutes
 * @returns {object} Query result with signal comparison
 */
export function useSignalComparison(symbol, interval = 60) {
  return useQuery({
    queryKey: ['signal', 'comparison', symbol, interval],
    queryFn: async () => {
      const response = await enhancedTradingAPI.getSignalComparison(symbol, interval)
      return response?.data || response
    },
    refetchInterval: 30000,
    staleTime: 15000,
    enabled: !!symbol,
    ...defaultQueryConfig,
  })
}

/**
 * Custom hook for fetching all Phase 3 data at once
 * Combines ML prediction, sentiment, MTF, and enhanced signal
 *
 * @param {string} symbol - Trading symbol
 * @param {number} interval - Time interval in minutes
 * @returns {object} Combined query results for all Phase 3 data
 */
export function usePhase3Data(symbol, interval = 60) {
  const mlQuery = useMLPrediction(symbol, interval)
  const sentimentQuery = useSentiment(symbol)
  const mtfQuery = useMultiTimeframe(symbol)
  const enhancedQuery = useEnhancedSignal(symbol, interval)

  return {
    ml: {
      data: mlQuery.data,
      isLoading: mlQuery.isLoading,
      isError: mlQuery.isError,
      error: mlQuery.error,
    },
    sentiment: {
      data: sentimentQuery.data,
      isLoading: sentimentQuery.isLoading,
      isError: sentimentQuery.isError,
      error: sentimentQuery.error,
    },
    mtf: {
      data: mtfQuery.data,
      isLoading: mtfQuery.isLoading,
      isError: mtfQuery.isError,
      error: mtfQuery.error,
    },
    enhanced: {
      data: enhancedQuery.data,
      isLoading: enhancedQuery.isLoading,
      isError: enhancedQuery.isError,
      error: enhancedQuery.error,
    },
    // Overall loading/error state
    isLoading: mlQuery.isLoading || sentimentQuery.isLoading ||
               mtfQuery.isLoading || enhancedQuery.isLoading,
    hasErrors: mlQuery.isError || sentimentQuery.isError ||
               mtfQuery.isError || enhancedQuery.isError,
  }
}

/**
 * Custom hook for ML model management
 * Provides model info, training status, and training controls
 *
 * @param {string} symbol - Trading symbol
 * @param {number} interval - Time interval
 * @returns {object} Model info and training functions
 */
export function useMLModel(symbol, interval = 60) {
  const modelQuery = useQuery({
    queryKey: ['ml', 'model', symbol, interval],
    queryFn: async () => {
      const response = await mlAPI.getModelInfo(symbol, interval)
      return response?.data || response
    },
    staleTime: 60000, // Model info is fairly static
    enabled: !!symbol,
    ...defaultQueryConfig,
  })

  return {
    model: modelQuery.data,
    isLoading: modelQuery.isLoading,
    isError: modelQuery.isError,
    error: modelQuery.error,
    refetch: modelQuery.refetch,
  }
}
