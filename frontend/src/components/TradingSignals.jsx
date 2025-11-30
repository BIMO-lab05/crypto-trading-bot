import React from 'react'
import { useMultipleSignals } from '../hooks/useSignals'

/**
 * TradingSignals - Research-Backed Signal Display Component
 *
 * Updated: 2025-11-29 - Applied dark theme and compact mode
 *
 * Features:
 * - Dark theme optimized
 * - Color-coded signals (green=BUY, red=SELL, amber=HOLD)
 * - Compact mode for sidebar display
 * - Research-optimized parameters display (MACD 5-35-5, RSI 9)
 * - Real-time 5-second updates
 *
 * Props:
 * - symbols: Array of trading pairs to display
 * - interval: Timeframe in minutes
 * - compact: Boolean for compact sidebar mode
 */
export default function TradingSignals({
  symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
  interval = 60,
  compact = false
}) {
  const { data: signals, isLoading, error } = useMultipleSignals(symbols, interval)

  // Helper function to get action style for dark theme
  const getActionStyle = (action) => {
    switch (action) {
      case 'BUY':
        return {
          bg: 'bg-emerald-500/10',
          border: 'border-emerald-500/30',
          text: 'text-emerald-400',
          badge: 'bg-emerald-500',
          icon: '↑'
        }
      case 'SELL':
        return {
          bg: 'bg-rose-500/10',
          border: 'border-rose-500/30',
          text: 'text-rose-400',
          badge: 'bg-rose-500',
          icon: '↓'
        }
      default: // HOLD
        return {
          bg: 'bg-amber-500/10',
          border: 'border-amber-500/30',
          text: 'text-amber-400',
          badge: 'bg-amber-500',
          icon: '→'
        }
    }
  }

  // Helper function to get confidence bar color
  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.75) return 'bg-emerald-500'
    if (confidence >= 0.5) return 'bg-amber-500'
    return 'bg-rose-500'
  }

  if (isLoading) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 h-full">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-300">Trading Signals</h2>
          <div className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-pulse"></div>
        </div>
        <div className="space-y-3">
          {symbols.slice(0, compact ? 4 : symbols.length).map((symbol) => (
            <div key={symbol} className="animate-pulse bg-slate-700/50 rounded-lg p-3">
              <div className="h-3 bg-slate-600 rounded w-16 mb-2"></div>
              <div className="h-5 bg-slate-600 rounded w-20"></div>
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
          <span className="text-sm">Signal error: {error.message}</span>
        </div>
      </div>
    )
  }

  // Compact mode: Vertical list for sidebar
  if (compact) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 backdrop-blur-sm h-full">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-300">Trading Signals</h2>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-pulse"></div>
            <span className="text-[10px] text-slate-500">Live</span>
          </div>
        </div>

        <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
          {symbols.map((symbol) => {
            const signalData = signals?.[symbol]?.signal || {}
            const action = signalData.action || 'HOLD'
            const confidence = signalData.confidence || 0
            const style = getActionStyle(action)
            const displaySymbol = symbol.replace('USDT', '')

            return (
              <div
                key={symbol}
                className={`rounded-lg p-3 border transition-all ${style.bg} ${style.border} hover:border-opacity-60`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-bold text-slate-100">{displaySymbol}</span>
                  <span className={`text-xs font-bold ${style.badge} text-white px-2 py-0.5 rounded-full flex items-center gap-1`}>
                    <span>{style.icon}</span>
                    <span>{action}</span>
                  </span>
                </div>

                {/* Confidence Bar */}
                <div className="mb-2">
                  <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                    <span>Confidence</span>
                    <span className={style.text}>{(confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full transition-all duration-300 ${getConfidenceColor(confidence)}`}
                      style={{ width: `${confidence * 100}%` }}
                    ></div>
                  </div>
                </div>

                {/* Quick Indicators */}
                <div className="flex justify-between text-[10px]">
                  <IndicatorPill
                    label="RSI"
                    signal={signalData.indicators?.RSI?.signal}
                  />
                  <IndicatorPill
                    label="MACD"
                    signal={signalData.indicators?.MACD?.signal}
                  />
                  <IndicatorPill
                    label="Trend"
                    signal={signalData.indicators?.TREND_FILTER?.signal}
                  />
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-3 pt-2 border-t border-slate-700/50 text-center text-[10px] text-slate-600">
          Research-optimized: MACD(5-35-5) RSI(9)
        </div>
      </div>
    )
  }

  // Full mode: Grid display
  return (
    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-300">Trading Signals</h2>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-pulse"></div>
          <span className="text-xs text-slate-500">Live Analysis</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {symbols.map((symbol) => {
          const signalData = signals?.[symbol]?.signal || {}
          const action = signalData.action || 'HOLD'
          const confidence = signalData.confidence || 0
          const indicators = signalData.indicators || {}
          const aggregatedScore = signalData.aggregated_score || 0
          const metadata = signalData.metadata || {}

          const style = getActionStyle(action)
          const displaySymbol = symbol.replace('USDT', '')

          const buyCount = metadata.buy_count || 0
          const sellCount = metadata.sell_count || 0
          const holdCount = metadata.hold_count || 0

          const rsi = indicators.RSI || {}
          const macd = indicators.MACD || {}
          const trend = indicators.TREND_FILTER || {}

          return (
            <div
              key={symbol}
              className={`rounded-lg p-4 border transition-all ${style.bg} ${style.border} hover:border-opacity-60`}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <span className="text-lg font-bold text-slate-100">{displaySymbol}</span>
                <span className={`text-sm font-bold ${style.badge} text-white px-3 py-1 rounded-full flex items-center gap-1`}>
                  <span>{style.icon}</span>
                  <span>{action}</span>
                </span>
              </div>

              {/* Confidence */}
              <div className="mb-3">
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span>Confidence</span>
                  <span className={`font-semibold ${style.text}`}>{(confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${getConfidenceColor(confidence)}`}
                    style={{ width: `${confidence * 100}%` }}
                  ></div>
                </div>
              </div>

              {/* Score */}
              <div className="mb-3 pb-3 border-b border-slate-700/50">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Aggregated Score</span>
                  <span className={`font-semibold ${aggregatedScore > 0 ? 'text-emerald-400' : aggregatedScore < 0 ? 'text-rose-400' : 'text-slate-400'}`}>
                    {aggregatedScore > 0 ? '+' : ''}{aggregatedScore.toFixed(3)}
                  </span>
                </div>
              </div>

              {/* Votes */}
              <div className="mb-3">
                <div className="text-[10px] text-slate-500 mb-1.5">Indicator Votes</div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-emerald-400 font-medium">{buyCount} Buy</span>
                  <span className="text-[10px] text-amber-400 font-medium">{holdCount} Hold</span>
                  <span className="text-[10px] text-rose-400 font-medium">{sellCount} Sell</span>
                </div>
              </div>

              {/* Indicators */}
              <div className="space-y-1.5">
                <IndicatorRow label="RSI" value={rsi.value?.toFixed(1)} signal={rsi.signal} />
                <IndicatorRow label="MACD" signal={macd.signal} />
                <IndicatorRow label="Trend" value={trend.metadata?.trend} signal={trend.signal} />
              </div>

              {/* Timestamp */}
              <div className="mt-3 pt-2 border-t border-slate-700/50 text-center text-[10px] text-slate-600">
                {signalData.timestamp ? new Date(signalData.timestamp).toLocaleTimeString() : 'N/A'}
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-4 text-center text-[10px] text-slate-600">
        Auto-refresh: 5s • Research-optimized: MACD(5-35-5), RSI(9), BB(2.5σ)
      </div>
    </div>
  )
}

/**
 * IndicatorPill - Compact indicator display
 */
function IndicatorPill({ label, signal }) {
  const getColor = () => {
    if (signal === 'BUY') return 'bg-emerald-500/20 text-emerald-400'
    if (signal === 'SELL') return 'bg-rose-500/20 text-rose-400'
    return 'bg-slate-700/50 text-slate-400'
  }

  return (
    <span className={`px-1.5 py-0.5 rounded ${getColor()}`}>
      {label}
    </span>
  )
}

/**
 * IndicatorRow - Full indicator row display
 */
function IndicatorRow({ label, value, signal }) {
  const getColor = () => {
    if (signal === 'BUY') return 'bg-emerald-500/20 text-emerald-400'
    if (signal === 'SELL') return 'bg-rose-500/20 text-rose-400'
    return 'bg-slate-700/50 text-slate-400'
  }

  return (
    <div className="flex justify-between items-center text-xs">
      <span className="text-slate-500">{label}</span>
      <span className={`font-medium px-2 py-0.5 rounded ${getColor()}`}>
        {value ? `${value} - ${signal || 'N/A'}` : signal || 'N/A'}
      </span>
    </div>
  )
}
