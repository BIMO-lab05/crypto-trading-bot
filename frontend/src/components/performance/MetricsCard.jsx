/**
 * MetricsCard.jsx - KPI Display Component
 *
 * Purpose: Reusable card component for displaying key performance indicators
 * with proper formatting, color coding, and trend visualization.
 *
 * Features:
 * - Multiple display variants (default, compact, large)
 * - Color coding based on value thresholds
 * - Trend indicators (up/down arrows)
 * - Loading skeleton states
 * - Tooltips with descriptions
 * - Dark mode support
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React from 'react'
import PropTypes from 'prop-types'

// ============================================================================
// FORMATTING UTILITIES
// ============================================================================

/**
 * Format numeric value based on type
 *
 * @param {number} value - Value to format
 * @param {string} format - Format type
 * @param {Object} options - Additional formatting options
 * @returns {string} Formatted value
 */
function formatValue(value, format, options = {}) {
  if (value == null || isNaN(value)) return 'N/A'

  const { decimals = 2, prefix = '', suffix = '' } = options

  switch (format) {
    case 'currency':
      return `$${value.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}`

    case 'percent':
      return `${(value * 100).toFixed(decimals)}%`

    case 'percentRaw':
      // Value is already in percentage form
      return `${value.toFixed(decimals)}%`

    case 'ratio':
      return value.toFixed(decimals)

    case 'integer':
      return Math.round(value).toLocaleString('en-US')

    case 'decimal':
      return value.toFixed(decimals)

    default:
      return `${prefix}${value.toFixed(decimals)}${suffix}`
  }
}

/**
 * Get color class based on value and thresholds
 *
 * @param {number} value - Value to evaluate
 * @param {Object} thresholds - Threshold configuration
 * @returns {string} Tailwind color class
 */
function getValueColor(value, thresholds) {
  if (value == null) return 'text-slate-500'

  const { good, warning, bad, inverse = false } = thresholds || {}

  // Inverse means lower is better (e.g., drawdown)
  if (inverse) {
    if (bad != null && value >= bad) return 'text-rose-500 dark:text-rose-400'
    if (warning != null && value >= warning) return 'text-amber-500 dark:text-amber-400'
    if (good != null && value < good) return 'text-emerald-500 dark:text-emerald-400'
    return 'text-slate-200'
  }

  // Normal: higher is better
  if (good != null && value >= good) return 'text-emerald-500 dark:text-emerald-400'
  if (warning != null && value >= warning) return 'text-amber-500 dark:text-amber-400'
  if (bad != null && value < bad) return 'text-rose-500 dark:text-rose-400'
  return 'text-slate-200'
}

/**
 * Get background color class for card based on value status
 */
function getBackgroundColor(value, thresholds, variant) {
  if (variant !== 'highlighted' || value == null) {
    return 'bg-slate-800/50'
  }

  const { good, warning, bad, inverse = false } = thresholds || {}

  if (inverse) {
    if (bad != null && value >= bad) return 'bg-rose-900/30 border-rose-500/30'
    if (warning != null && value >= warning) return 'bg-amber-900/30 border-amber-500/30'
    if (good != null && value < good) return 'bg-emerald-900/30 border-emerald-500/30'
  } else {
    if (good != null && value >= good) return 'bg-emerald-900/30 border-emerald-500/30'
    if (warning != null && value >= warning) return 'bg-amber-900/30 border-amber-500/30'
    if (bad != null && value < bad) return 'bg-rose-900/30 border-rose-500/30'
  }

  return 'bg-slate-800/50'
}

// ============================================================================
// ICON COMPONENTS
// ============================================================================

/**
 * Trend arrow icon component
 */
