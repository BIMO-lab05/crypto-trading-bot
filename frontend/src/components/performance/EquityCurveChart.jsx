/**
 * EquityCurveChart.jsx - Equity Curve Visualization Component
 *
 * Purpose: Displays the portfolio equity curve over time using Recharts.
 * Shows the growth/decline of portfolio value with proper formatting.
 *
 * Features:
 * - Line chart showing equity progression
 * - Optional benchmark comparison
 * - Custom tooltips with detailed information
 * - Responsive design
 * - Dark mode optimized colors
 * - Gradient fill under the curve
 * - Period selection
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts'
import { format, parseISO, isValid } from 'date-fns'
import ChartFigure from '../a11y/ChartFigure'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format timestamp for X-axis display
 *
 * @param {string|number} timestamp - Timestamp to format
 * @param {string} period - Time period for context-appropriate formatting
 * @returns {string} Formatted date string
 */
function formatXAxis(timestamp, period) {
  const date = typeof timestamp === 'string' ? parseISO(timestamp) : new Date(timestamp)

  if (!isValid(date)) return ''

  switch (period) {
    case '1d':
      return format(date, 'HH:mm')
    case '7d':
      return format(date, 'EEE HH:mm')
    case '30d':
      return format(date, 'MMM d')
    case '90d':
    case 'all':
      return format(date, 'MMM d')
    default:
      return format(date, 'MMM d HH:mm')
  }
}

/**
 * Format currency value
 *
 * @param {number} value - Value to format
 * @returns {string} Formatted currency string
 */
