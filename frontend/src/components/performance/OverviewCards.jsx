/**
 * OverviewCards.jsx - Performance Overview Cards Component
 *
 * Purpose: Displays the main performance KPIs in a visually prominent card layout.
 * Shows Total P&L, Win Rate, Sharpe Ratio, Active Positions, and period comparisons.
 *
 * Features:
 * - Large, prominent metric display
 * - Period-over-period comparison
 * - Trend indicators with animations
 * - Win rate gauge visualization
 * - Loading skeleton states
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import { formatCurrency, formatPnL, formatPercent, formatRatio } from '../../utils/formatters'

// ============================================================================
// LOADING SKELETON
// ============================================================================

/**
 * Loading skeleton for overview cards
 */
const OverviewCardsSkeleton = () => (
  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 animate-pulse">
    {[1, 2, 3, 4, 5, 6].map((i) => (
      <div key={i} className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
        <div className="h-4 bg-slate-700 rounded w-2/3 mb-3"></div>
        <div className="h-8 bg-slate-700 rounded w-1/2 mb-2"></div>
        <div className="h-3 bg-slate-700 rounded w-1/3"></div>
      </div>
    ))}
  </div>
)

// ============================================================================
// TREND INDICATOR COMPONENT
// ============================================================================

/**
 * TrendIndicator - Shows up/down arrow with percentage change
 */
