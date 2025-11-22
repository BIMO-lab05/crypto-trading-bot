import React from 'react'
import { useMultipleTickers } from '../hooks/useTicker'

/**
 * PriceTickerGrid component displays real-time price data
 * Shows: current price, 24h change, volume for multiple symbols
 * UPDATED: Now supports 7 trading pairs (added SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT)
 */
export default function PriceTickerGrid({ symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT'] }) {
  const { data: tickers, isLoading, error } = useMultipleTickers(symbols)

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">Live Prices</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
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
        <h2 className="text-2xl font-bold text-gray-800 mb-4">Live Prices</h2>
        <div className="text-red-600">
          <p className="text-sm">Unable to load price data: {error.message}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Live Prices</h2>
        <div className="flex items-center">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2"></div>
          <span className="text-sm text-gray-600">Live</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {symbols.map((symbol) => {
          const ticker = tickers?.[symbol]?.ticker || {}

          // Convert string values to numbers (API may return strings)
          const price = parseFloat(ticker.last_price) || 0
          const change24h = parseFloat(ticker.price_24h_pcnt) || 0
          const volume24h = parseFloat(ticker.volume_24h) || 0
          const high24h = parseFloat(ticker.high_price_24h) || 0
          const low24h = parseFloat(ticker.low_price_24h) || 0

          // Determine if price is up or down
          const isPositive = change24h >= 0

          // Format symbol for display (remove USDT)
          const displaySymbol = symbol.replace('USDT', '')

          return (
            <div
              key={symbol}
              className={`rounded-lg p-4 border-2 transition-all ${
                isPositive
                  ? 'bg-green-50 border-green-200 hover:border-green-400'
                  : 'bg-red-50 border-red-200 hover:border-red-400'
              }`}
            >
              {/* Symbol Header */}
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-lg font-bold text-gray-800">{displaySymbol}</h3>
                <span className="text-xs text-gray-500">USDT</span>
              </div>

              {/* Current Price */}
              <div className="mb-2">
                <p className={`text-3xl font-bold ${
                  isPositive ? 'text-green-600' : 'text-red-600'
                }`}>
                  ${typeof price === 'number' ? price.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }) : '0.00'}
                </p>
              </div>

              {/* 24h Change */}
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-gray-600">24h Change:</span>
                <span className={`text-sm font-semibold ${
                  isPositive ? 'text-green-600' : 'text-red-600'
                }`}>
                  {isPositive ? '▲' : '▼'} {Math.abs(change24h).toFixed(2)}%
                </span>
              </div>

              {/* 24h Stats */}
              <div className="border-t pt-3 space-y-1">
                <div className="flex justify-between text-xs text-gray-600">
                  <span>24h High:</span>
                  <span className="font-semibold">
                    ${typeof high24h === 'number' ? high24h.toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2
                    }) : '0.00'}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-gray-600">
                  <span>24h Low:</span>
                  <span className="font-semibold">
                    ${typeof low24h === 'number' ? low24h.toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2
                    }) : '0.00'}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-gray-600">
                  <span>24h Volume:</span>
                  <span className="font-semibold">
                    ${typeof volume24h === 'number' ? (volume24h / 1000000).toFixed(2) : '0.00'}M
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Last Update Time */}
      <div className="mt-4 text-center text-xs text-gray-500">
        Auto-refreshing every 3 seconds • Last update: {new Date().toLocaleTimeString()}
      </div>
    </div>
  )
}