const TrendArrow = ({ direction, className = '' }) => {
  if (direction === 'up') {
    return (
      <svg
        className={`w-4 h-4 ${className}`}
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
    )
  }

  if (direction === 'down') {
    return (
      <svg
        className={`w-4 h-4 ${className}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M19 14l-7 7m0 0l-7-7m7 7V3"
        />
      </svg>
    )
  }

  return (
    <svg
      className={`w-4 h-4 ${className}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14" />
    </svg>
  )
}

/**
 * Info icon for tooltips
 */
const InfoIcon = ({ className = '' }) => (
  <svg
    className={`w-4 h-4 ${className}`}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
)

// ============================================================================
// LOADING SKELETON
// ============================================================================

/**
 * Loading skeleton for MetricsCard
 */
const MetricsCardSkeleton = ({ variant = 'default' }) => {
  const sizeClasses = {
    compact: 'p-3',
    default: 'p-4',
    large: 'p-5',
  }

  return (
    <div
      className={`bg-slate-800/50 rounded-lg border border-slate-700/50 ${sizeClasses[variant]} animate-pulse`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="h-4 bg-slate-700 rounded w-1/3"></div>
        <div className="h-4 bg-slate-700 rounded w-4"></div>
      </div>
      <div className="h-8 bg-slate-700 rounded w-2/3 mb-2"></div>
      <div className="h-3 bg-slate-700 rounded w-1/2"></div>
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * MetricsCard - KPI Display Component
 *
 * @param {Object} props - Component props
 * @param {string} props.title - Metric title/label
 * @param {number} props.value - Metric value
 * @param {string} props.format - Value format type ('currency', 'percent', 'ratio', etc.)
 * @param {string} props.description - Metric description for tooltip
 * @param {Object} props.thresholds - Color threshold configuration
 * @param {string} props.trend - Trend direction ('up', 'down', 'neutral')
 * @param {number} props.change - Change value from previous period
 * @param {string} props.changeFormat - Format for change value
 * @param {string} props.variant - Display variant ('compact', 'default', 'large', 'highlighted')
 * @param {boolean} props.loading - Loading state
 * @param {React.ReactNode} props.icon - Optional icon component
 * @param {string} props.className - Additional CSS classes
 */
function MetricsCard({
  title,
  value,
  format = 'decimal',
  description,
  thresholds,
  trend,
  change,
  changeFormat = 'percent',
  variant = 'default',
  loading = false,
  icon,
  className = '',
  formatOptions = {},
}) {
  // Show skeleton if loading
  if (loading) {
    return <MetricsCardSkeleton variant={variant} />
  }

  // Determine styling based on variant
  const sizeClasses = {
    compact: {
      container: 'p-3',
      title: 'text-xs',
      value: 'text-lg',
      description: 'text-[10px]',
    },
    default: {
      container: 'p-4',
      title: 'text-sm',
      value: 'text-2xl',
      description: 'text-xs',
    },
    large: {
      container: 'p-5',
      title: 'text-base',
      value: 'text-3xl',
      description: 'text-sm',
    },
    highlighted: {
      container: 'p-4',
      title: 'text-sm',
      value: 'text-2xl',
      description: 'text-xs',
    },
  }

  const sizes = sizeClasses[variant] || sizeClasses.default
  const valueColor = getValueColor(value, thresholds)
  const bgColor = getBackgroundColor(value, thresholds, variant)

  // Determine trend direction if not explicitly provided
  const effectiveTrend = trend || (change > 0 ? 'up' : change < 0 ? 'down' : 'neutral')
  const trendColor =
    effectiveTrend === 'up'
      ? 'text-emerald-500'
      : effectiveTrend === 'down'
      ? 'text-rose-500'
      : 'text-slate-400'

  return (
    <div
      className={`
        ${bgColor}
        rounded-lg border border-slate-700/50
        ${sizes.container}
        transition-all duration-200
        hover:border-slate-600/50
        ${className}
      `}
    >
      {/* Header: Title and Icon */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {icon && <span className="text-slate-400">{icon}</span>}
          <h4 className={`font-medium text-slate-400 uppercase tracking-wide ${sizes.title}`}>
            {title}
          </h4>
        </div>

        {/* Info tooltip trigger */}
        {description && (
          <div className="group relative">
            <InfoIcon className="text-slate-500 hover:text-slate-300 cursor-help" />
            <div className="absolute right-0 top-6 z-10 hidden group-hover:block w-48 p-2 bg-slate-900 border border-slate-700 rounded-lg shadow-xl">
              <p className="text-xs text-slate-300">{description}</p>
            </div>
          </div>
        )}
      </div>

      {/* Main Value */}
      <div className="flex items-baseline gap-2 mb-1">
        <span className={`font-bold ${valueColor} ${sizes.value}`}>
          {formatValue(value, format, formatOptions)}
        </span>

        {/* Trend indicator */}
        {(trend || change != null) && (
          <div className={`flex items-center gap-0.5 ${trendColor}`}>
            <TrendArrow direction={effectiveTrend} className={trendColor} />
            {change != null && (
              <span className="text-xs font-medium">
                {formatValue(Math.abs(change), changeFormat, { decimals: 1 })}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Description/Subtext */}
      {description && variant !== 'compact' && (
        <p className={`text-slate-500 ${sizes.description} line-clamp-2`}>{description}</p>
      )}
    </div>
  )
}

// PropTypes for type checking
MetricsCard.propTypes = {
  title: PropTypes.string.isRequired,
  value: PropTypes.number,
  format: PropTypes.oneOf(['currency', 'percent', 'percentRaw', 'ratio', 'integer', 'decimal']),
  description: PropTypes.string,
  thresholds: PropTypes.shape({
    good: PropTypes.number,
    warning: PropTypes.number,
    bad: PropTypes.number,
    inverse: PropTypes.bool,
  }),
  trend: PropTypes.oneOf(['up', 'down', 'neutral']),
  change: PropTypes.number,
  changeFormat: PropTypes.string,
  variant: PropTypes.oneOf(['compact', 'default', 'large', 'highlighted']),
  loading: PropTypes.bool,
  icon: PropTypes.node,
  className: PropTypes.string,
  formatOptions: PropTypes.object,
}

// ============================================================================
// PRE-CONFIGURED METRIC CARDS
// ============================================================================

/**
 * SharpeRatioCard - Pre-configured card for Sharpe Ratio display
 */
export const SharpeRatioCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="Sharpe Ratio"
    value={value}
    format="ratio"
    description="Risk-adjusted return. Values > 1 are good, > 2 are excellent."
    thresholds={{ good: 2, warning: 1, bad: 0 }}
    loading={loading}
    {...props}
  />
)

/**
 * SortinoRatioCard - Pre-configured card for Sortino Ratio display
 */
export const SortinoRatioCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="Sortino Ratio"
    value={value}
    format="ratio"
    description="Downside risk-adjusted return. Values > 1.5 are good."
    thresholds={{ good: 1.5, warning: 1, bad: 0 }}
    loading={loading}
    {...props}
  />
)

/**
 * MaxDrawdownCard - Pre-configured card for Maximum Drawdown display
 */
export const MaxDrawdownCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="Max Drawdown"
    value={value}
    format="percentRaw"
    description="Largest peak-to-trough decline. Lower is better."
    thresholds={{ good: 5, warning: 10, bad: 20, inverse: true }}
    loading={loading}
    {...props}
  />
)

/**
 * WinRateCard - Pre-configured card for Win Rate display
 */
export const WinRateCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="Win Rate"
    value={value}
    format="percentRaw"
    description="Percentage of winning trades."
    thresholds={{ good: 55, warning: 45, bad: 40 }}
    loading={loading}
    {...props}
  />
)

/**
 * ProfitFactorCard - Pre-configured card for Profit Factor display
 */
export const ProfitFactorCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="Profit Factor"
    value={value}
    format="ratio"
    description="Gross profit / Gross loss. Values > 1.5 indicate profitability."
    thresholds={{ good: 1.5, warning: 1.2, bad: 1 }}
    loading={loading}
    {...props}
  />
)

/**
 * TotalPnLCard - Pre-configured card for Total P&L display
 */
export const TotalPnLCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="Total P&L"
    value={value}
    format="currency"
    description="Total realized profit/loss."
    thresholds={{ good: 0, bad: -100 }}
    loading={loading}
    {...props}
  />
)

/**
 * VaRCard - Pre-configured card for Value at Risk display
 */
export const VaRCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="VaR (95%)"
    value={value}
    format="currency"
    description="Maximum expected daily loss at 95% confidence."
    thresholds={{ good: 100, warning: 500, bad: 1000, inverse: true }}
    loading={loading}
    {...props}
  />
)

/**
 * CVaRCard - Pre-configured card for Conditional VaR display
 */
export const CVaRCard = ({ value, loading, ...props }) => (
  <MetricsCard
    title="CVaR (95%)"
    value={value}
    format="currency"
    description="Expected shortfall beyond VaR threshold."
    thresholds={{ good: 150, warning: 750, bad: 1500, inverse: true }}
    loading={loading}
    {...props}
  />
)

export default MetricsCard
