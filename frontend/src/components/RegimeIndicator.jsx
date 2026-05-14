import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { tradingAPI } from '../services/api'
import TileState from './TileState'

/**
 * Regime Indicator Component
 *
 * Compact indicator showing current market regime
 * Designed to fit in the key metrics strip
 *
 * Created: 2026-01-06
 * Purpose: Quick visual indicator of market regime and active strategy
 *
 * UPDATED 2026-05-13 (Plan 06-05, DASH-05): wrapped in <TileState/> per
 * audit verdict FIXED.
 */
export default function RegimeIndicator() {
  const q = useQuery({
    queryKey: ['trading-status-regime'],
    queryFn: () => tradingAPI.getStatus(),
    refetchInterval: 5000,
    staleTime: 4000,
  })

  const hybrid = q.data?.status?.hybrid_strategy_stats || {}
  const trendPct = hybrid.trend_pct || 0
  const meanRevPct = hybrid.mean_reversion_pct || 0

  // Determine market regime
  let regime = 'MIXED'
  let regimeColor = 'slate'
  let regimeBg = 'bg-slate-600/20'
  let regimeBorder = 'border-slate-600/50'
  let regimeIcon = '⚖️'
  let strategy = 'Balanced'

  if (trendPct > 55) {
    regime = 'TRENDING'
    regimeColor = 'blue'
    regimeBg = 'bg-blue-500/10'
    regimeBorder = 'border-blue-500/30'
    regimeIcon = '📈'
    strategy = 'Trend'
  } else if (meanRevPct > 55) {
    regime = 'RANGING'
    regimeColor = 'emerald'
    regimeBg = 'bg-emerald-500/10'
    regimeBorder = 'border-emerald-500/30'
    regimeIcon = '↔️'
    strategy = 'Mean Rev'
  }

  return (
    <div data-testid="regime-indicator" style={{ display: 'contents' }}>
    <TileState
      query={q}
      title="Market Regime"
      thresholdKey="signals"
      lastUpdatedAt={undefined}
      isEmpty={(d) => !d || !d.status}
    >
    <div className={`flex items-center gap-3 px-4 py-2.5 ${regimeBg} rounded-lg border ${regimeBorder} backdrop-blur-sm`}>
      {/* Icon */}
      <div className="text-lg">{regimeIcon}</div>

      {/* Content */}
      <div className="flex flex-col">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Market</span>
          <span className={`text-sm font-bold text-${regimeColor}-400`}>{regime}</span>
        </div>
        <div className="text-xs text-slate-500">
          Using <span className={`font-medium text-${regimeColor}-400`}>{strategy}</span> Strategy
        </div>
      </div>

      {/* Live indicator */}
      <div className={`w-2 h-2 bg-${regimeColor}-500 rounded-full animate-pulse shadow-sm shadow-${regimeColor}-500/50 ml-1`}></div>
    </div>
    </TileState>
    </div>
  )
}
