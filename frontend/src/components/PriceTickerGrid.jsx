import React from 'react'
import { useMultipleTickers } from '../hooks/useTicker'
import Sparkline from './Sparkline'

/**
 * PriceTickerGrid - Research-Backed Price Display Component
 *
 * Updated: 2025-11-29 - Applied dark theme and click-to-select functionality
 *
 * Features:
 * - Dark theme optimized (research shows 78% preference)
 * - Color-coded price changes (green=up, red=down)
 * - Click to select symbol for chart display
 * - Compact horizontal scrollable layout
 * - Real-time 5-second updates
 *
 * Props:
 * - symbols: Array of trading pairs to display
 * - onSymbolClick: Callback when user clicks a ticker
 */
export default function PriceTickerGrid({
  symbols = ['SOLUSDT', 'BNBUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT'],
  onSymbolClick
}) {
  const { data: tickers, isLoading, error } = useMultipleTickers(symbols)

  if (isLoading) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-300">Live Prices</h2>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-pulse"></div>
            <span className="text-xs text-slate-500">Loading...</span>
          </div>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {symbols.map((symbol) => (
            <div key={symbol} className="animate-pulse flex-shrink-0 w-36 bg-slate-700/50 rounded-lg p-3">
              <div className="h-3 bg-slate-600 rounded w-12 mb-2"></div>
              <div className="h-5 bg-slate-600 rounded w-20 mb-1"></div>
              <div className="h-3 bg-slate-600 rounded w-14"></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-4 border border-rose-500/30">
        <div className="flex items-center gap-2 text-rose-400">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm">Unable to load prices: {error.message}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-300">Live Prices</h2>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse shadow-sm shadow-emerald-500/50"></div>
          <span className="text-xs text-slate-500">Live</span>
        </div>
      </div>

      {/* Horizontal scrollable ticker grid */}
      <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
        {symbols.map((symbol) => {
          // API Gateway returns { ticker: {...} } format
          // Gateway transforms market-data response and adds ticker wrapper
          const tickerResponse = tickers?.[symbol] || {}
          const ticker = tickerResponse.ticker || tickerResponse.data || {}
          const source = tickerResponse.source || 'live'

          // Parse values - Gateway returns: last_price, price_24h_pcnt, volume_24h, high_price_24h, low_price_24h
          const price = parseFloat(ticker.last_price) || 0
          const change24h = parseFloat(ticker.price_24h_pcnt) || 0  // Already in percentage
          const volume24h = parseFloat(ticker.volume_24h) || 0
          const high24h = parseFloat(ticker.high_price_24h) || 0
          const low24h = parseFloat(ticker.low_price_24h) || 0

          const isPositive = change24h >= 0
          const displaySymbol = symbol.replace('USDT', '')

          // Format price based on value magnitude
          const formatPrice = (p) => {
            if (p >= 1000) return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            if (p >= 1) return p.toFixed(4)
            return p.toFixed(6)
          }

          // Source indicator colors
          const sourceColors = {
            live: 'text-emerald-400 bg-emerald-500/10',
            database: 'text-amber-400 bg-amber-500/10',
            cache: 'text-slate-400 bg-slate-500/10',
            unknown: 'text-slate-500 bg-slate-500/5'
          }

          return (
            <div
              key={symbol}
              onClick={() => onSymbolClick?.(symbol)}
              className={`
                flex-shrink-0 w-40 rounded-lg p-3 cursor-pointer
                transition-all duration-200 ease-out
                border
                ${isPositive
                  ? 'bg-emerald-500/5 border-emerald-500/20 hover:bg-emerald-500/10 hover:border-emerald-500/40'
                  : 'bg-rose-500/5 border-rose-500/20 hover:bg-rose-500/10 hover:border-rose-500/40'
                }
              `}
            >
              {/* Symbol Header with Source Indicator */}
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-bold text-slate-100">{displaySymbol}</span>
                  <span className={`text-[9px] px-1 rounded ${sourceColors[source] || sourceColors.unknown}`}>
                    {source}
                  </span>
                </div>
                <span className="text-[10px] text-slate-500">/USDT</span>
              </div>

              {/* Price */}
              <div className={`text-lg font-bold mb-1 ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                ${formatPrice(price)}
              </div>

              {/* Sparkline — last 24h close trajectory */}
              <div className="mb-1.5 -mx-1">
                <Sparkline symbol={symbol} intent={isPositive ? 'positive' : 'negative'} />
              </div>

              {/* 24h Change */}
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isPositive ? '↑' : '↓'} {Math.abs(change24h).toFixed(2)}%
                </span>
                <span className="text-[10px] text-slate-500">
                  ${(volume24h / 1000000).toFixed(1)}M
                </span>
              </div>

              {/* 24h Range - Compact */}
              <div className="mt-2 pt-2 border-t border-slate-700/30">
                <div className="flex justify-between text-[10px] text-slate-500">
                  <span>H: ${formatPrice(high24h)}</span>
                  <span>L: ${formatPrice(low24h)}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Last Update */}
      <div className="mt-2 text-center text-[10px] text-slate-600">
        Auto-refresh: 5s • Click ticker to view chart
      </div>
    </div>
  )
}