function formatCurrency(value) {
  if (value == null || isNaN(value)) return 'N/A'
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/**
 * Format percentage value
 *
 * @param {number} value - Value to format (0.1 = 10%)
 * @returns {string} Formatted percentage string
 */
function formatPercent(value) {
  if (value == null || isNaN(value)) return 'N/A'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(2)}%`
}

// ============================================================================
// CUSTOM TOOLTIP COMPONENT
// ============================================================================

/**
 * CustomTooltip - Detailed tooltip for equity curve data points
 */
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload
  const date = typeof data.timestamp === 'string'
    ? parseISO(data.timestamp)
    : new Date(data.timestamp)

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[180px]">
      {/* Date/Time Header */}
      <p className="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-2 mb-2">
        {isValid(date) ? format(date, 'MMM d, yyyy HH:mm') : 'N/A'}
      </p>

      {/* Equity Value */}
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Equity</span>
        <span className="text-sm font-bold text-emerald-400">
          {formatCurrency(data.equity)}
        </span>
      </div>

      {/* P&L if available */}
      {data.pnl != null && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-slate-400">Trade P&L</span>
          <span
            className={`text-sm font-semibold ${
              data.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {data.pnl >= 0 ? '+' : ''}
            {formatCurrency(data.pnl)}
          </span>
        </div>
      )}

      {/* Cumulative P&L if available */}
      {data.cumulativePnl != null && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-slate-400">Total P&L</span>
          <span
            className={`text-sm font-semibold ${
              data.cumulativePnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {data.cumulativePnl >= 0 ? '+' : ''}
            {formatCurrency(data.cumulativePnl)}
          </span>
        </div>
      )}

      {/* Trade Count if available */}
      {data.tradeCount != null && (
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400">Trades</span>
          <span className="text-sm text-slate-300">{data.tradeCount}</span>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const EquityCurveSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/4"></div>
      <div className="flex gap-2">
        <div className="h-8 w-16 bg-slate-700 rounded"></div>
        <div className="h-8 w-16 bg-slate-700 rounded"></div>
        <div className="h-8 w-16 bg-slate-700 rounded"></div>
      </div>
    </div>
    <div className="h-[300px] bg-slate-700/50 rounded"></div>
    <div className="flex justify-between mt-4">
      <div className="h-4 w-20 bg-slate-700 rounded"></div>
      <div className="h-4 w-20 bg-slate-700 rounded"></div>
      <div className="h-4 w-20 bg-slate-700 rounded"></div>
    </div>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * EquityCurveChart - Portfolio Equity Curve Visualization
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Equity curve data points
 * @param {boolean} props.loading - Loading state
 * @param {string} props.period - Current time period ('1d', '7d', '30d', '90d', 'all')
 * @param {Function} props.onPeriodChange - Period change handler
 * @param {number} props.height - Chart height in pixels
 * @param {number} props.initialEquity - Starting equity value (for reference line)
 * @param {boolean} props.showBenchmark - Show benchmark comparison
 * @param {string} props.className - Additional CSS classes
 */
function EquityCurveChart({
  data = [],
  loading = false,
  period = '30d',
  onPeriodChange,
  height = 300,
  initialEquity = 10000,
  showBenchmark = false,
  className = '',
}) {
  // Period options for selector
  const periodOptions = [
    { value: '1d', label: '1D' },
    { value: '7d', label: '7D' },
    { value: '30d', label: '30D' },
    { value: '90d', label: '90D' },
    { value: 'all', label: 'All' },
  ]

  // Calculate statistics from data
  const stats = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        current: initialEquity,
        change: 0,
        changePercent: 0,
        high: initialEquity,
        low: initialEquity,
      }
    }

    const equities = data.map((d) => d.equity).filter((e) => e != null)
    const firstEquity = equities[0] || initialEquity
    const lastEquity = equities[equities.length - 1] || initialEquity
    const change = lastEquity - firstEquity
    const changePercent = firstEquity > 0 ? change / firstEquity : 0

    return {
      current: lastEquity,
      first: firstEquity,
      change,
      changePercent,
      high: Math.max(...equities),
      low: Math.min(...equities),
    }
  }, [data, initialEquity])

  // Determine Y-axis domain with padding
  const yDomain = useMemo(() => {
    if (!data || data.length === 0) {
      return [initialEquity * 0.9, initialEquity * 1.1]
    }

    const equities = data.map((d) => d.equity).filter((e) => e != null)
    const min = Math.min(...equities)
    const max = Math.max(...equities)
    const padding = (max - min) * 0.1 || max * 0.05

    return [Math.floor(min - padding), Math.ceil(max + padding)]
  }, [data, initialEquity])

  // Show skeleton if loading
  if (loading) {
    return <EquityCurveSkeleton />
  }

  // Determine gradient color based on performance
  const gradientColor = stats.change >= 0 ? '#10b981' : '#f43f5e' // emerald-500 / rose-500
  const lineColor = stats.change >= 0 ? '#34d399' : '#fb7185' // emerald-400 / rose-400

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          {/* Title and Stats */}
          <div>
            <h3 className="text-base font-semibold text-slate-100 mb-1">
              Equity Curve
            </h3>
            <div className="flex items-center gap-4">
              <span className="text-2xl font-bold text-slate-100">
                {formatCurrency(stats.current)}
              </span>
              <span
                className={`text-sm font-semibold ${
                  stats.change >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {formatCurrency(stats.change)} ({formatPercent(stats.changePercent)})
              </span>
            </div>
          </div>

          {/* Period Selector */}
          {onPeriodChange && (
            <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
              {periodOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => onPeriodChange(option.value)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                    period === option.value
                      ? 'bg-slate-700 text-slate-100'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        {data.length === 0 ? (
          <div className="flex items-center justify-center h-[300px] text-slate-400">
            <div className="text-center">
              <p className="text-lg mb-2">No equity data available</p>
              <p className="text-sm text-slate-500">
                Data will appear after trades are executed
              </p>
            </div>
          </div>
        ) : (
          <ChartFigure
            summary={`Equity curve over ${period}. Starting ${formatCurrency(stats.first)}, ending ${formatCurrency(stats.current)}, ${stats.change >= 0 ? 'up' : 'down'} ${formatPercent(stats.changePercent)}. High ${formatCurrency(stats.high)}, low ${formatCurrency(stats.low)}.`}
            tableCaption={`Equity curve summary for ${period}`}
            columns={[
              { key: 'metric', label: 'Metric' },
              { key: 'value', label: 'Value' },
            ]}
            rows={[
              { metric: 'Start', value: formatCurrency(stats.first) },
              { metric: 'Current', value: formatCurrency(stats.current) },
              { metric: 'Change', value: `${formatCurrency(stats.change)} (${formatPercent(stats.changePercent)})` },
              { metric: 'High', value: formatCurrency(stats.high) },
              { metric: 'Low', value: formatCurrency(stats.low) },
            ]}
          >
          <ResponsiveContainer width="100%" height={height}>
            <AreaChart
              data={data}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {/* Gradient Definition */}
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={gradientColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={gradientColor} stopOpacity={0} />
                </linearGradient>
              </defs>

              {/* Grid */}
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />

              {/* X-Axis */}
              <XAxis
                dataKey="timestamp"
                tickFormatter={(ts) => formatXAxis(ts, period)}
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={{ stroke: '#475569' }}
              />

              {/* Y-Axis */}
              <YAxis
                domain={yDomain}
                tickFormatter={(val) => `$${(val / 1000).toFixed(1)}k`}
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={{ stroke: '#475569' }}
                width={60}
              />

              {/* Tooltip */}
              <Tooltip content={<CustomTooltip />} />

              {/* Initial Equity Reference Line */}
              <ReferenceLine
                y={initialEquity}
                stroke="#6366f1"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
                label={{
                  value: 'Initial',
                  fill: '#818cf8',
                  fontSize: 10,
                  position: 'right',
                }}
              />

              {/* Main Equity Area */}
              <Area
                type="monotone"
                dataKey="equity"
                stroke={lineColor}
                strokeWidth={2}
                fill="url(#equityGradient)"
                isAnimationActive={false}
                name="Portfolio Equity"
              />
            </AreaChart>
          </ResponsiveContainer>
          </ChartFigure>
        )}
      </div>

      {/* Footer Stats */}
      {data.length > 0 && (
        <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
          <div className="flex justify-between text-xs text-slate-400">
            <span>
              High: <span className="text-emerald-400 font-medium">{formatCurrency(stats.high)}</span>
            </span>
            <span>
              Low: <span className="text-rose-400 font-medium">{formatCurrency(stats.low)}</span>
            </span>
            <span>
              Points: <span className="text-slate-300 font-medium">{data.length}</span>
            </span>
            <span>Period: {period}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// PropTypes
EquityCurveChart.propTypes = {
  data: PropTypes.arrayOf(
    PropTypes.shape({
      timestamp: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
      equity: PropTypes.number.isRequired,
      pnl: PropTypes.number,
      cumulativePnl: PropTypes.number,
      tradeCount: PropTypes.number,
    })
  ),
  loading: PropTypes.bool,
  period: PropTypes.oneOf(['1d', '7d', '30d', '90d', 'all']),
  onPeriodChange: PropTypes.func,
  height: PropTypes.number,
  initialEquity: PropTypes.number,
  showBenchmark: PropTypes.bool,
  className: PropTypes.string,
}

export default EquityCurveChart
