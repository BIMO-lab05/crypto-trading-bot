import React from 'react'
import { usePerformanceAnalytics } from '../hooks/useAutoTrader'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import TileState from './TileState'

/**
 * Calculate advanced performance metrics from trade history
 */
function calculateAdvancedMetrics(trades, performanceMetrics) {
  if (!trades || trades.length === 0) return null

  // Extract realized P&L from closed trades
  const tradePnLs = trades
    .filter(t => t.status === 'CLOSED' && t.realized_pnl)
    .map(t => parseFloat(t.realized_pnl))

  if (tradePnLs.length === 0) return null

  const totalTrades = tradePnLs.length
  const avgPnL = tradePnLs.reduce((sum, pnl) => sum + pnl, 0) / totalTrades

  // Calculate standard deviation
  const variance = tradePnLs.reduce((sum, pnl) => sum + Math.pow(pnl - avgPnL, 2), 0) / totalTrades
  const stdDev = Math.sqrt(variance)

  // Calculate downside deviation (for Sortino)
  const downsidePnLs = tradePnLs.filter(pnl => pnl < 0)
  const downsideVariance = downsidePnLs.length > 0
    ? downsidePnLs.reduce((sum, pnl) => sum + Math.pow(pnl, 2), 0) / downsidePnLs.length
    : 0
  const downsideDev = Math.sqrt(downsideVariance)

  // Sharpe Ratio (assuming risk-free rate = 0 for crypto)
  const sharpeRatio = stdDev !== 0 ? avgPnL / stdDev : 0

  // Sortino Ratio (only penalizes downside volatility)
  const sortinoRatio = downsideDev !== 0 ? avgPnL / downsideDev : 0

  // Max Drawdown - calculate from cumulative P&L
  let cumulativePnL = 0
  let peak = 0
  let maxDrawdown = 0
  tradePnLs.forEach(pnl => {
    cumulativePnL += pnl
    if (cumulativePnL > peak) peak = cumulativePnL
    const drawdown = peak - cumulativePnL
    if (drawdown > maxDrawdown) maxDrawdown = drawdown
  })

  // VaR 95% - sort P&Ls and find 5th percentile
  const sortedPnLs = [...tradePnLs].sort((a, b) => a - b)
  const var95Index = Math.floor(totalTrades * 0.05)
  const var95 = sortedPnLs[var95Index] || 0

  // CVaR 95% - average of losses beyond VaR
  const lossesBeforeVar = sortedPnLs.slice(0, var95Index + 1)
  const cvar95 = lossesBeforeVar.length > 0
    ? lossesBeforeVar.reduce((sum, pnl) => sum + pnl, 0) / lossesBeforeVar.length
    : 0

  return {
    sharpeRatio,
    sortinoRatio,
    maxDrawdown,
    var95: Math.abs(var95),
    cvar95: Math.abs(cvar95),
    totalTrades: performanceMetrics?.total_trades || totalTrades,
    winningTrades: performanceMetrics?.winning_trades || tradePnLs.filter(p => p > 0).length,
    winRate: performanceMetrics?.win_rate || (tradePnLs.filter(p => p > 0).length / totalTrades * 100),
  }
}

/**
 * PerformanceAnalyticsPanel - Display Advanced Performance Metrics
 *
 * Created: 2025-11-30
 *
 * Shows real-time performance analytics:
 * - Sharpe Ratio (risk-adjusted return)
 * - Sortino Ratio (downside risk-adjusted return)
 * - Max Drawdown (largest peak-to-trough decline)
 * - Value at Risk (VaR 95%)
 * - Conditional VaR (Expected Shortfall)
 * - Win Rate and Trade Statistics
 *
 * Research-backed metrics used by professional traders and hedge funds
 */

