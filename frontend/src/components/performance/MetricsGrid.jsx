/**
 * MetricsGrid.jsx - Detailed Metrics Grid Component
 *
 * Purpose: Displays comprehensive performance metrics in a structured grid layout.
 * Includes Risk-Adjusted Metrics, Drawdown Analysis, Win/Loss Statistics, and Risk Metrics.
 *
 * Features:
 * - Categorized metric sections
 * - Expandable/collapsible sections
 * - Tooltips with metric explanations
 * - Color-coded values based on thresholds
 * - Loading skeleton states
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState } from 'react'
import PropTypes from 'prop-types'
import {
  formatCurrency,
  formatPnL,
  formatPercent,
  formatRatio,
  formatInteger,
} from '../../utils/formatters'
import { PAPER_DEFAULT_BALANCE } from '../../utils/balance'

// ============================================================================
// RISK THRESHOLDS
// ============================================================================

// Dollar risk thresholds expressed as fractions of the paper account
// (PAPER_DEFAULT_BALANCE) so they keep their meaning at any account size.
// VaR(95): good ≤ 1% of the account, warning at 5%, bad at 10%.
const VAR_THRESHOLDS = {
  good: 0.01 * PAPER_DEFAULT_BALANCE,
  warning: 0.05 * PAPER_DEFAULT_BALANCE,
  bad: 0.1 * PAPER_DEFAULT_BALANCE,
  inverse: true,
}

// CVaR (expected tail loss) runs deeper than VaR: 1.5% / 7.5% / 15%.
const CVAR_THRESHOLDS = {
  good: 0.015 * PAPER_DEFAULT_BALANCE,
  warning: 0.075 * PAPER_DEFAULT_BALANCE,
  bad: 0.15 * PAPER_DEFAULT_BALANCE,
  inverse: true,
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Get color class based on metric value and thresholds
 */
function getValueColor(value, thresholds = {}) {
  if (value == null) return 'text-slate-400'

  const { good, warning, bad, inverse = false } = thresholds

  if (inverse) {
    // Lower is better (e.g., drawdown)
    if (bad != null && value >= bad) return 'text-rose-400'
    if (warning != null && value >= warning) return 'text-amber-400'
    if (good != null && value < good) return 'text-emerald-400'
  } else {
    // Higher is better
    if (good != null && value >= good) return 'text-emerald-400'
    if (warning != null && value >= warning) return 'text-amber-400'
    if (bad != null && value < bad) return 'text-rose-400'
  }

  return 'text-slate-200'
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const MetricsGridSkeleton = () => (
  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-pulse">
    {[1, 2, 3, 4].map((i) => (
      <div key={i} className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5">
        <div className="h-5 bg-slate-700 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          {[1, 2, 3, 4].map((j) => (
            <div key={j} className="flex justify-between">
              <div className="h-4 bg-slate-700 rounded w-1/3"></div>
              <div className="h-4 bg-slate-700 rounded w-1/4"></div>
            </div>
          ))}
        </div>
      </div>
    ))}
  </div>
)

// ============================================================================
// METRIC ROW COMPONENT
// ============================================================================

/**
 * MetricRow - Single metric display row with label and value
 */