const TrendIndicator = ({ value, format = 'percent' }) => {
  if (value == null) return null

  const isPositive = value > 0
  const isNeutral = value === 0

  let formattedValue
  if (format === 'percent') {
    formattedValue = `${isPositive ? '+' : ''}${(value * 100).toFixed(1)}%`
  } else if (format === 'currency') {
    formattedValue = formatPnL(value)
  } else {
    formattedValue = `${isPositive ? '+' : ''}${value.toFixed(2)}`
  }

  return (
    <div className={`flex items-center gap-1 text-sm ${
      isPositive ? 'text-emerald-400' :
      isNeutral ? 'text-slate-400' :
      'text-rose-400'
    }`}>
      {!isNeutral && (
        <svg
          className={`w-4 h-4 ${isPositive ? '' : 'rotate-180'}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 10l7-7m0 0l7 7m-7-7v18"
          />
        </svg>
      )}
      <span className="font-medium">{formattedValue}</span>
    </div>
  )
}

// ============================================================================
// WIN RATE GAUGE COMPONENT
// ============================================================================

/**
 * WinRateGauge - Circular progress indicator for win rate
 */
const WinRateGauge = ({ value, size = 60 }) => {
  const percentage = Math.min(100, Math.max(0, value || 0))
  const strokeWidth = 6
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percentage / 100) * circumference

  // Determine color based on win rate
  const getColor = () => {
    if (percentage >= 60) return '#10b981' // emerald-500
    if (percentage >= 50) return '#f59e0b' // amber-500
    return '#f43f5e' // rose-500
  }

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#334155"
          strokeWidth={strokeWidth}
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={getColor()}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-500 ease-out"
        />
      </svg>
      {/* Center text */}
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-sm font-bold text-slate-100">
          {percentage.toFixed(0)}%
        </span>
      </div>
    </div>
  )
}

// ============================================================================
// INDIVIDUAL CARD COMPONENTS
// ============================================================================

/**
 * TotalPnLCard - Large P&L display card
 */
const TotalPnLCard = ({ value, change, loading }) => {
  if (loading) {
    return (
      <div className="col-span-2 bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-1/3 mb-4"></div>
        <div className="h-10 bg-slate-700 rounded w-2/3 mb-2"></div>
        <div className="h-4 bg-slate-700 rounded w-1/4"></div>
      </div>
    )
  }

  const isPositive = (value || 0) >= 0

  return (
    <div className={`col-span-2 rounded-xl p-5 border transition-all duration-200 ${
      isPositive
        ? 'bg-emerald-500/10 border-emerald-500/30 hover:bg-emerald-500/15'
        : 'bg-rose-500/10 border-rose-500/30 hover:bg-rose-500/15'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wide">
          Total P&L
        </h3>
        {change != null && (
          <TrendIndicator value={change} format="percent" />
        )}
      </div>
      <p className={`text-3xl font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
        {formatPnL(value)}
      </p>
      <p className="text-xs text-slate-500 mt-2">
        Realized profit/loss for selected period
      </p>
    </div>
  )
}

/**
 * WinRateCard - Win rate with gauge visualization
 */
const WinRateCard = ({ value, totalTrades, loading }) => {
  if (loading) {
    return (
      <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-1/2 mb-4"></div>
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-slate-700 rounded-full"></div>
          <div className="h-6 bg-slate-700 rounded w-1/3"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-3">
        Win Rate
      </h3>
      <div className="flex items-center gap-4">
        <WinRateGauge value={value} />
        <div>
          <p className="text-lg font-semibold text-slate-100">
            {formatPercent(value, { isRaw: true, decimals: 1 })}
          </p>
          {totalTrades != null && (
            <p className="text-xs text-slate-500">
              {totalTrades} trades
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * SharpeCard - Sharpe ratio display
 */
const SharpeCard = ({ value, change, loading }) => {
  if (loading) {
    return (
      <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-2/3 mb-4"></div>
        <div className="h-8 bg-slate-700 rounded w-1/2 mb-2"></div>
        <div className="h-3 bg-slate-700 rounded w-1/3"></div>
      </div>
    )
  }

  // Color based on Sharpe value
  const getColor = () => {
    if (value == null) return 'text-slate-400'
    if (value >= 2) return 'text-emerald-400'
    if (value >= 1) return 'text-green-400'
    if (value >= 0) return 'text-amber-400'
    return 'text-rose-400'
  }

  const getQuality = () => {
    if (value == null) return 'N/A'
    if (value >= 2) return 'Excellent'
    if (value >= 1) return 'Good'
    if (value >= 0.5) return 'Acceptable'
    if (value >= 0) return 'Low'
    return 'Poor'
  }

  return (
    <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wide">
          Sharpe Ratio
        </h3>
        {change != null && (
          <TrendIndicator value={change} format="number" />
        )}
      </div>
      <p className={`text-2xl font-bold ${getColor()}`}>
        {formatRatio(value)}
      </p>
      <p className="text-xs text-slate-500 mt-1">
        {getQuality()} risk-adjusted returns
      </p>
    </div>
  )
}

/**
 * ActivePositionsCard - Current open positions count
 */
const ActivePositionsCard = ({ count, totalValue, loading }) => {
  if (loading) {
    return (
      <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-2/3 mb-4"></div>
        <div className="h-8 bg-slate-700 rounded w-1/3 mb-2"></div>
        <div className="h-3 bg-slate-700 rounded w-1/2"></div>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-2">
        Active Positions
      </h3>
      <p className="text-2xl font-bold text-slate-100">
        {count || 0}
      </p>
      {totalValue != null && (
        <p className="text-xs text-slate-500 mt-1">
          Total value: {formatCurrency(totalValue)}
        </p>
      )}
    </div>
  )
}

/**
 * TodayPnLCard - Today's P&L
 */
const TodayPnLCard = ({ value, tradeCount, loading }) => {
  if (loading) {
    return (
      <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-1/2 mb-4"></div>
        <div className="h-8 bg-slate-700 rounded w-2/3 mb-2"></div>
        <div className="h-3 bg-slate-700 rounded w-1/3"></div>
      </div>
    )
  }

  const isPositive = (value || 0) >= 0

  return (
    <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-2">
        Today&apos;s P&L
      </h3>
      <p className={`text-2xl font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
        {formatPnL(value)}
      </p>
      {tradeCount != null && (
        <p className="text-xs text-slate-500 mt-1">
          {tradeCount} trades today
        </p>
      )}
    </div>
  )
}

/**
 * WeekPnLCard - This week's P&L
 */
const WeekPnLCard = ({ value, change, loading }) => {
  if (loading) {
    return (
      <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-2/3 mb-4"></div>
        <div className="h-8 bg-slate-700 rounded w-1/2 mb-2"></div>
        <div className="h-3 bg-slate-700 rounded w-1/3"></div>
      </div>
    )
  }

  const isPositive = (value || 0) >= 0

  return (
    <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wide">
          This Week
        </h3>
        {change != null && (
          <TrendIndicator value={change} format="percent" />
        )}
      </div>
      <p className={`text-2xl font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
        {formatPnL(value)}
      </p>
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * OverviewCards - Main Performance Overview Component
 *
 * @param {Object} props - Component props
 * @param {Object} props.metrics - Performance metrics data
 * @param {boolean} props.loading - Loading state
 * @param {string} props.className - Additional CSS classes
 */
function OverviewCards({
  metrics: metricsProp = {},
  loading = false,
  className = '',
}) {
  // A default parameter only applies when the prop is `undefined`, so an
  // explicit `metrics={null}` -- which the performance API returns while no
  // data has been recorded yet -- fell through to the destructure below and
  // crashed the whole dashboard with "Cannot read properties of null".
  // Coalesce instead of relying on the default.
  const metrics = metricsProp ?? {}

  // Extract metrics with fallbacks
  const {
    totalPnL = 0,
    totalPnLChange = null,
    winRate = 0,
    totalTrades = 0,
    sharpeRatio = null,
    sharpeChange = null,
    activePositions = 0,
    activePositionsValue = null,
    todayPnL = 0,
    todayTrades = 0,
    weekPnL = 0,
    weekPnLChange = null,
  } = metrics

  if (loading) {
    return <OverviewCardsSkeleton />
  }

  return (
    <div className={`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 ${className}`}>
      {/* Total P&L - Spans 2 columns */}
      <TotalPnLCard
        value={totalPnL}
        change={totalPnLChange}
        loading={loading}
      />

      {/* Win Rate */}
      <WinRateCard
        value={winRate}
        totalTrades={totalTrades}
        loading={loading}
      />

      {/* Sharpe Ratio */}
      <SharpeCard
        value={sharpeRatio}
        change={sharpeChange}
        loading={loading}
      />

      {/* Active Positions */}
      <ActivePositionsCard
        count={activePositions}
        totalValue={activePositionsValue}
        loading={loading}
      />

      {/* Today's P&L */}
      <TodayPnLCard
        value={todayPnL}
        tradeCount={todayTrades}
        loading={loading}
      />
    </div>
  )
}

// PropTypes
OverviewCards.propTypes = {
  metrics: PropTypes.shape({
    totalPnL: PropTypes.number,
    totalPnLChange: PropTypes.number,
    winRate: PropTypes.number,
    totalTrades: PropTypes.number,
    sharpeRatio: PropTypes.number,
    sharpeChange: PropTypes.number,
    activePositions: PropTypes.number,
    activePositionsValue: PropTypes.number,
    todayPnL: PropTypes.number,
    todayTrades: PropTypes.number,
    weekPnL: PropTypes.number,
    weekPnLChange: PropTypes.number,
  }),
  loading: PropTypes.bool,
  className: PropTypes.string,
}

export default OverviewCards