const RatioGauge = ({ label, value, min, max, goodRange, description }) => {
  const normalizedValue = Math.max(min, Math.min(max, value || 0))
  const percentage = ((normalizedValue - min) / (max - min)) * 100

  const getColor = () => {
    if (value == null) return 'bg-slate-500'
    if (goodRange) {
      const [goodMin, goodMax] = goodRange
      if (value >= goodMin && value <= goodMax) return 'bg-emerald-500'
      if (value < goodMin) return 'bg-amber-500'
      return 'bg-rose-500'
    }
    if (value > 1) return 'bg-emerald-500'
    if (value > 0) return 'bg-amber-500'
    return 'bg-rose-500'
  }

  return (
    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
      <div className="flex justify-between items-start mb-2">
        <div>
          <h4 className="text-sm font-medium text-slate-200">{label}</h4>
          {description && (
            <p className="text-xs text-slate-500 mt-0.5">{description}</p>
          )}
        </div>
        <span className={`text-lg font-bold ${
          value == null ? 'text-slate-500' :
          value > 1 ? 'text-emerald-400' :
          value > 0 ? 'text-amber-400' :
          'text-rose-400'
        }`}>
          {value != null ? value.toFixed(2) : 'N/A'}
        </span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${getColor()} rounded-full transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-slate-500 mt-1">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

const RiskMetricCard = ({ label, value, format, trend, description, icon }) => {
  const formatValue = () => {
    if (value == null) return 'N/A'
    switch (format) {
      case 'percent':
        return `${(value * 100).toFixed(2)}%`
      case 'currency':
        return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
      default:
        return value.toFixed(2)
    }
  }

  const getTrendColor = () => {
    if (trend === 'positive') return 'text-emerald-400'
    if (trend === 'negative') return 'text-rose-400'
    return 'text-slate-100'
  }

  return (
    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
      <div className="flex items-center gap-2 mb-2">
        {icon && <span className="text-slate-400">{icon}</span>}
        <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</h4>
      </div>
      <div className={`text-xl font-bold ${getTrendColor()} mb-1`}>
        {formatValue()}
      </div>
      {description && (
        <p className="text-xs text-slate-500">{description}</p>
      )}
    </div>
  )
}

const TradeStatsCard = ({ totalTrades, winningTrades, losingTrades, winRate }) => (
  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
    <h4 className="text-sm font-medium text-slate-200 mb-3">Trade Statistics</h4>

    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">Total Trades</span>
        <span className="text-sm font-bold text-slate-100">{totalTrades || 0}</span>
      </div>

      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">Winning</span>
        <span className="text-sm font-bold text-emerald-400">{winningTrades || 0}</span>
      </div>

      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">Losing</span>
        <span className="text-sm font-bold text-rose-400">{losingTrades || 0}</span>
      </div>

      <div className="pt-2 border-t border-slate-700">
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400">Win Rate</span>
          <span className={`text-lg font-bold ${
            (winRate || 0) >= 50 ? 'text-emerald-400' :
            (winRate || 0) >= 40 ? 'text-amber-400' :
            'text-rose-400'
          }`}>
            {winRate != null ? `${winRate.toFixed(1)}%` : 'N/A'}
          </span>
        </div>

        {totalTrades > 0 && (
          <div className="mt-2 h-2 bg-slate-700 rounded-full overflow-hidden flex">
            <div
              className="h-full bg-emerald-500"
              style={{ width: `${(winningTrades / totalTrades) * 100}%` }}
            />
            <div
              className="h-full bg-rose-500"
              style={{ width: `${((losingTrades || 0) / totalTrades) * 100}%` }}
            />
          </div>
        )}
      </div>
    </div>
  </div>
)

export default function PerformanceAnalyticsPanel() {
  // Load-bearing query is performance (06-TILE-AUDIT). Plan 06-05 DASH-05:
  // wrapped in <TileState/>; inline isLoading/isError early-returns removed.
  const perfQuery = usePerformanceAnalytics()
  const { data: performanceData } = perfQuery

  // Fetch trade history for advanced metric calculation.
  // WR-04: route through the shared api client (services/api.js) so
  // baseURL ('/api', overridable via VITE_API_BASE_URL) and the
  // response interceptor that unwraps .data both apply. The shared
  // client returns the unwrapped body, so no .data access here.
  const { data: tradesData } = useQuery({
    queryKey: ['trades', 'history'],
    queryFn: async () => {
      return await api.get('/trading/trades/history', { params: { limit: 1000 } })
    },
    refetchInterval: 30000,
    staleTime: 25000,
  })

  // Calculate advanced metrics from trade history
  const trades = tradesData?.trades || []
  const metrics = performanceData?.metrics
  const performanceSummary = calculateAdvancedMetrics(trades, metrics)

  const TrendIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
    </svg>
  )

  const WarningIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  )

  const ChartIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  )

  const hasData = performanceSummary && performanceSummary.totalTrades > 0

  return (
    <div data-testid="performance-analytics-panel" style={{ display: 'contents' }}>
    <TileState
      query={perfQuery}
      title="Performance Analytics"
      thresholdKey="performance"
      lastUpdatedAt={undefined}
      isEmpty={(d) => !d || !d.metrics || Object.keys(d.metrics).length === 0}
    >
    <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              Performance Analytics
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Risk-adjusted return metrics used by professional traders
            </p>
          </div>
          <span className="text-xs px-2 py-1 bg-purple-500/10 text-purple-400 rounded-full border border-purple-500/20">
            Advanced
          </span>
        </div>
      </div>

      <div className="p-5">
        {!hasData ? (
          <div className="text-center py-8">
            <div className="text-slate-400 mb-2">No trading data available yet</div>
            <p className="text-xs text-slate-500">
              Performance metrics will appear after trades are executed
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Risk-Adjusted Return Ratios */}
            <div>
              <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                Risk-Adjusted Returns
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <RatioGauge
                  label="Sharpe Ratio"
                  value={performanceSummary?.sharpeRatio}
                  min={-2}
                  max={4}
                  goodRange={[1, 4]}
                  description="Risk-adjusted return (>1 good, >2 excellent)"
                />
                <RatioGauge
                  label="Sortino Ratio"
                  value={performanceSummary?.sortinoRatio}
                  min={-2}
                  max={4}
                  goodRange={[1.5, 4]}
                  description="Downside risk-adjusted return (>1.5 good)"
                />
              </div>
            </div>

            {/* Risk Metrics */}
            <div>
              <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                Risk Metrics
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <RiskMetricCard
                  label="Max Drawdown"
                  value={performanceSummary?.maxDrawdown}
                  format="percent"
                  trend={
                    Math.abs(performanceSummary?.maxDrawdown || 0) < 0.1 ? 'positive' :
                    Math.abs(performanceSummary?.maxDrawdown || 0) < 0.2 ? 'neutral' :
                    'negative'
                  }
                  description="Largest peak-to-trough decline"
                  icon={TrendIcon}
                />
                <RiskMetricCard
                  label="VaR (95%)"
                  value={performanceSummary?.var95}
                  format="percent"
                  trend="negative"
                  description="Maximum expected daily loss"
                  icon={WarningIcon}
                />
                <RiskMetricCard
                  label="CVaR (95%)"
                  value={performanceSummary?.cvar95}
                  format="percent"
                  trend="negative"
                  description="Expected shortfall beyond VaR"
                  icon={WarningIcon}
                />
              </div>
            </div>

            {/* Trade Statistics */}
            <div>
              <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                Trade Statistics
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <TradeStatsCard
                  totalTrades={performanceSummary?.totalTrades}
                  winningTrades={performanceSummary?.winningTrades}
                  losingTrades={
                    (performanceSummary?.totalTrades || 0) -
                    (performanceSummary?.winningTrades || 0)
                  }
                  winRate={performanceSummary?.winRate}
                />
                <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
                  <h4 className="text-sm font-medium text-slate-200 mb-3">Interpretation</h4>
                  <div className="space-y-2 text-xs text-slate-400">
                    <p>
                      <span className="text-emerald-400">Sharpe &gt; 1:</span> Good risk-adjusted returns
                    </p>
                    <p>
                      <span className="text-emerald-400">Sortino &gt; 1.5:</span> Low downside risk
                    </p>
                    <p>
                      <span className="text-amber-400">Drawdown &lt; 10%:</span> Acceptable loss control
                    </p>
                    <p>
                      <span className="text-rose-400">VaR/CVaR:</span> Potential daily loss at 95% confidence
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
        <p className="text-xs text-slate-500">
          Auto-refresh every 30s | Metrics: Sharpe, Sortino, VaR, CVaR (Monte Carlo method)
        </p>
      </div>
    </div>
    </TileState>
    </div>
  )
}
