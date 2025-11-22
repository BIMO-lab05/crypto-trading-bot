import React from 'react'
import { useMultipleSignals } from '../hooks/useSignals'

/**
 * TradingSignals component displays trading signals for multiple symbols
 * Shows: action (BUY/SELL/HOLD), confidence, key indicators, and aggregated score
 */
export default function TradingSignals({ symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'], interval = 60 }) {
  const { data: signals, isLoading, error } = useMultipleSignals(symbols, interval)

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">Trading Signals</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {symbols.map((symbol) => (
            <div key={symbol} className="animate-pulse bg-gray-50 rounded-lg p-4">
              <div className="h-4 bg-gray-200 rounded w-20 mb-2"></div>
              <div className="h-8 bg-gray-200 rounded w-32 mb-2"></div>
              <div className="h-3 bg-gray-200 rounded w-24"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">Trading Signals</h2>
        <div className="text-red-600">
          <p className="text-sm">Unable to load trading signals: {error.message}</p>
        </div>
      </div>
    )
  }

  // Helper function to get action color and background
  const getActionStyle = (action) => {
    switch (action) {
      case 'BUY':
        return {
          bg: 'bg-green-50',
          border: 'border-green-300',
          text: 'text-green-700',
          badge: 'bg-green-600',
          icon: '📈'
        }
      case 'SELL':
        return {
          bg: 'bg-red-50',
          border: 'border-red-300',
          text: 'text-red-700',
          badge: 'bg-red-600',
          icon: '📉'
        }
      default: // HOLD
        return {
          bg: 'bg-yellow-50',
          border: 'border-yellow-300',
          text: 'text-yellow-700',
          badge: 'bg-yellow-600',
          icon: '⏸️'
        }
    }
  }

  // Helper function to get confidence bar color
  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.75) return 'bg-green-500'
    if (confidence >= 0.5) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Trading Signals</h2>
        <div className="flex items-center">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2"></div>
          <span className="text-sm text-gray-600">Live Analysis</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {symbols.map((symbol) => {
          const signalData = signals?.[symbol]?.signal || {}
          const action = signalData.action || 'HOLD'
          const confidence = signalData.confidence || 0
          const indicators = signalData.indicators || {}
          const aggregatedScore = signalData.aggregated_score || 0
          const metadata = signalData.metadata || {}

          const style = getActionStyle(action)
          const displaySymbol = symbol.replace('USDT', '')

          // Count indicator signals
          const buyCount = metadata.buy_count || 0
          const sellCount = metadata.sell_count || 0
          const holdCount = metadata.hold_count || 0

          // Get key indicator signals (RSI, MACD, Trend)
          const rsi = indicators.RSI || {}
          const macd = indicators.MACD || {}
          const trend = indicators.TREND_FILTER || {}
          const volume = indicators.VOLUME_CONFIRMATION || {}

          return (
            <div
              key={symbol}
              className={`rounded-lg p-4 border-2 transition-all ${style.bg} ${style.border} hover:shadow-md`}
            >
              {/* Header with Symbol and Action Badge */}
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-bold text-gray-800">{displaySymbol}</h3>
                <div className={`${style.badge} text-white px-3 py-1 rounded-full text-sm font-bold flex items-center space-x-1`}>
                  <span>{style.icon}</span>
                  <span>{action}</span>
                </div>
              </div>

              {/* Confidence Score */}
              <div className="mb-3">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs text-gray-600">Confidence:</span>
                  <span className={`text-sm font-bold ${style.text}`}>
                    {(confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${getConfidenceColor(confidence)}`}
                    style={{ width: `${confidence * 100}%` }}
                  ></div>
                </div>
              </div>

              {/* Aggregated Score */}
              <div className="mb-3 pb-3 border-b border-gray-200">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-gray-600">Aggregated Score:</span>
                  <span className={`text-sm font-bold ${aggregatedScore > 0 ? 'text-green-600' : aggregatedScore < 0 ? 'text-red-600' : 'text-gray-600'}`}>
                    {aggregatedScore > 0 ? '+' : ''}{aggregatedScore.toFixed(3)}
                  </span>
                </div>
              </div>

              {/* Indicator Votes */}
              <div className="mb-3">
                <div className="text-xs text-gray-600 mb-2">Indicator Votes:</div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                    <span className="text-xs font-semibold text-green-700">{buyCount} Buy</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
                    <span className="text-xs font-semibold text-yellow-700">{holdCount} Hold</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                    <span className="text-xs font-semibold text-red-700">{sellCount} Sell</span>
                  </div>
                </div>
              </div>

              {/* Key Indicators */}
              <div className="space-y-2">
                <div className="text-xs text-gray-700">
                  <div className="flex justify-between items-center">
                    <span>RSI:</span>
                    <span className={`font-semibold px-2 py-0.5 rounded ${
                      rsi.signal === 'BUY' ? 'bg-green-100 text-green-700' :
                      rsi.signal === 'SELL' ? 'bg-red-100 text-red-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {rsi.value?.toFixed(1) || 'N/A'} - {rsi.signal || 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="text-xs text-gray-700">
                  <div className="flex justify-between items-center">
                    <span>MACD:</span>
                    <span className={`font-semibold px-2 py-0.5 rounded ${
                      macd.signal === 'BUY' ? 'bg-green-100 text-green-700' :
                      macd.signal === 'SELL' ? 'bg-red-100 text-red-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {macd.signal || 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="text-xs text-gray-700">
                  <div className="flex justify-between items-center">
                    <span>Trend:</span>
                    <span className={`font-semibold px-2 py-0.5 rounded ${
                      trend.signal === 'BUY' ? 'bg-green-100 text-green-700' :
                      trend.signal === 'SELL' ? 'bg-red-100 text-red-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {trend.metadata?.trend || trend.signal || 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="text-xs text-gray-700">
                  <div className="flex justify-between items-center">
                    <span>Volume:</span>
                    <span className={`font-semibold px-2 py-0.5 rounded ${
                      volume.metadata?.confirmed ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
                    }`}>
                      {volume.metadata?.strength || 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Timestamp */}
              <div className="mt-3 pt-3 border-t border-gray-200">
                <div className="text-xs text-gray-500 text-center">
                  {signalData.timestamp ? new Date(signalData.timestamp).toLocaleTimeString() : 'N/A'}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Auto-refresh Notice */}
      <div className="mt-4 text-center text-xs text-gray-500">
        Auto-refreshing every 10 seconds • Interval: {interval} minutes
      </div>
    </div>
  )
}
