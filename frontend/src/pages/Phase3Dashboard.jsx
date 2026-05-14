import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mlAPI, sentimentAPI, multiTimeframeAPI, enhancedTradingAPI } from '../services/api'
import TileState from '../components/TileState'

/**
 * Phase3Dashboard - AI-Enhanced Trading Dashboard
 * Displays ML predictions, sentiment analysis, and multi-timeframe confirmation
 *
 * UPDATED 2026-05-14 (Plan 06-05, DASH-05): wrapped in
 * <TileState forceStale/> per audit verdict LABELED_STALE. Phase 3
 * services (ml-prediction-service + sentiment-analysis-service) are
 * feature-flagged OFF by default (ENABLE_ML_PREDICTIONS=false,
 * ENABLE_SENTIMENT_ANALYSIS=false). The ML query drives the wrapper:
 * if /api/ml/* returns 503 the Failed (...) UI surfaces (F-05 precedence);
 * otherwise the page renders with a corner stale badge until Phase 7+
 * re-enables ML on a returns-target rebuild.
 *
 * UPDATED 2025-11-28: Added dark mode support throughout the component
 * - All backgrounds now support both light and dark themes
 * - Text colors adapt to current theme
 * - Status badges use theme-aware colors
 * - Smooth transitions for theme switching
 *
 * UPDATED 2025-11-27: Fixed field mappings to match actual API responses:
 * - ML API: predicted_direction (not trend), average_confidence (not confidence)
 * - MTF API: overall_signal (not consensus_signal), timeframe_details (not timeframe_signals)
 * - Sentiment API: nested news_sentiment/social_sentiment objects
 */

