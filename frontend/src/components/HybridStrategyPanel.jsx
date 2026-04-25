import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { tradingAPI } from '../services/api'

/**
 * Hybrid Strategy Panel Component
 *
 * Displays hybrid strategy routing information:
 * - Current market regime (TRENDING/RANGING)
 * - Strategy distribution (Trend-Following vs Mean Reversion)
 * - Routing statistics
 * - Recent activity
 *
 * Created: 2026-01-06
 * Purpose: Provide visibility into hybrid strategy decision-making
 */
export default function HybridStrategyPanel() {
  // Fetch trading status every 5 seconds
  const { data, isLoading, error } = useQuery({
    queryKey: ['trading-status'],
    queryFn: () => tradingAPI.getStatus(),
    refetchInterval: 5000,
    staleTime: 4000,
  })

  if (isLoading) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700/50 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-200">Hybrid Strategy Routing</h2>
          <div className="animate-pulse flex items-center gap-1.5">
            <div className="w-2 h-2 bg-slate-500 rounded-full"></div>
            <span className="text-xs text-slate-500">Loading...</span>
          </div>
        </div>
        <div className="animate-pulse space-y-4">
          <div className="h-16 bg-slate-700/50 rounded-lg"></div>
          <div className="h-24 bg-slate-700/50 rounded-lg"></div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-6 border border-rose-500/30">
        <div className="flex items-center gap-2 text-rose-400">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm">Unable to load strategy data</span>
        </div>
      </div>
    )
  }

  const status = data?.status || {}
  const hybrid = status.hybrid_strategy_stats || {}

  // Calculate metrics
  const trendPct = hybrid.trend_pct || 0
  const meanRevPct = hybrid.mean_reversion_pct || 0
  const totalSignals = hybrid.total_signals || 0

  // Determine market regime based on percentages
  let currentRegime = 'MIXED'
  let regimeColor = 'text-slate-400'
  let regimeIcon = '⚖️'

  if (trendPct > 55) {
    currentRegime = 'TRENDING'
    regimeColor = 'text-blue-400'
    regimeIcon = '📈'
  } else if (meanRevPct > 55) {
    currentRegime = 'RANGING'
    regimeColor = 'text-emerald-400'
    regimeIcon = '↔️'
  }

  // Active strategy based on current majority
  const activeStrategy = trendPct > meanRevPct ? 'Trend-Following' : 'Mean Reversion'
  const activeStrategyColor = trendPct > meanRevPct ? 'text-blue-400' : 'text-emerald-400'

  return (
    <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700/50 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-slate-200">Hybrid Strategy Routing</h2>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse shadow-sm shadow-emerald-500/50"></div>
          <span className="text-xs text-slate-500">Live</span>
        </div>
      </div>

      {/* Current Regime Card */}
      <div className="bg-slate-900/50 rounded-lg p-4 mb-6 border border-slate-700/30">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Current Market</span>
          <span className="text-2xl">{regimeIcon}</span>
        </div>
        <div className={`text-2xl font-bold ${regimeColor} mb-1`}>
          {currentRegime}
        </div>
        <div className="text-sm text-slate-400">
          Active Strategy: <span className={`font-medium ${activeStrategyColor}`}>{activeStrategy}</span>
        </div>
      </div>

      {/* Strategy Distribution */}
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-slate-300">Trend-Following</span>
            <span className="text-sm font-bold text-blue-400">{trendPct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-slate-700/30 rounded-full h-3 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all duration-500 shadow-lg shadow-blue-500/30"
              style={{ width: `${trendPct}%` }}
            />
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {hybrid.trend_signals?.toLocaleString() || 0} signals routed
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-slate-300">Mean Reversion</span>
            <span className="text-sm font-bold text-emerald-400">{meanRevPct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-slate-700/30 rounded-full h-3 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-emerald-600 rounded-full transition-all duration-500 shadow-lg shadow-emerald-500/30"
              style={{ width: `${meanRevPct}%` }}
            />
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {hybrid.mean_reversion_signals?.toLocaleString() || 0} signals routed
          </div>
        </div>
      </div>

      {/* Statistics Footer */}
      <div className="mt-6 pt-4 border-t border-slate-700/30">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400">Total Routing Decisions</span>
          <span className="font-mono font-medium text-slate-300">{totalSignals.toLocaleString()}</span>
        </div>
      </div>

      {/* Info Tooltip */}
      <div className="mt-4 p-3 bg-slate-900/30 rounded-lg border border-slate-700/20">
        <div className="flex gap-2">
          <svg className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-xs text-slate-400 leading-relaxed">
            <span className="font-medium text-slate-300">Hybrid Strategy:</span> Automatically switches between
            trend-following (when ADX ≥ 25) and mean reversion (when ADX &lt; 25) based on market conditions.
          </div>
        </div>
      </div>
    </div>
  )
}
