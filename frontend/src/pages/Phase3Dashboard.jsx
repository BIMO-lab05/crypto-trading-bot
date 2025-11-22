import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { mlAPI, sentimentAPI, multiTimeframeAPI, enhancedTradingAPI } from '../services/api'

/**
 * Phase3Dashboard - AI-Enhanced Trading Dashboard
 * Displays ML predictions, sentiment analysis, and multi-timeframe confirmation
 */

export default function Phase3Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = React.useState('BTCUSDT')
  const [selectedInterval, setSelectedInterval] = React.useState(60)

  // Trading symbols to monitor - UPDATED: Added SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']
  const intervals = [
    { value: 5, label: '5m' },
    { value: 15, label: '15m' },
    { value: 60, label: '1h' },
    { value: 240, label: '4h' },
  ]

  // Fetch ML prediction
  const { data: mlData, isLoading: mlLoading } = useQuery({
    queryKey: ['ml', 'prediction', selectedSymbol, selectedInterval],
    queryFn: () => mlAPI.getPricePrediction(selectedSymbol, selectedInterval),
    refetchInterval: 60000, // Refetch every minute
  })

  // Fetch sentiment analysis
  const { data: sentimentData, isLoading: sentimentLoading } = useQuery({
    queryKey: ['sentiment', 'combined', selectedSymbol],
    queryFn: () => sentimentAPI.getCombinedSentiment(selectedSymbol, 24),
    refetchInterval: 900000, // Refetch every 15 minutes
  })

  // Fetch multi-timeframe analysis
  const { data: mtfData, isLoading: mtfLoading } = useQuery({
    queryKey: ['mtf', 'analysis', selectedSymbol],
    queryFn: () => multiTimeframeAPI.getAnalysis(selectedSymbol),
    refetchInterval: 60000, // Refetch every minute
  })

  // Fetch enhanced signal
  const { data: enhancedSignalData, isLoading: signalLoading } = useQuery({
    queryKey: ['enhanced', 'signal', selectedSymbol, selectedInterval],
    queryFn: () => enhancedTradingAPI.getEnhancedSignal(selectedSymbol, selectedInterval),
    refetchInterval: 30000, // Refetch every 30 seconds
  })

  const mlPrediction = mlData?.data
  const sentiment = sentimentData?.data
  const mtf = mtfData?.data
  const enhancedSignal = enhancedSignalData?.data

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            🤖 Phase 3: AI-Enhanced Trading
          </h1>
          <p className="text-gray-600 text-lg">
            Machine Learning Predictions • Sentiment Analysis • Multi-Timeframe Confirmation
          </p>
        </div>

        {/* Symbol & Interval Selector */}
        <div className="mb-6 flex flex-wrap items-center gap-4">
          {/* Symbol Selection */}
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700">Symbol:</span>
            <div className="flex flex-wrap gap-2">
              {symbols.map((symbol) => (
                <button
                  key={symbol}
                  onClick={() => setSelectedSymbol(symbol)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    selectedSymbol === symbol
                      ? 'bg-blue-600 text-white shadow-lg'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>

          {/* Interval Selection */}
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700">Interval:</span>
            <div className="flex space-x-2">
              {intervals.map((interval) => (
                <button
                  key={interval.value}
                  onClick={() => setSelectedInterval(interval.value)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    selectedInterval === interval.value
                      ? 'bg-purple-600 text-white shadow-lg'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {interval.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Enhanced Signal Summary */}
        {enhancedSignal && (
          <div className={`mb-6 rounded-xl shadow-xl p-6 ${
            enhancedSignal.action === 'BUY'
              ? 'bg-gradient-to-r from-green-500 to-emerald-600'
              : enhancedSignal.action === 'SELL'
              ? 'bg-gradient-to-r from-red-500 to-rose-600'
              : 'bg-gradient-to-r from-gray-500 to-slate-600'
          } text-white`}>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold mb-2">
                  Phase 3 Enhanced Signal: {enhancedSignal.action}
                </h2>
                <p className="text-white/90 text-lg">
                  Confidence: {(enhancedSignal.confidence * 100).toFixed(1)}% •
                  Phase: {enhancedSignal.metadata?.phase || '3'}
                </p>
              </div>
              <div className="text-right">
                <div className="text-5xl font-black mb-2">
                  {enhancedSignal.action === 'BUY' ? '📈' :
                   enhancedSignal.action === 'SELL' ? '📉' : '⏸️'}
                </div>
              </div>
            </div>

            {/* Signal Breakdown */}
            {enhancedSignal.metadata && (
              <div className="mt-4 pt-4 border-t border-white/20 grid grid-cols-2 md:grid-cols-4 gap-4">
                {enhancedSignal.metadata.ml_prediction && (
                  <div>
                    <p className="text-white/70 text-xs mb-1">ML Prediction</p>
                    <p className="font-semibold">
                      {enhancedSignal.metadata.ml_prediction.trend}
                    </p>
                    <p className="text-xs text-white/80">
                      {(enhancedSignal.metadata.ml_prediction.confidence * 100).toFixed(0)}%
                    </p>
                  </div>
                )}
                {enhancedSignal.metadata.sentiment && (
                  <div>
                    <p className="text-white/70 text-xs mb-1">Sentiment</p>
                    <p className="font-semibold">
                      {enhancedSignal.metadata.sentiment.label}
                    </p>
                    <p className="text-xs text-white/80">
                      Score: {enhancedSignal.metadata.sentiment.score.toFixed(2)}
                    </p>
                  </div>
                )}
                {enhancedSignal.metadata.multi_timeframe && (
                  <div>
                    <p className="text-white/70 text-xs mb-1">Timeframe Alignment</p>
                    <p className="font-semibold">
                      {enhancedSignal.metadata.multi_timeframe.alignment_score.toFixed(0)}%
                    </p>
                    <p className="text-xs text-white/80">
                      {enhancedSignal.metadata.multi_timeframe.consensus_signal}
                    </p>
                  </div>
                )}
                <div>
                  <p className="text-white/70 text-xs mb-1">Technical</p>
                  <p className="font-semibold">
                    {enhancedSignal.metadata.base_signal?.buy_count || 0} BUY /
                    {enhancedSignal.metadata.base_signal?.sell_count || 0} SELL
                  </p>
                  <p className="text-xs text-white/80">
                    Consensus: {enhancedSignal.metadata.base_signal?.consensus_count || 0}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* ML Predictions Card */}
          <div className="bg-white rounded-xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-800 flex items-center">
                <span className="mr-2">🧠</span>
                ML Price Predictions (LSTM)
              </h2>
              {mlLoading && (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
              )}
            </div>

            {mlPrediction ? (
              <div className="space-y-4">
                {/* Trend Classification */}
                <div className={`p-4 rounded-lg ${
                  mlPrediction.trend === 'BULLISH'
                    ? 'bg-green-50 border border-green-200'
                    : mlPrediction.trend === 'BEARISH'
                    ? 'bg-red-50 border border-red-200'
                    : 'bg-gray-50 border border-gray-200'
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-gray-600">Predicted Trend</p>
                      <p className={`text-2xl font-bold ${
                        mlPrediction.trend === 'BULLISH' ? 'text-green-600' :
                        mlPrediction.trend === 'BEARISH' ? 'text-red-600' : 'text-gray-600'
                      }`}>
                        {mlPrediction.trend}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-gray-600">Confidence</p>
                      <p className="text-2xl font-bold text-blue-600">
                        {(mlPrediction.confidence * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>

                {/* Price Predictions */}
                {mlPrediction.predictions && mlPrediction.predictions.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">
                      Next {mlPrediction.predictions.length} Step Predictions
                    </p>
                    <div className="space-y-2">
                      {mlPrediction.predictions.map((price, idx) => (
                        <div key={idx} className="flex items-center justify-between bg-gray-50 rounded p-2">
                          <span className="text-sm text-gray-600">Step {idx + 1}</span>
                          <span className="font-semibold text-gray-800">
                            ${price.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Model Info */}
                {mlPrediction.model_version && (
                  <div className="pt-3 border-t border-gray-200">
                    <p className="text-xs text-gray-500">
                      Model: {mlPrediction.model_version}
                    </p>
                    {mlPrediction.last_training_date && (
                      <p className="text-xs text-gray-500">
                        Trained: {mlPrediction.last_training_date}
                      </p>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500">
                  {mlLoading ? 'Loading predictions...' : 'Model not trained yet'}
                </p>
                {!mlLoading && (
                  <button className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">
                    Train Model
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Sentiment Analysis Card */}
          <div className="bg-white rounded-xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-800 flex items-center">
                <span className="mr-2">📰</span>
                Sentiment Analysis
              </h2>
              {sentimentLoading && (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-600"></div>
              )}
            </div>

            {sentiment ? (
              <div className="space-y-4">
                {/* Combined Sentiment */}
                <div className={`p-4 rounded-lg ${
                  sentiment.combined_label === 'BULLISH'
                    ? 'bg-green-50 border border-green-200'
                    : sentiment.combined_label === 'BEARISH'
                    ? 'bg-red-50 border border-red-200'
                    : 'bg-gray-50 border border-gray-200'
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-gray-600">Overall Sentiment</p>
                      <p className={`text-2xl font-bold ${
                        sentiment.combined_label === 'BULLISH' ? 'text-green-600' :
                        sentiment.combined_label === 'BEARISH' ? 'text-red-600' : 'text-gray-600'
                      }`}>
                        {sentiment.combined_label}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-gray-600">Score</p>
                      <p className="text-2xl font-bold text-purple-600">
                        {sentiment.combined_score?.toFixed(2) || '0.00'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Sentiment Sources Breakdown */}
                <div className="grid grid-cols-2 gap-3">
                  {/* News Sentiment */}
                  {sentiment.news_sentiment && (
                    <div className="bg-blue-50 rounded-lg p-3">
                      <p className="text-xs text-gray-600 mb-1">News</p>
                      <p className="font-semibold text-gray-800">
                        {sentiment.news_sentiment.sentiment_label}
                      </p>
                      <p className="text-xs text-gray-600">
                        Score: {sentiment.news_sentiment.sentiment_score?.toFixed(2)}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {sentiment.news_sentiment.articles_analyzed || 0} articles
                      </p>
                    </div>
                  )}

                  {/* Social Sentiment */}
                  {sentiment.social_sentiment && (
                    <div className="bg-purple-50 rounded-lg p-3">
                      <p className="text-xs text-gray-600 mb-1">Social Media</p>
                      <p className="font-semibold text-gray-800">
                        {sentiment.social_sentiment.sentiment_label}
                      </p>
                      <p className="text-xs text-gray-600">
                        Score: {sentiment.social_sentiment.sentiment_score?.toFixed(2)}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {sentiment.social_sentiment.posts_analyzed || 0} posts
                      </p>
                    </div>
                  )}
                </div>

                {/* Confidence */}
                <div className="flex items-center justify-between pt-3 border-t border-gray-200">
                  <span className="text-sm text-gray-600">Confidence</span>
                  <span className="font-semibold text-gray-800">
                    {(sentiment.confidence * 100).toFixed(1)}%
                  </span>
                </div>

                {/* Data Quality */}
                {sentiment.data_quality && (
                  <div className="text-xs text-gray-500 text-center">
                    Data Quality: {sentiment.data_quality}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500">
                  {sentimentLoading ? 'Analyzing sentiment...' : 'No sentiment data available'}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Multi-Timeframe Heatmap */}
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-800 flex items-center">
              <span className="mr-2">⏱️</span>
              Multi-Timeframe Analysis
            </h2>
            {mtfLoading && (
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-green-600"></div>
            )}
          </div>

          {mtf ? (
            <div className="space-y-4">
              {/* Alignment Summary */}
              <div className="bg-gradient-to-r from-blue-50 to-green-50 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600">Timeframe Alignment</p>
                    <p className="text-3xl font-bold text-green-600">
                      {mtf.alignment_score?.toFixed(0) || 0}%
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-600">Consensus Signal</p>
                    <p className={`text-2xl font-bold ${
                      mtf.consensus_signal === 'BUY' ? 'text-green-600' :
                      mtf.consensus_signal === 'SELL' ? 'text-red-600' : 'text-gray-600'
                    }`}>
                      {mtf.consensus_signal}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-600">Signal Strength</p>
                    <p className="text-2xl font-bold text-purple-600">
                      {(mtf.signal_strength * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>
              </div>

              {/* Timeframe Grid */}
              {mtf.timeframe_signals && mtf.timeframe_signals.length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  {mtf.timeframe_signals.map((tf) => (
                    <div
                      key={tf.timeframe}
                      className={`rounded-lg p-3 text-center ${
                        tf.signal === 'BUY'
                          ? 'bg-green-100 border-2 border-green-500'
                          : tf.signal === 'SELL'
                          ? 'bg-red-100 border-2 border-red-500'
                          : 'bg-gray-100 border-2 border-gray-300'
                      }`}
                    >
                      <p className="text-xs text-gray-600 mb-1">{tf.timeframe}</p>
                      <p className={`font-bold ${
                        tf.signal === 'BUY' ? 'text-green-700' :
                        tf.signal === 'SELL' ? 'text-red-700' : 'text-gray-700'
                      }`}>
                        {tf.signal}
                      </p>
                      <p className="text-xs text-gray-600 mt-1">
                        {(tf.confidence * 100).toFixed(0)}%
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Trend Classification */}
              <div className="grid grid-cols-3 gap-3 pt-3 border-t border-gray-200">
                <div className="text-center">
                  <p className="text-xs text-gray-600 mb-1">Short Term</p>
                  <p className="font-semibold text-gray-800">
                    {mtf.short_term_trend || 'NEUTRAL'}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-600 mb-1">Medium Term</p>
                  <p className="font-semibold text-gray-800">
                    {mtf.medium_term_trend || 'NEUTRAL'}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-gray-600 mb-1">Long Term</p>
                  <p className="font-semibold text-gray-800">
                    {mtf.long_term_trend || 'NEUTRAL'}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500">
                {mtfLoading ? 'Analyzing timeframes...' : 'No multi-timeframe data available'}
              </p>
            </div>
          )}
        </div>

        {/* Footer Info */}
        <div className="bg-white rounded-xl shadow-lg p-6">
          <h3 className="font-semibold text-gray-800 mb-3">Phase 3 Features</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-gray-600">
            <div>
              <p className="font-semibold text-gray-700 mb-1">🧠 ML Predictions (30% weight)</p>
              <p>LSTM neural network forecasts price trends with multi-step predictions</p>
            </div>
            <div>
              <p className="font-semibold text-gray-700 mb-1">📰 Sentiment Analysis (15% weight)</p>
              <p>Analyzes news and social media to gauge market sentiment</p>
            </div>
            <div>
              <p className="font-semibold text-gray-700 mb-1">⏱️ Multi-Timeframe (15% weight)</p>
              <p>Confirms signals across 4-6 timeframes for higher accuracy</p>
            </div>
          </div>
          <div className="mt-4 text-center text-xs text-gray-500">
            Data refresh rates: ML & MTF every 60s • Sentiment every 15min • Enhanced Signal every 30s
          </div>
        </div>
      </div>
    </div>
  )
}