export default function Phase3Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = React.useState('BTCUSDT')
  const [selectedInterval, setSelectedInterval] = React.useState(60)
  const [trainingStatus, setTrainingStatus] = React.useState(null) // 'training', 'success', 'error'
  const [trainingMessage, setTrainingMessage] = React.useState('')

  // State for "Train All Intervals" feature
  const [trainAllProgress, setTrainAllProgress] = React.useState(null) // { current: 1, total: 4, currentInterval: '5m', completedIntervals: [] }
  const [isTrainingAll, setIsTrainingAll] = React.useState(false)

  // Query client for cache invalidation after training
  const queryClient = useQueryClient()

  // All intervals for training
  const allIntervals = [
    { value: 5, label: '5m' },
    { value: 15, label: '15m' },
    { value: 60, label: '1h' },
    { value: 240, label: '4h' },
  ]

  // ML Model Training mutation
  const trainModelMutation = useMutation({
    mutationFn: ({ symbol, interval, lookbackDays }) =>
      mlAPI.trainModel(symbol, interval, lookbackDays),
    onMutate: () => {
      if (!isTrainingAll) {
        setTrainingStatus('training')
        setTrainingMessage('Training model... This may take several minutes.')
      }
    },
    onSuccess: (data) => {
      if (!isTrainingAll) {
        setTrainingStatus('success')
        setTrainingMessage(data?.message || 'Model trained successfully!')
        // Invalidate ML prediction queries to fetch fresh predictions
        queryClient.invalidateQueries({ queryKey: ['ml', 'prediction'] })
        // Auto-clear success message after 10 seconds
        setTimeout(() => {
          setTrainingStatus(null)
          setTrainingMessage('')
        }, 10000)
      }
    },
    onError: (error) => {
      if (!isTrainingAll) {
        setTrainingStatus('error')
        setTrainingMessage(
          error?.response?.data?.detail ||
          error?.message ||
          'Failed to train model. Please try again.'
        )
      }
    },
  })

  // Handler for training button click
  const handleTrainModel = () => {
    trainModelMutation.mutate({
      symbol: selectedSymbol,
      interval: selectedInterval,
      lookbackDays: 90, // Default to 90 days of historical data
    })
  }

  // Handler for "Train All Intervals" button
  const handleTrainAllIntervals = async () => {
    setIsTrainingAll(true)
    setTrainingStatus('training')
    const completedIntervals = []

    for (let i = 0; i < allIntervals.length; i++) {
      const interval = allIntervals[i]
      setTrainAllProgress({
        current: i + 1,
        total: allIntervals.length,
        currentInterval: interval.label,
        completedIntervals: [...completedIntervals],
      })
      setTrainingMessage(`Training ${interval.label} model (${i + 1}/${allIntervals.length})...`)

      try {
        await mlAPI.trainModel(selectedSymbol, interval.value, 90)
        completedIntervals.push(interval.label)
      } catch (error) {
        // Use a constant format string to avoid CWE-134 (semgrep), with
        // the interval label and error passed as separate console args.
        console.error('Failed to train interval:', interval.label, error)
        // Continue with next interval even if one fails
        completedIntervals.push(`${interval.label} (failed)`)
      }
    }

    // All done
    setIsTrainingAll(false)
    setTrainAllProgress(null)
    setTrainingStatus('success')
    setTrainingMessage(`All models trained! Completed: ${completedIntervals.join(', ')}`)
    queryClient.invalidateQueries({ queryKey: ['ml', 'prediction'] })

    // Auto-clear after 15 seconds
    setTimeout(() => {
      setTrainingStatus(null)
      setTrainingMessage('')
    }, 15000)
  }

  // Trading symbols to monitor
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']
  const intervals = [
    { value: 5, label: '5m' },
    { value: 15, label: '15m' },
    { value: 60, label: '1h' },
    { value: 240, label: '4h' },
  ]

  // Fetch ML prediction with error handling and retry logic.
  // Plan 06-05 DASH-05: this query also drives the page-level
  // <TileState forceStale/> banner (LABELED_STALE verdict). When the ML
  // endpoint is 503 the wrapper's Failed (...) UI takes precedence over
  // the page body (F-05).
  const mlQuery = useQuery({
    queryKey: ['ml', 'prediction', selectedSymbol, selectedInterval],
    queryFn: () => mlAPI.getPricePrediction(selectedSymbol, selectedInterval),
    refetchInterval: 60000,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
    staleTime: 30000,
  })
  const {
    data: mlData,
    isLoading: mlLoading,
    isError: mlError,
    error: mlErrorDetails
  } = mlQuery

  // Fetch sentiment analysis with error handling
  const {
    data: sentimentData,
    isLoading: sentimentLoading,
    isError: sentimentError,
    error: sentimentErrorDetails
  } = useQuery({
    queryKey: ['sentiment', 'combined', selectedSymbol],
    queryFn: () => sentimentAPI.getCombinedSentiment(selectedSymbol, 24),
    refetchInterval: 900000,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
    staleTime: 300000,
  })

  // Fetch multi-timeframe analysis with error handling
  const {
    data: mtfData,
    isLoading: mtfLoading,
    isError: mtfError,
    error: mtfErrorDetails
  } = useQuery({
    queryKey: ['mtf', 'analysis', selectedSymbol],
    queryFn: () => multiTimeframeAPI.getAnalysis(selectedSymbol),
    refetchInterval: 60000,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
    staleTime: 30000,
  })

  // Fetch enhanced signal with error handling
  const {
    data: enhancedSignalData,
    isLoading: signalLoading,
    isError: signalError,
    error: signalErrorDetails
  } = useQuery({
    queryKey: ['enhanced', 'signal', selectedSymbol, selectedInterval],
    queryFn: () => enhancedTradingAPI.getEnhancedSignal(selectedSymbol, selectedInterval),
    refetchInterval: 30000,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
    staleTime: 15000,
  })

  // Extract data from API responses - handle nested .data wrapper and .signal wrapper
  const mlPrediction = mlData?.data || mlData
  const sentiment = sentimentData?.data || sentimentData
  const mtf = mtfData?.data || mtfData
  // Enhanced signal API returns {success, signal: {...}}, extract the signal object
  const rawEnhancedSignal = enhancedSignalData?.signal || enhancedSignalData?.data || enhancedSignalData

  // Normalize enhanced signal data to expected format
  // API returns: technical_analysis, ml_predictions, sentiment at top level
  // Frontend expects: action, metadata.ml_prediction, metadata.sentiment, etc.
  const enhancedSignal = rawEnhancedSignal ? {
    ...rawEnhancedSignal,
    // Map 'signal' to 'action' for consistency
    action: rawEnhancedSignal.action || rawEnhancedSignal.signal,
    // Build metadata from top-level fields
    metadata: {
      phase: '3',
      ml_prediction: rawEnhancedSignal.ml_predictions ? {
        trend: rawEnhancedSignal.ml_predictions.trend,
        confidence: rawEnhancedSignal.ml_predictions.trend_confidence || rawEnhancedSignal.ml_predictions.model_accuracy,
      } : null,
      sentiment: rawEnhancedSignal.sentiment?.news_sentiment ? {
        label: calculateSentimentLabel(rawEnhancedSignal.sentiment),
        score: calculateSentimentScore(rawEnhancedSignal.sentiment),
      } : null,
      multi_timeframe: rawEnhancedSignal.multi_timeframe || {
        alignment_score: rawEnhancedSignal.technical_analysis?.confidence || 0,
        overall_signal: rawEnhancedSignal.technical_analysis?.signal || 'HOLD',
      },
      base_signal: {
        buy_count: rawEnhancedSignal.signal_breakdown?.buy_signals || 0,
        sell_count: rawEnhancedSignal.signal_breakdown?.sell_signals || 0,
        aggregated_score: rawEnhancedSignal.technical_analysis?.confidence || rawEnhancedSignal.confidence || 0,
      },
    },
    // Also support components structure
    components: {
      ml: rawEnhancedSignal.ml_predictions,
      sentiment: rawEnhancedSignal.sentiment,
      technical: rawEnhancedSignal.technical_analysis,
      mtf: rawEnhancedSignal.multi_timeframe,
    },
  } : null

  // Helper functions for sentiment calculations
  function calculateSentimentLabel(sentimentData) {
    if (!sentimentData?.news_sentiment?.articles) return 'NEUTRAL'
    const articles = sentimentData.news_sentiment.articles
    let totalScore = 0
    articles.forEach(a => { totalScore += (a.sentiment_score || 0) })
    const avgScore = articles.length > 0 ? totalScore / articles.length : 0
    if (avgScore > 0.3) return 'BULLISH'
    if (avgScore < -0.3) return 'BEARISH'
    return 'NEUTRAL'
  }

  function calculateSentimentScore(sentimentData) {
    if (!sentimentData?.news_sentiment?.articles) return 0
    const articles = sentimentData.news_sentiment.articles
    let totalScore = 0
    articles.forEach(a => { totalScore += (a.sentiment_score || 0) })
    return articles.length > 0 ? totalScore / articles.length : 0
  }

  // Debug logging for data flow troubleshooting
  console.log('[Phase3Dashboard] ML Data:', { raw: mlData, extracted: mlPrediction, loading: mlLoading, error: mlError })
  console.log('[Phase3Dashboard] Sentiment Data:', { raw: sentimentData, extracted: sentiment, loading: sentimentLoading, error: sentimentError })
  console.log('[Phase3Dashboard] MTF Data:', { raw: mtfData, extracted: mtf, loading: mtfLoading, error: mtfError })
  console.log('[Phase3Dashboard] Enhanced Signal:', { raw: enhancedSignalData, extracted: enhancedSignal, loading: signalLoading, error: signalError })

  // Helper function to calculate combined sentiment from news and social data
  const calculateCombinedSentiment = (sentimentData) => {
    if (!sentimentData) return { label: 'NEUTRAL', score: 0 }

    const newsArticles = sentimentData.news_sentiment?.articles || []
    // Social sentiment is nested under .twitter (API returns social_sentiment.twitter.posts)
    const socialPosts = sentimentData.social_sentiment?.twitter?.posts ||
                        sentimentData.social_sentiment?.posts || []

    // Calculate average sentiment score from news articles
    let totalScore = 0
    let count = 0

    newsArticles.forEach(article => {
      if (article.sentiment_score !== undefined) {
        totalScore += article.sentiment_score
        count++
      }
    })

    socialPosts.forEach(post => {
      if (post.sentiment_score !== undefined) {
        totalScore += post.sentiment_score
        count++
      }
    })

    const avgScore = count > 0 ? totalScore / count : 0

    // Determine label based on score
    let label = 'NEUTRAL'
    if (avgScore > 0.3) label = 'BULLISH'
    else if (avgScore < -0.3) label = 'BEARISH'

    return { label, score: avgScore }
  }

  // Use API's pre-calculated sentiment values if available, fallback to calculation
  const combinedSentiment = sentiment ? {
    label: sentiment.sentiment_label || calculateCombinedSentiment(sentiment).label,
    score: sentiment.overall_sentiment ?? calculateCombinedSentiment(sentiment).score,
    tradingSignal: sentiment.trading_signal || 'HOLD',
    signalStrength: sentiment.signal_strength || 0,
    dataQuality: sentiment.data_quality || 'UNKNOWN',
    confidence: sentiment.confidence || 0,
  } : { label: 'NEUTRAL', score: 0, tradingSignal: 'HOLD', signalStrength: 0, dataQuality: 'UNKNOWN', confidence: 0 }

  return (
    <TileState
      query={mlQuery}
      title="Phase 3: AI-Enhanced Trading"
      thresholdKey="default"
      lastUpdatedAt={undefined}
      forceStale
      isEmpty={() => false}
    >
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 dark:from-slate-900 dark:to-slate-800 py-8 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-slate-100 mb-2 transition-colors duration-200">
            Phase 3: AI-Enhanced Trading
          </h1>
          <p className="text-gray-600 dark:text-slate-400 text-lg transition-colors duration-200">
            Machine Learning Predictions | Sentiment Analysis | Multi-Timeframe Confirmation
          </p>
        </div>

        {/* Symbol & Interval Selector */}
        <div className="mb-6 flex flex-wrap items-center gap-4">
          {/* Symbol Selection */}
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700 dark:text-slate-300 transition-colors duration-200">Symbol:</span>
            <div className="flex flex-wrap gap-2">
              {symbols.map((symbol) => (
                <button
                  key={symbol}
                  onClick={() => setSelectedSymbol(symbol)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    selectedSymbol === symbol
                      ? 'bg-blue-600 text-white shadow-lg dark:bg-blue-500'
                      : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700'
                  }`}
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>

          {/* Interval Selection */}
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700 dark:text-slate-300 transition-colors duration-200">Interval:</span>
            <div className="flex space-x-2">
              {intervals.map((interval) => (
                <button
                  key={interval.value}
                  onClick={() => setSelectedInterval(interval.value)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    selectedInterval === interval.value
                      ? 'bg-purple-600 text-white shadow-lg dark:bg-purple-500'
                      : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700'
                  }`}
                >
                  {interval.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Enhanced Signal Summary */}
        {signalLoading && (
          <div className="mb-6 rounded-xl shadow-xl p-6 bg-gradient-to-r from-blue-500 to-indigo-600 dark:from-blue-600 dark:to-indigo-700 text-white transition-colors duration-200">
            <div className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mr-3"></div>
              <span className="text-xl">Loading Enhanced Signal...</span>
            </div>
          </div>
        )}

        {signalError && (
          <div className="mb-6 rounded-xl shadow-xl p-6 bg-gradient-to-r from-amber-500 to-orange-600 dark:from-amber-600 dark:to-orange-700 text-white transition-colors duration-200">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold mb-2">Enhanced Signal Unavailable</h2>
                <p className="text-white/90">
                  {signalErrorDetails?.response?.data?.detail ||
                   signalErrorDetails?.message ||
                   'Unable to fetch enhanced signal. Services may be initializing.'}
                </p>
              </div>
              <div className="text-5xl">--</div>
            </div>
          </div>
        )}

        {!signalLoading && !signalError && enhancedSignal && (
          <div className={`mb-6 rounded-xl shadow-xl p-6 transition-colors duration-200 ${
            enhancedSignal.action === 'BUY'
              ? 'bg-gradient-to-r from-green-500 to-emerald-600 dark:from-green-600 dark:to-emerald-700'
              : enhancedSignal.action === 'SELL'
              ? 'bg-gradient-to-r from-red-500 to-rose-600 dark:from-red-600 dark:to-rose-700'
              : 'bg-gradient-to-r from-gray-500 to-slate-600 dark:from-gray-600 dark:to-slate-700'
          } text-white`}>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold mb-2">
                  Phase 3 Enhanced Signal: {enhancedSignal.action || enhancedSignal.signal || 'HOLD'}
                </h2>
                <p className="text-white/90 text-lg">
                  Confidence: {((enhancedSignal.confidence || 0) * 100).toFixed(1)}% |
                  Phase: {enhancedSignal.metadata?.phase || enhancedSignal.phase || '3'}
                </p>
              </div>
              <div className="text-right">
                <div className="text-5xl font-black mb-2">
                  {(enhancedSignal.action || enhancedSignal.signal) === 'BUY' ? '+' :
                   (enhancedSignal.action || enhancedSignal.signal) === 'SELL' ? '-' : '='}
                </div>
              </div>
            </div>

            {/* Signal Breakdown */}
            {(enhancedSignal.metadata || enhancedSignal.components) && (
              <div className="mt-4 pt-4 border-t border-white/20 grid grid-cols-2 md:grid-cols-4 gap-4">
                {(enhancedSignal.metadata?.ml_prediction || enhancedSignal.components?.ml) && (
                  <div>
                    <p className="text-white/70 text-xs mb-1">ML Prediction</p>
                    <p className="font-semibold">
                      {enhancedSignal.metadata?.ml_prediction?.trend ||
                       enhancedSignal.components?.ml?.predicted_direction ||
                       'N/A'}
                    </p>
                    <p className="text-xs text-white/80">
                      {(enhancedSignal.metadata?.ml_prediction?.confidence ||
                        enhancedSignal.components?.ml?.average_confidence)
                        ? `${((enhancedSignal.metadata?.ml_prediction?.confidence ||
                             enhancedSignal.components?.ml?.average_confidence) * 100).toFixed(0)}%`
                        : 'N/A'}
                    </p>
                  </div>
                )}
                {(enhancedSignal.metadata?.sentiment || enhancedSignal.components?.sentiment) && (
                  <div>
                    <p className="text-white/70 text-xs mb-1">Sentiment</p>
                    <p className="font-semibold">
                      {enhancedSignal.metadata?.sentiment?.label ||
                       enhancedSignal.components?.sentiment?.label ||
                       'N/A'}
                    </p>
                    <p className="text-xs text-white/80">
                      Score: {(enhancedSignal.metadata?.sentiment?.score ??
                               enhancedSignal.components?.sentiment?.score) != null
                        ? (enhancedSignal.metadata?.sentiment?.score ??
                           enhancedSignal.components?.sentiment?.score).toFixed(2)
                        : 'N/A'}
                    </p>
                  </div>
                )}
                {(enhancedSignal.metadata?.multi_timeframe || enhancedSignal.components?.mtf) && (
                  <div>
                    <p className="text-white/70 text-xs mb-1">Timeframe Alignment</p>
                    <p className="font-semibold">
                      {(enhancedSignal.metadata?.multi_timeframe?.alignment_score ??
                        enhancedSignal.components?.mtf?.alignment_score) != null
                        ? `${(((enhancedSignal.metadata?.multi_timeframe?.alignment_score ??
                               enhancedSignal.components?.mtf?.alignment_score)) * 100).toFixed(0)}%`
                        : 'N/A'}
                    </p>
                    <p className="text-xs text-white/80">
                      {enhancedSignal.metadata?.multi_timeframe?.consensus_signal ||
                       enhancedSignal.metadata?.multi_timeframe?.overall_signal ||
                       enhancedSignal.components?.mtf?.overall_signal ||
                       'N/A'}
                    </p>
                  </div>
                )}
                <div>
                  <p className="text-white/70 text-xs mb-1">Technical</p>
                  <p className="font-semibold">
                    {enhancedSignal.metadata?.base_signal?.buy_count ??
                     enhancedSignal.components?.technical?.buy_count ?? 0} BUY /
                    {enhancedSignal.metadata?.base_signal?.sell_count ??
                     enhancedSignal.components?.technical?.sell_count ?? 0} SELL
                  </p>
                  <p className="text-xs text-white/80">
                    Score: {(enhancedSignal.metadata?.base_signal?.aggregated_score ??
                             enhancedSignal.components?.technical?.score)?.toFixed(2) ?? 'N/A'}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* ML Predictions Card */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg dark:shadow-slate-900/50 p-6 transition-colors duration-200 border border-transparent dark:border-slate-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 flex items-center transition-colors duration-200">
                <span className="mr-2 text-blue-600 dark:text-blue-400">[ML]</span>
                ML Price Predictions (LSTM)
              </h2>
              <div className="flex items-center space-x-2">
                {mlLoading && (
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600 dark:border-blue-400"></div>
                )}
                {/* Train Model Button (single interval) */}
                <button
                  onClick={handleTrainModel}
                  disabled={trainingStatus === 'training' || isTrainingAll}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center space-x-2 ${
                    trainingStatus === 'training' || isTrainingAll
                      ? 'bg-gray-400 dark:bg-slate-600 text-white cursor-not-allowed'
                      : 'bg-blue-600 dark:bg-blue-500 text-white hover:bg-blue-700 dark:hover:bg-blue-400 shadow-md hover:shadow-lg'
                  }`}
                  title={`Train model for ${intervals.find(i => i.value === selectedInterval)?.label || selectedInterval}`}
                >
                  {trainingStatus === 'training' && !isTrainingAll ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>Training...</span>
                    </>
                  ) : (
                    <span>Train {intervals.find(i => i.value === selectedInterval)?.label}</span>
                  )}
                </button>
                {/* Train All Intervals Button */}
                <button
                  onClick={handleTrainAllIntervals}
                  disabled={trainingStatus === 'training' || isTrainingAll}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center space-x-2 ${
                    isTrainingAll
                      ? 'bg-amber-500 dark:bg-amber-600 text-white cursor-not-allowed'
                      : trainingStatus === 'training'
                      ? 'bg-gray-400 dark:bg-slate-600 text-white cursor-not-allowed'
                      : 'bg-purple-600 dark:bg-purple-500 text-white hover:bg-purple-700 dark:hover:bg-purple-400 shadow-md hover:shadow-lg'
                  }`}
                  title="Train models for all timeframes (5m, 15m, 1h, 4h)"
                >
                  {isTrainingAll ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>{trainAllProgress?.current}/{trainAllProgress?.total}</span>
                    </>
                  ) : (
                    <span>Train All</span>
                  )}
                </button>
              </div>
            </div>

            {/* Training Status Notification */}
            {trainingStatus && (
              <div className={`mb-4 p-4 rounded-lg transition-colors duration-200 ${
                trainingStatus === 'training'
                  ? 'bg-amber-50 dark:bg-amber-500/20 border border-amber-200 dark:border-amber-500/30'
                  : trainingStatus === 'success'
                  ? 'bg-emerald-50 dark:bg-emerald-500/20 border border-emerald-200 dark:border-emerald-500/30'
                  : 'bg-red-50 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30'
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center flex-1">
                    {trainingStatus === 'training' && (
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-amber-600 dark:border-amber-400 mr-3 flex-shrink-0"></div>
                    )}
                    {trainingStatus === 'success' && (
                      <span className="text-emerald-600 dark:text-emerald-400 mr-2 text-xl flex-shrink-0">+</span>
                    )}
                    {trainingStatus === 'error' && (
                      <span className="text-red-600 dark:text-red-400 mr-2 text-xl flex-shrink-0">!</span>
                    )}
                    <div className="flex-1">
                      <p className={`text-sm font-medium transition-colors duration-200 ${
                        trainingStatus === 'training' ? 'text-amber-800 dark:text-amber-300' :
                        trainingStatus === 'success' ? 'text-emerald-800 dark:text-emerald-300' : 'text-red-800 dark:text-red-300'
                      }`}>
                        {trainingMessage}
                      </p>
                      {/* Progress bar for Train All */}
                      {isTrainingAll && trainAllProgress && (
                        <div className="mt-2">
                          <div className="flex justify-between text-xs text-amber-700 dark:text-amber-400 mb-1 transition-colors duration-200">
                            <span>Training {trainAllProgress.currentInterval}...</span>
                            <span>{trainAllProgress.current} of {trainAllProgress.total}</span>
                          </div>
                          <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2 transition-colors duration-200">
                            <div
                              className="bg-amber-600 dark:bg-amber-500 h-2 rounded-full transition-all duration-300"
                              style={{ width: `${(trainAllProgress.current / trainAllProgress.total) * 100}%` }}
                            ></div>
                          </div>
                          {trainAllProgress.completedIntervals.length > 0 && (
                            <p className="text-xs text-amber-700 dark:text-amber-400 mt-1 transition-colors duration-200">
                              Completed: {trainAllProgress.completedIntervals.join(', ')}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  {trainingStatus !== 'training' && (
                    <button
                      onClick={() => { setTrainingStatus(null); setTrainingMessage(''); }}
                      className="text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200 ml-2 flex-shrink-0 transition-colors duration-200"
                    >
                      x
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Error State */}
            {mlError && (
              <div className="bg-red-50 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30 rounded-lg p-4 mb-4 transition-colors duration-200">
                <div className="flex items-start">
                  <span className="text-red-500 dark:text-red-400 mr-2">[!]</span>
                  <div>
                    <p className="text-sm font-medium text-red-800 dark:text-red-300 transition-colors duration-200">ML Prediction Error</p>
                    <p className="text-sm text-red-600 dark:text-red-400 mt-1 transition-colors duration-200">
                      {mlErrorDetails?.response?.data?.detail ||
                       mlErrorDetails?.message ||
                       'Unable to fetch ML predictions. The model may need training.'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {!mlError && mlPrediction ? (
              <div className="space-y-4">
                {/* Trend Classification - Handle UP/DOWN/SIDEWAYS/BULLISH/BEARISH */}
                {(() => {
                  // Normalize direction for display
                  const dir = (mlPrediction.predicted_direction || mlPrediction.trend || 'SIDEWAYS').toUpperCase()
                  const isBullish = dir === 'UP' || dir === 'BULLISH'
                  const isBearish = dir === 'DOWN' || dir === 'BEARISH'
                  // Map to display-friendly names
                  const displayDir = dir === 'UP' ? 'BULLISH' : dir === 'DOWN' ? 'BEARISH' : dir

                  return (
                    <div className={`p-4 rounded-lg transition-colors duration-200 ${
                      isBullish
                        ? 'bg-emerald-50 dark:bg-emerald-500/20 border border-emerald-200 dark:border-emerald-500/30'
                        : isBearish
                        ? 'bg-red-50 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30'
                        : 'bg-gray-50 dark:bg-slate-700/50 border border-gray-200 dark:border-slate-600'
                    }`}>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Predicted Direction</p>
                          <p className={`text-2xl font-bold transition-colors duration-200 ${
                            isBullish ? 'text-emerald-600 dark:text-emerald-400' :
                            isBearish ? 'text-red-600 dark:text-red-400' :
                            'text-gray-600 dark:text-slate-400'
                          }`}>
                            {displayDir}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Avg Confidence</p>
                          <p className="text-2xl font-bold text-blue-600 dark:text-blue-400 transition-colors duration-200">
                            {(mlPrediction.average_confidence ?? mlPrediction.confidence) != null
                              ? `${((mlPrediction.average_confidence ?? mlPrediction.confidence) * 100).toFixed(1)}%`
                              : 'N/A'}
                          </p>
                        </div>
                      </div>
                      {/* Directional Strength */}
                      {mlPrediction.directional_strength != null && (
                        <div className="mt-2 pt-2 border-t border-gray-200 dark:border-slate-600 transition-colors duration-200">
                          <p className="text-xs text-gray-600 dark:text-slate-400 transition-colors duration-200">
                            Directional Strength: {(mlPrediction.directional_strength * 100).toFixed(2)}%
                          </p>
                        </div>
                      )}
                    </div>
                  )
                })()}

                {/* Current Price */}
                {mlPrediction.current_price && (
                  <div className="bg-blue-50 dark:bg-blue-500/20 rounded-lg p-3 transition-colors duration-200">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Current Price</span>
                      <span className="font-bold text-blue-700 dark:text-blue-400 transition-colors duration-200">
                        ${mlPrediction.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>
                )}

                {/* Price Predictions - FIXED: Handle array of prediction objects */}
                {mlPrediction.predictions && Array.isArray(mlPrediction.predictions) && mlPrediction.predictions.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 dark:text-slate-300 mb-2 transition-colors duration-200">
                      Price Predictions ({mlPrediction.predictions.length} steps)
                    </p>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {mlPrediction.predictions.map((pred, idx) => {
                        // Handle both object format and number format
                        const price = typeof pred === 'object' ? pred.predicted_price : pred
                        const confidence = typeof pred === 'object' ? pred.confidence : null
                        const timestamp = typeof pred === 'object' ? pred.timestamp : null

                        return (
                          <div key={idx} className="flex items-center justify-between bg-gray-50 dark:bg-slate-700/50 rounded p-2 transition-colors duration-200">
                            <div>
                              <span className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Step {idx + 1}</span>
                              {timestamp && (
                                <span className="text-xs text-gray-400 dark:text-slate-500 ml-2 transition-colors duration-200">
                                  {new Date(timestamp).toLocaleTimeString()}
                                </span>
                              )}
                            </div>
                            <div className="text-right">
                              <span className="font-semibold text-gray-800 dark:text-slate-200 transition-colors duration-200">
                                ${typeof price === 'number' ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'N/A'}
                              </span>
                              {confidence != null && (
                                <span className="text-xs text-gray-500 dark:text-slate-400 ml-2 transition-colors duration-200">
                                  ({(confidence * 100).toFixed(0)}%)
                                </span>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Model Info */}
                {(mlPrediction.model_version || mlPrediction.model_type) && (
                  <div className="pt-3 border-t border-gray-200 dark:border-slate-700 transition-colors duration-200">
                    <p className="text-xs text-gray-500 dark:text-slate-500 transition-colors duration-200">
                      Model: {mlPrediction.model_type || 'LSTM'} - {mlPrediction.model_version || 'Unknown'}
                    </p>
                    {mlPrediction.model_last_trained && (
                      <p className="text-xs text-gray-500 dark:text-slate-500 transition-colors duration-200">
                        Trained: {new Date(mlPrediction.model_last_trained).toLocaleString()}
                      </p>
                    )}
                    {mlPrediction.prediction_horizon_minutes && (
                      <p className="text-xs text-gray-500 dark:text-slate-500 transition-colors duration-200">
                        Horizon: {mlPrediction.prediction_horizon_minutes} minutes
                      </p>
                    )}
                  </div>
                )}
              </div>
            ) : !mlError && (
              <div className="text-center py-8">
                <p className="text-gray-500 dark:text-slate-400 transition-colors duration-200">
                  {mlLoading ? 'Loading predictions...' : 'Model not trained yet'}
                </p>
                {!mlLoading && (
                  <p className="mt-2 text-sm text-gray-400 dark:text-slate-500 transition-colors duration-200">
                    Train the LSTM model to get price predictions
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Sentiment Analysis Card */}
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg dark:shadow-slate-900/50 p-6 transition-colors duration-200 border border-transparent dark:border-slate-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 flex items-center transition-colors duration-200">
                <span className="mr-2 text-purple-600 dark:text-purple-400">[SA]</span>
                Sentiment Analysis
              </h2>
              {sentimentLoading && (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-600 dark:border-purple-400"></div>
              )}
            </div>

            {/* Error State */}
            {sentimentError && (
              <div className="bg-amber-50 dark:bg-amber-500/20 border border-amber-200 dark:border-amber-500/30 rounded-lg p-4 mb-4 transition-colors duration-200">
                <div className="flex items-start">
                  <span className="text-amber-500 dark:text-amber-400 mr-2">[!]</span>
                  <div>
                    <p className="text-sm font-medium text-amber-800 dark:text-amber-300 transition-colors duration-200">Sentiment Analysis Unavailable</p>
                    <p className="text-sm text-amber-600 dark:text-amber-400 mt-1 transition-colors duration-200">
                      {sentimentErrorDetails?.response?.data?.detail ||
                       sentimentErrorDetails?.message ||
                       'Unable to fetch sentiment data. External API may be unavailable.'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {!sentimentError && sentiment ? (
              <div className="space-y-4">
                {/* Combined Sentiment - Using API's pre-calculated values */}
                <div className={`p-4 rounded-lg transition-colors duration-200 ${
                  combinedSentiment.label === 'BULLISH'
                    ? 'bg-emerald-50 dark:bg-emerald-500/20 border border-emerald-200 dark:border-emerald-500/30'
                    : combinedSentiment.label === 'BEARISH'
                    ? 'bg-red-50 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30'
                    : 'bg-gray-50 dark:bg-slate-700/50 border border-gray-200 dark:border-slate-600'
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Overall Sentiment</p>
                      <p className={`text-2xl font-bold transition-colors duration-200 ${
                        combinedSentiment.label === 'BULLISH' ? 'text-emerald-600 dark:text-emerald-400' :
                        combinedSentiment.label === 'BEARISH' ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-400'
                      }`}>
                        {combinedSentiment.label}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Trading Signal</p>
                      <p className={`text-xl font-bold transition-colors duration-200 ${
                        combinedSentiment.tradingSignal === 'BUY' ? 'text-emerald-600 dark:text-emerald-400' :
                        combinedSentiment.tradingSignal === 'SELL' ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-400'
                      }`}>
                        {combinedSentiment.tradingSignal}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Score</p>
                      <p className="text-2xl font-bold text-purple-600 dark:text-purple-400 transition-colors duration-200">
                        {combinedSentiment.score.toFixed(2)}
                      </p>
                    </div>
                  </div>
                  {/* Data Quality & Confidence */}
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-slate-600 flex justify-between text-xs">
                    <span className="text-gray-600 dark:text-slate-400">
                      Data Quality: <span className={`font-semibold ${
                        combinedSentiment.dataQuality === 'EXCELLENT' ? 'text-emerald-600 dark:text-emerald-400' :
                        combinedSentiment.dataQuality === 'GOOD' ? 'text-blue-600 dark:text-blue-400' :
                        'text-amber-600 dark:text-amber-400'
                      }`}>{combinedSentiment.dataQuality}</span>
                    </span>
                    <span className="text-gray-600 dark:text-slate-400">
                      Confidence: <span className="font-semibold">{(combinedSentiment.confidence * 100).toFixed(0)}%</span>
                    </span>
                  </div>
                </div>

                {/* Sentiment Sources Breakdown */}
                <div className="grid grid-cols-2 gap-3">
                  {/* News Sentiment */}
                  {sentiment.news_sentiment && (
                    <div className="bg-blue-50 dark:bg-blue-500/20 rounded-lg p-3 transition-colors duration-200">
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-xs text-gray-600 dark:text-slate-400 transition-colors duration-200">News Sentiment</p>
                        {sentiment.news_sentiment.sentiment_label && (
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            sentiment.news_sentiment.sentiment_label === 'POSITIVE' || sentiment.news_sentiment.sentiment_label === 'BULLISH'
                              ? 'bg-emerald-100 dark:bg-emerald-500/30 text-emerald-700 dark:text-emerald-400'
                              : sentiment.news_sentiment.sentiment_label === 'NEGATIVE' || sentiment.news_sentiment.sentiment_label === 'BEARISH'
                              ? 'bg-red-100 dark:bg-red-500/30 text-red-700 dark:text-red-400'
                              : 'bg-gray-100 dark:bg-slate-600 text-gray-700 dark:text-slate-300'
                          }`}>
                            {sentiment.news_sentiment.sentiment_label}
                          </span>
                        )}
                      </div>
                      <p className="font-semibold text-gray-800 dark:text-slate-200 transition-colors duration-200">
                        {sentiment.news_sentiment.total_articles || 0} articles
                      </p>
                      {/* Sentiment breakdown counts */}
                      {(sentiment.news_sentiment.positive_count != null || sentiment.news_sentiment.negative_count != null) && (
                        <div className="flex justify-between text-xs mt-2 text-gray-600 dark:text-slate-400">
                          <span className="text-emerald-600 dark:text-emerald-400">{sentiment.news_sentiment.positive_count || 0} pos</span>
                          <span className="text-gray-500 dark:text-slate-500">{sentiment.news_sentiment.neutral_count || 0} neu</span>
                          <span className="text-red-600 dark:text-red-400">{sentiment.news_sentiment.negative_count || 0} neg</span>
                        </div>
                      )}
                      {/* Average sentiment */}
                      {sentiment.news_sentiment.average_sentiment != null && (
                        <p className="text-xs text-gray-600 dark:text-slate-400 mt-1 transition-colors duration-200">
                          Avg: {sentiment.news_sentiment.average_sentiment.toFixed(2)}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Social Sentiment - data is nested under .twitter */}
                  {(sentiment.social_sentiment?.twitter || sentiment.social_sentiment) ? (
                    (() => {
                      const twitter = sentiment.social_sentiment?.twitter || sentiment.social_sentiment
                      return (
                        <div className="bg-purple-50 dark:bg-purple-500/20 rounded-lg p-3 transition-colors duration-200">
                          <div className="flex items-center justify-between mb-1">
                            <p className="text-xs text-gray-600 dark:text-slate-400 transition-colors duration-200">Social Media (Twitter)</p>
                            {twitter.sentiment_label && (
                              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                twitter.sentiment_label === 'BULLISH' ? 'bg-emerald-100 dark:bg-emerald-500/30 text-emerald-700 dark:text-emerald-400' :
                                twitter.sentiment_label === 'BEARISH' ? 'bg-red-100 dark:bg-red-500/30 text-red-700 dark:text-red-400' :
                                'bg-gray-100 dark:bg-slate-600 text-gray-700 dark:text-slate-300'
                              }`}>
                                {twitter.sentiment_label}
                              </span>
                            )}
                          </div>
                          <p className="font-semibold text-gray-800 dark:text-slate-200 transition-colors duration-200">
                            {twitter.total_posts || twitter.posts?.length || 0} posts
                          </p>
                          {/* Sentiment breakdown */}
                          {(twitter.positive_count != null || twitter.negative_count != null) && (
                            <div className="flex justify-between text-xs mt-2 text-gray-600 dark:text-slate-400">
                              <span className="text-emerald-600 dark:text-emerald-400">{twitter.positive_count || 0} pos</span>
                              <span className="text-gray-500 dark:text-slate-500">{twitter.neutral_count || 0} neu</span>
                              <span className="text-red-600 dark:text-red-400">{twitter.negative_count || 0} neg</span>
                            </div>
                          )}
                          {/* Average sentiment - fixed field name */}
                          {(twitter.average_sentiment ?? twitter.weighted_sentiment) != null && (
                            <p className="text-xs text-gray-600 dark:text-slate-400 mt-1 transition-colors duration-200">
                              Avg: {(twitter.average_sentiment ?? twitter.weighted_sentiment).toFixed(3)}
                            </p>
                          )}
                        </div>
                      )
                    })()
                  ) : (
                    <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-3 transition-colors duration-200">
                      <p className="text-xs text-gray-600 dark:text-slate-400 mb-1 transition-colors duration-200">Social Media</p>
                      <p className="font-semibold text-gray-500 dark:text-slate-400 transition-colors duration-200">No data</p>
                    </div>
                  )}
                </div>

                {/* Recent Articles List */}
                {sentiment.news_sentiment?.articles && sentiment.news_sentiment.articles.length > 0 && (
                  <div className="pt-3 border-t border-gray-200 dark:border-slate-700 transition-colors duration-200">
                    <p className="text-xs font-medium text-gray-700 dark:text-slate-300 mb-2 transition-colors duration-200">Recent Headlines</p>
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {sentiment.news_sentiment.articles.slice(0, 5).map((article, idx) => (
                        <div key={idx} className="flex items-center justify-between text-xs">
                          <span className="text-gray-600 dark:text-slate-400 truncate flex-1 mr-2 transition-colors duration-200">
                            {article.title}
                          </span>
                          <span className={`px-1 py-0.5 rounded whitespace-nowrap transition-colors duration-200 ${
                            article.sentiment_label === 'POSITIVE' ? 'bg-emerald-100 dark:bg-emerald-500/30 text-emerald-700 dark:text-emerald-400' :
                            article.sentiment_label === 'NEGATIVE' ? 'bg-red-100 dark:bg-red-500/30 text-red-700 dark:text-red-400' :
                            'bg-gray-100 dark:bg-slate-600 text-gray-700 dark:text-slate-300'
                          }`}>
                            {article.sentiment_score?.toFixed(1) || 0}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : !sentimentError && (
              <div className="text-center py-8">
                <p className="text-gray-500 dark:text-slate-400 transition-colors duration-200">
                  {sentimentLoading ? 'Analyzing sentiment...' : 'No sentiment data available'}
                </p>
                {!sentimentLoading && (
                  <p className="mt-2 text-sm text-gray-400 dark:text-slate-500 transition-colors duration-200">
                    Sentiment analysis aggregates news and social media data
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Multi-Timeframe Heatmap */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg dark:shadow-slate-900/50 p-6 mb-6 transition-colors duration-200 border border-transparent dark:border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 flex items-center transition-colors duration-200">
              <span className="mr-2 text-emerald-600 dark:text-emerald-400">[MTF]</span>
              Multi-Timeframe Analysis
            </h2>
            {mtfLoading && (
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-emerald-600 dark:border-emerald-400"></div>
            )}
          </div>

          {/* Error State */}
          {mtfError && (
            <div className="bg-amber-50 dark:bg-amber-500/20 border border-amber-200 dark:border-amber-500/30 rounded-lg p-4 mb-4 transition-colors duration-200">
              <div className="flex items-start">
                <span className="text-amber-500 dark:text-amber-400 mr-2">[!]</span>
                <div>
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-300 transition-colors duration-200">Multi-Timeframe Analysis Error</p>
                  <p className="text-sm text-amber-600 dark:text-amber-400 mt-1 transition-colors duration-200">
                    {mtfErrorDetails?.response?.data?.detail ||
                     mtfErrorDetails?.message ||
                     'Unable to fetch multi-timeframe data. Technical analysis service may be unavailable.'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {!mtfError && mtf ? (
            <div className="space-y-4">
              {/* Alignment Summary - FIXED: Use overall_signal instead of consensus_signal */}
              <div className="bg-gradient-to-r from-blue-50 to-emerald-50 dark:from-blue-500/20 dark:to-emerald-500/20 rounded-lg p-4 transition-colors duration-200">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Timeframe Alignment</p>
                    <p className="text-3xl font-bold text-emerald-600 dark:text-emerald-400 transition-colors duration-200">
                      {mtf.alignment_score != null ? `${(mtf.alignment_score * 100).toFixed(0)}%` : 'N/A'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Overall Signal</p>
                    {/* FIXED: Use overall_signal */}
                    <p className={`text-2xl font-bold transition-colors duration-200 ${
                      (mtf.overall_signal || mtf.consensus_signal) === 'BUY' ? 'text-emerald-600 dark:text-emerald-400' :
                      (mtf.overall_signal || mtf.consensus_signal) === 'SELL' ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-400'
                    }`}>
                      {mtf.overall_signal || mtf.consensus_signal || 'HOLD'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">Confidence</p>
                    <p className="text-2xl font-bold text-purple-600 dark:text-purple-400 transition-colors duration-200">
                      {mtf.confidence != null
                        ? `${(mtf.confidence * 100).toFixed(0)}%`
                        : 'N/A'}
                    </p>
                  </div>
                </div>
                {/* Summary counts */}
                {mtf.summary && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-slate-600 flex justify-center space-x-6 transition-colors duration-200">
                    <span className="text-sm text-gray-700 dark:text-slate-300 transition-colors duration-200">
                      <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{mtf.summary.buy_timeframes || 0}</span> Buy
                    </span>
                    <span className="text-sm text-gray-700 dark:text-slate-300 transition-colors duration-200">
                      <span className="text-gray-600 dark:text-slate-400 font-semibold">{mtf.summary.hold_timeframes || 0}</span> Hold
                    </span>
                    <span className="text-sm text-gray-700 dark:text-slate-300 transition-colors duration-200">
                      <span className="text-red-600 dark:text-red-400 font-semibold">{mtf.summary.sell_timeframes || 0}</span> Sell
                    </span>
                  </div>
                )}
                {/* Recommendation */}
                {mtf.recommendation && (
                  <div className="mt-2 text-center">
                    <p className="text-sm text-gray-600 dark:text-slate-400 italic transition-colors duration-200">{mtf.recommendation}</p>
                  </div>
                )}
              </div>

              {/* Timeframe Grid - FIXED: Use timeframe_details instead of timeframe_signals */}
              {(mtf.timeframe_details || mtf.timeframe_signals) &&
               Array.isArray(mtf.timeframe_details || mtf.timeframe_signals) &&
               (mtf.timeframe_details || mtf.timeframe_signals).length > 0 ? (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                  {(mtf.timeframe_details || mtf.timeframe_signals).map((tf, index) => (
                    <div
                      key={tf.timeframe || tf.interval || index}
                      className={`rounded-lg p-3 text-center transition-colors duration-200 ${
                        tf.signal === 'BUY'
                          ? 'bg-emerald-100 dark:bg-emerald-500/20 border-2 border-emerald-500 dark:border-emerald-400'
                          : tf.signal === 'SELL'
                          ? 'bg-red-100 dark:bg-red-500/20 border-2 border-red-500 dark:border-red-400'
                          : 'bg-gray-100 dark:bg-slate-700/50 border-2 border-gray-300 dark:border-slate-600'
                      }`}
                    >
                      <p className="text-xs text-gray-600 dark:text-slate-400 mb-1 transition-colors duration-200">
                        {tf.timeframe || `${tf.interval_minutes}m` || 'N/A'}
                      </p>
                      <p className={`font-bold transition-colors duration-200 ${
                        tf.signal === 'BUY' ? 'text-emerald-700 dark:text-emerald-400' :
                        tf.signal === 'SELL' ? 'text-red-700 dark:text-red-400' : 'text-gray-700 dark:text-slate-300'
                      }`}>
                        {tf.signal || 'HOLD'}
                      </p>
                      {/* Show RSI if available */}
                      {tf.rsi != null && (
                        <p className="text-xs text-gray-600 dark:text-slate-400 mt-1 transition-colors duration-200">
                          RSI: {tf.rsi.toFixed(1)}
                        </p>
                      )}
                      {/* Show trend if available */}
                      {tf.trend && (
                        <p className={`text-xs mt-1 transition-colors duration-200 ${
                          tf.trend === 'BULLISH' ? 'text-emerald-600 dark:text-emerald-400' :
                          tf.trend === 'BEARISH' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-slate-500'
                        }`}>
                          {tf.trend}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 text-center transition-colors duration-200">
                  <p className="text-sm text-gray-500 dark:text-slate-400 transition-colors duration-200">Timeframe breakdown not available</p>
                </div>
              )}
            </div>
          ) : !mtfError && (
            <div className="text-center py-8">
              <p className="text-gray-500 dark:text-slate-400 transition-colors duration-200">
                {mtfLoading ? 'Analyzing timeframes...' : 'No multi-timeframe data available'}
              </p>
              {!mtfLoading && (
                <p className="mt-2 text-sm text-gray-400 dark:text-slate-500 transition-colors duration-200">
                  Multi-timeframe analysis confirms signals across 1m, 5m, 15m, 1h, and 4h timeframes
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer Info */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg dark:shadow-slate-900/50 p-6 transition-colors duration-200 border border-transparent dark:border-slate-700">
          <h3 className="font-semibold text-gray-800 dark:text-slate-100 mb-3 transition-colors duration-200">Phase 3 Features</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-gray-600 dark:text-slate-400 transition-colors duration-200">
            <div>
              <p className="font-semibold text-gray-700 dark:text-slate-300 mb-1 transition-colors duration-200">
                <span className="text-blue-600 dark:text-blue-400">[ML]</span> ML Predictions (30% weight)
              </p>
              <p>LSTM neural network forecasts price trends with multi-step predictions</p>
            </div>
            <div>
              <p className="font-semibold text-gray-700 dark:text-slate-300 mb-1 transition-colors duration-200">
                <span className="text-purple-600 dark:text-purple-400">[SA]</span> Sentiment Analysis (15% weight)
              </p>
              <p>Analyzes news and social media to gauge market sentiment</p>
            </div>
            <div>
              <p className="font-semibold text-gray-700 dark:text-slate-300 mb-1 transition-colors duration-200">
                <span className="text-emerald-600 dark:text-emerald-400">[MTF]</span> Multi-Timeframe (15% weight)
              </p>
              <p>Confirms signals across multiple timeframes for higher accuracy</p>
            </div>
          </div>
          <div className="mt-4 text-center text-xs text-gray-500 dark:text-slate-500 transition-colors duration-200">
            Data refresh rates: ML & MTF every 60s | Sentiment every 15min | Enhanced Signal every 30s
          </div>

          {/* Service Status Indicator */}
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-slate-700 transition-colors duration-200">
            <div className="flex items-center justify-center space-x-6 text-xs">
              <span className={`flex items-center transition-colors duration-200 ${mlError ? 'text-red-500 dark:text-red-400' : mlLoading ? 'text-amber-500 dark:text-amber-400' : 'text-emerald-500 dark:text-emerald-400'}`}>
                <span className={`w-2 h-2 rounded-full mr-1 ${mlError ? 'bg-red-500 dark:bg-red-400' : mlLoading ? 'bg-amber-500 dark:bg-amber-400 animate-pulse' : 'bg-emerald-500 dark:bg-emerald-400'}`}></span>
                ML Service
              </span>
              <span className={`flex items-center transition-colors duration-200 ${sentimentError ? 'text-red-500 dark:text-red-400' : sentimentLoading ? 'text-amber-500 dark:text-amber-400' : 'text-emerald-500 dark:text-emerald-400'}`}>
                <span className={`w-2 h-2 rounded-full mr-1 ${sentimentError ? 'bg-red-500 dark:bg-red-400' : sentimentLoading ? 'bg-amber-500 dark:bg-amber-400 animate-pulse' : 'bg-emerald-500 dark:bg-emerald-400'}`}></span>
                Sentiment Service
              </span>
              <span className={`flex items-center transition-colors duration-200 ${mtfError ? 'text-red-500 dark:text-red-400' : mtfLoading ? 'text-amber-500 dark:text-amber-400' : 'text-emerald-500 dark:text-emerald-400'}`}>
                <span className={`w-2 h-2 rounded-full mr-1 ${mtfError ? 'bg-red-500 dark:bg-red-400' : mtfLoading ? 'bg-amber-500 dark:bg-amber-400 animate-pulse' : 'bg-emerald-500 dark:bg-emerald-400'}`}></span>
                MTF Service
              </span>
              <span className={`flex items-center transition-colors duration-200 ${signalError ? 'text-red-500 dark:text-red-400' : signalLoading ? 'text-amber-500 dark:text-amber-400' : 'text-emerald-500 dark:text-emerald-400'}`}>
                <span className={`w-2 h-2 rounded-full mr-1 ${signalError ? 'bg-red-500 dark:bg-red-400' : signalLoading ? 'bg-amber-500 dark:bg-amber-400 animate-pulse' : 'bg-emerald-500 dark:bg-emerald-400'}`}></span>
                Enhanced Signal
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
    </TileState>
  )
}