const MetricRow = ({
  label,
  value,
  format = 'number',
  formatOptions = {},
  thresholds,
  tooltip,
  highlight = false,
}) => {
  const [showTooltip, setShowTooltip] = useState(false)

  // Format value based on type
  let formattedValue
  switch (format) {
    case 'currency':
      formattedValue = formatCurrency(value, formatOptions)
      break
    case 'pnl':
      formattedValue = formatPnL(value, formatOptions.decimals)
      break
    case 'percent':
      formattedValue = formatPercent(value, { isRaw: true, ...formatOptions })
      break
    case 'ratio':
      formattedValue = formatRatio(value, formatOptions.decimals)
      break
    case 'integer':
      formattedValue = formatInteger(value)
      break
    default:
      formattedValue = value != null ? value.toString() : 'N/A'
  }

  const colorClass = getValueColor(value, thresholds)

  return (
    <div
      className={`flex items-center justify-between py-2 ${
        highlight ? 'bg-slate-700/30 -mx-3 px-3 rounded' : ''
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-400">{label}</span>
        {tooltip && (
          <div className="relative">
            <button
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              className="text-slate-500 hover:text-slate-300"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </button>
            {showTooltip && (
              <div className="absolute left-0 top-6 z-20 w-48 p-2 bg-slate-900 border border-slate-700 rounded-lg shadow-xl text-xs text-slate-300">
                {tooltip}
              </div>
            )}
          </div>
        )}
      </div>
      <span className={`text-sm font-semibold ${colorClass}`}>
        {formattedValue}
      </span>
    </div>
  )
}

// ============================================================================
// SECTION COMPONENT
// ============================================================================

/**
 * MetricSection - Collapsible section containing related metrics
 */
const MetricSection = ({
  title,
  icon,
  children,
  defaultExpanded = true,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Section Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-5 py-4 flex items-center justify-between bg-slate-800/50 hover:bg-slate-700/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          {icon && (
            <span className="text-slate-400">
              {icon}
            </span>
          )}
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wide">
            {title}
          </h3>
        </div>
        <svg
          className={`w-5 h-5 text-slate-400 transition-transform ${
            isExpanded ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Section Content */}
      {isExpanded && (
        <div className="px-5 py-3 divide-y divide-slate-700/50">
          {children}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * MetricsGrid - Comprehensive Metrics Display Grid
 *
 * @param {Object} props - Component props
 * @param {Object} props.metrics - Performance metrics data
 * @param {boolean} props.loading - Loading state
 * @param {string} props.className - Additional CSS classes
 */
function MetricsGrid({
  metrics = {},
  loading = false,
  className = '',
}) {
  if (loading) {
    return <MetricsGridSkeleton />
  }

  // Destructure metrics with fallbacks
  const {
    // Risk-adjusted metrics
    sharpeRatio,
    sortinoRatio,
    calmarRatio,
    informationRatio,

    // Drawdown metrics
    maxDrawdown,
    maxDrawdownPercent,
    avgDrawdown,
    currentDrawdown,
    maxDrawdownDuration,
    recoveryFactor,

    // Win/Loss statistics
    totalTrades,
    winningTrades,
    losingTrades,
    winRate,
    avgWin,
    avgLoss,
    largestWin,
    largestLoss,
    consecutiveWins,
    consecutiveLosses,

    // P&L metrics
    totalPnL,
    grossProfit,
    grossLoss,
    avgPnL,
    profitFactor,
    expectancy,

    // Risk metrics
    var95,
    cvar95,
    var99,
    stdDev,
    volatility,
    downsideDeviation,
  } = metrics

  return (
    <div className={`grid grid-cols-1 md:grid-cols-2 gap-6 ${className}`}>
      {/* Risk-Adjusted Metrics Section */}
      <MetricSection
        title="Risk-Adjusted Metrics"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        }
      >
        <MetricRow
          label="Sharpe Ratio"
          value={sharpeRatio}
          format="ratio"
          thresholds={{ good: 2, warning: 1, bad: 0 }}
          tooltip="Risk-adjusted return. Values > 1 are good, > 2 are excellent."
          highlight
        />
        <MetricRow
          label="Sortino Ratio"
          value={sortinoRatio}
          format="ratio"
          thresholds={{ good: 1.5, warning: 1, bad: 0 }}
          tooltip="Like Sharpe but only considers downside volatility."
        />
        <MetricRow
          label="Calmar Ratio"
          value={calmarRatio}
          format="ratio"
          thresholds={{ good: 1, warning: 0.5, bad: 0 }}
          tooltip="Annual return divided by max drawdown."
        />
        <MetricRow
          label="Profit Factor"
          value={profitFactor}
          format="ratio"
          thresholds={{ good: 1.5, warning: 1.2, bad: 1 }}
          tooltip="Gross profit / Gross loss. Values > 1.5 indicate profitability."
        />
        <MetricRow
          label="Expectancy"
          value={expectancy}
          format="currency"
          thresholds={{ good: 0 }}
          tooltip="Expected average profit per trade."
        />
        <MetricRow
          label="Recovery Factor"
          value={recoveryFactor}
          format="ratio"
          thresholds={{ good: 2, warning: 1, bad: 0.5 }}
          tooltip="Net profit / Max drawdown. Higher is better."
        />
      </MetricSection>

      {/* Drawdown Analysis Section */}
      <MetricSection
        title="Drawdown Analysis"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
          </svg>
        }
      >
        <MetricRow
          label="Max Drawdown"
          value={maxDrawdownPercent}
          format="percent"
          formatOptions={{ decimals: 2 }}
          thresholds={{ good: 5, warning: 10, bad: 20, inverse: true }}
          tooltip="Largest peak-to-trough decline. Lower is better."
          highlight
        />
        <MetricRow
          label="Max DD Value"
          value={maxDrawdown}
          format="currency"
          tooltip="Maximum drawdown in absolute terms."
        />
        <MetricRow
          label="Current Drawdown"
          value={currentDrawdown}
          format="percent"
          formatOptions={{ decimals: 2 }}
          thresholds={{ good: 2, warning: 5, bad: 10, inverse: true }}
          tooltip="Current distance from peak equity."
        />
        <MetricRow
          label="Average Drawdown"
          value={avgDrawdown}
          format="percent"
          formatOptions={{ decimals: 2 }}
          tooltip="Average drawdown across all periods."
        />
        <MetricRow
          label="Max DD Duration"
          value={maxDrawdownDuration}
          format="integer"
          tooltip="Longest drawdown period in days."
        />
      </MetricSection>

      {/* Win/Loss Statistics Section */}
      <MetricSection
        title="Win/Loss Statistics"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      >
        <MetricRow
          label="Win Rate"
          value={winRate}
          format="percent"
          thresholds={{ good: 55, warning: 45, bad: 40 }}
          tooltip="Percentage of winning trades."
          highlight
        />
        <MetricRow
          label="Total Trades"
          value={totalTrades}
          format="integer"
          tooltip="Total number of closed trades."
        />
        <MetricRow
          label="Winning Trades"
          value={winningTrades}
          format="integer"
          tooltip="Number of profitable trades."
        />
        <MetricRow
          label="Losing Trades"
          value={losingTrades}
          format="integer"
          tooltip="Number of losing trades."
        />
        <MetricRow
          label="Average Win"
          value={avgWin}
          format="currency"
          thresholds={{ good: 0 }}
          tooltip="Average profit on winning trades."
        />
        <MetricRow
          label="Average Loss"
          value={avgLoss}
          format="currency"
          tooltip="Average loss on losing trades (shown as positive)."
        />
        <MetricRow
          label="Largest Win"
          value={largestWin}
          format="currency"
          tooltip="Best single trade."
        />
        <MetricRow
          label="Largest Loss"
          value={largestLoss}
          format="currency"
          tooltip="Worst single trade."
        />
        <MetricRow
          label="Max Consec. Wins"
          value={consecutiveWins}
          format="integer"
          tooltip="Maximum consecutive winning trades."
        />
        <MetricRow
          label="Max Consec. Losses"
          value={consecutiveLosses}
          format="integer"
          thresholds={{ good: 3, warning: 5, bad: 7, inverse: true }}
          tooltip="Maximum consecutive losing trades."
        />
      </MetricSection>

      {/* Risk Metrics Section */}
      <MetricSection
        title="Risk Metrics"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        }
      >
        <MetricRow
          label="VaR (95%)"
          value={var95}
          format="currency"
          thresholds={VAR_THRESHOLDS}
          tooltip="Maximum expected daily loss at 95% confidence."
          highlight
        />
        <MetricRow
          label="CVaR (95%)"
          value={cvar95}
          format="currency"
          thresholds={CVAR_THRESHOLDS}
          tooltip="Expected loss when VaR is exceeded (tail risk)."
        />
        <MetricRow
          label="VaR (99%)"
          value={var99}
          format="currency"
          tooltip="Maximum expected daily loss at 99% confidence."
        />
        <MetricRow
          label="Std Deviation"
          value={stdDev}
          format="currency"
          tooltip="Standard deviation of returns."
        />
        <MetricRow
          label="Volatility"
          value={volatility}
          format="percent"
          tooltip="Annualized return volatility."
        />
        <MetricRow
          label="Downside Dev"
          value={downsideDeviation}
          format="currency"
          tooltip="Volatility of negative returns only."
        />
      </MetricSection>

      {/* P&L Summary Section */}
      <MetricSection
        title="P&L Summary"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
        className="md:col-span-2"
        defaultExpanded
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-slate-900/50 rounded-lg p-4 text-center">
            <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Total P&L</p>
            <p className={`text-xl font-bold ${(totalPnL || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {formatPnL(totalPnL)}
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-4 text-center">
            <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Gross Profit</p>
            <p className="text-xl font-bold text-emerald-400">
              {formatCurrency(grossProfit)}
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-4 text-center">
            <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Gross Loss</p>
            <p className="text-xl font-bold text-rose-400">
              {formatCurrency(grossLoss)}
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-4 text-center">
            <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Avg P&L / Trade</p>
            <p className={`text-xl font-bold ${(avgPnL || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {formatPnL(avgPnL)}
            </p>
          </div>
        </div>
      </MetricSection>
    </div>
  )
}

// PropTypes
MetricsGrid.propTypes = {
  metrics: PropTypes.shape({
    sharpeRatio: PropTypes.number,
    sortinoRatio: PropTypes.number,
    calmarRatio: PropTypes.number,
    informationRatio: PropTypes.number,
    maxDrawdown: PropTypes.number,
    maxDrawdownPercent: PropTypes.number,
    avgDrawdown: PropTypes.number,
    currentDrawdown: PropTypes.number,
    maxDrawdownDuration: PropTypes.number,
    recoveryFactor: PropTypes.number,
    totalTrades: PropTypes.number,
    winningTrades: PropTypes.number,
    losingTrades: PropTypes.number,
    winRate: PropTypes.number,
    avgWin: PropTypes.number,
    avgLoss: PropTypes.number,
    largestWin: PropTypes.number,
    largestLoss: PropTypes.number,
    consecutiveWins: PropTypes.number,
    consecutiveLosses: PropTypes.number,
    totalPnL: PropTypes.number,
    grossProfit: PropTypes.number,
    grossLoss: PropTypes.number,
    avgPnL: PropTypes.number,
    profitFactor: PropTypes.number,
    expectancy: PropTypes.number,
    var95: PropTypes.number,
    cvar95: PropTypes.number,
    var99: PropTypes.number,
    stdDev: PropTypes.number,
    volatility: PropTypes.number,
    downsideDeviation: PropTypes.number,
  }),
  loading: PropTypes.bool,
  className: PropTypes.string,
}

export default MetricsGrid
