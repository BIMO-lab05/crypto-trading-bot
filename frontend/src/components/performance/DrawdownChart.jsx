/**
 * DrawdownChart.jsx - Drawdown Visualization Component
 *
 * Purpose: Displays drawdown over time as an inverted area chart.
 * Drawdown represents the peak-to-trough decline in portfolio value.
 *
 * Features:
 * - Area chart showing drawdown magnitude
 * - Current and maximum drawdown indicators
 * - Underwater equity visualization
 * - Custom tooltips with recovery information
 * - Dark mode optimized
 * - Responsive design
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
} from 'recharts'
import { format, parseISO, isValid, differenceInDays } from 'date-fns'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format timestamp for X-axis
 */
function formatXAxis(timestamp, period) {
  const date = typeof timestamp === 'string' ? parseISO(timestamp) : new Date(timestamp)
  if (!isValid(date)) return ''

  switch (period) {
    case '1d':
      return format(date, 'HH:mm')
    case '7d':
      return format(date, 'EEE')
    case '30d':
    case '90d':
    case 'all':
      return format(date, 'MMM d')
    default:
      return format(date, 'MMM d')
  }
}

/**
 * Get severity color based on drawdown percentage
 */
function getSeverityColor(drawdownPercent) {
  if (drawdownPercent >= 20) return { stroke: '#dc2626', fill: '#dc2626' } // red-600
  if (drawdownPercent >= 10) return { stroke: '#ea580c', fill: '#ea580c' } // orange-600
  if (drawdownPercent >= 5) return { stroke: '#d97706', fill: '#d97706' } // amber-600
  return { stroke: '#f59e0b', fill: '#f59e0b' } // amber-500
}

// ============================================================================
// CUSTOM TOOLTIP
// ============================================================================

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload
  const date = typeof data.timestamp === 'string'
    ? parseISO(data.timestamp)
    : new Date(data.timestamp)

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[200px]">
      <p className="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-2 mb-2">
        {isValid(date) ? format(date, 'MMM d, yyyy HH:mm') : 'N/A'}
      </p>

      {/* Drawdown Percentage */}
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Drawdown</span>
        <span className="text-sm font-bold text-rose-400">
          -{data.drawdownPercent?.toFixed(2) || 0}%
        </span>
      </div>

      {/* Drawdown Value */}
      {data.drawdownValue != null && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-slate-400">Value</span>
          <span className="text-sm font-semibold text-rose-400">
            ${Math.abs(data.drawdownValue).toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      )}

      {/* Current Equity */}
      {data.equity != null && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-slate-400">Equity</span>
          <span className="text-sm text-slate-300">
            ${data.equity.toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      )}

      {/* Peak Value */}
      {data.peak != null && (
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400">Peak</span>
          <span className="text-sm text-emerald-400">
            ${data.peak.toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const DrawdownChartSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/4"></div>
      <div className="h-6 bg-slate-700 rounded w-1/6"></div>
    </div>
    <div className="h-[250px] bg-slate-700/50 rounded"></div>
  </div>
)

// ============================================================================
// STATS CARD COMPONENT
// ============================================================================

const DrawdownStat = ({ label, value, color = 'text-slate-100' }) => (
  <div className="bg-slate-900/50 rounded-lg px-3 py-2">
    <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">{label}</p>
    <p className={`text-sm font-bold ${color}`}>{value}</p>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * DrawdownChart - Drawdown Visualization Component
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Drawdown series data
 * @param {boolean} props.loading - Loading state
 * @param {string} props.period - Time period
 * @param {number} props.height - Chart height
 * @param {string} props.className - Additional CSS classes
 */
function DrawdownChart({
  data = [],
  loading = false,
  period = '30d',
  height = 250,
  className = '',
}) {
  // Calculate statistics
  const stats = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        current: 0,
        max: 0,
        maxDate: null,
        avgDrawdown: 0,
        timeInDrawdown: 0,
        recoveryTime: null,
      }
    }

    const drawdowns = data.map((d) => d.drawdownPercent || 0)
    const currentDD = drawdowns[drawdowns.length - 1] || 0
    const maxDD = Math.max(...drawdowns)
    const maxDDIndex = drawdowns.indexOf(maxDD)
    const maxDDDate = data[maxDDIndex]?.timestamp

    // Calculate average drawdown (excluding zero drawdowns)
    const nonZeroDrawdowns = drawdowns.filter((d) => d > 0)
    const avgDD = nonZeroDrawdowns.length > 0
      ? nonZeroDrawdowns.reduce((sum, d) => sum + d, 0) / nonZeroDrawdowns.length
      : 0

    // Calculate time in drawdown (percentage of periods)
    const timeInDD = (nonZeroDrawdowns.length / drawdowns.length) * 100

    return {
      current: currentDD,
      max: maxDD,
      maxDate: maxDDDate,
      avgDrawdown: avgDD,
      timeInDrawdown: timeInDD,
    }
  }, [data])

  // Determine severity colors based on max drawdown
  const colors = useMemo(() => getSeverityColor(stats.max), [stats.max])

  // Y-axis domain (inverted, showing negative values)
  const yDomain = useMemo(() => {
    if (!data || data.length === 0) return [0, -10]
    const maxDD = Math.max(...data.map((d) => d.drawdownPercent || 0))
    return [0, -Math.ceil(maxDD + 2)]
  }, [data])

  if (loading) {
    return <DrawdownChartSkeleton />
  }

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              Drawdown Analysis
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Peak-to-trough portfolio decline over time
            </p>
          </div>

          {/* Current Drawdown Badge */}
          <div className={`px-3 py-1.5 rounded-lg ${
            stats.current > 10 ? 'bg-rose-500/20 border border-rose-500/30' :
            stats.current > 5 ? 'bg-amber-500/20 border border-amber-500/30' :
            stats.current > 0 ? 'bg-yellow-500/20 border border-yellow-500/30' :
            'bg-emerald-500/20 border border-emerald-500/30'
          }`}>
            <p className="text-xs text-slate-400">Current</p>
            <p className={`text-lg font-bold ${
              stats.current > 10 ? 'text-rose-400' :
              stats.current > 5 ? 'text-amber-400' :
              stats.current > 0 ? 'text-yellow-400' :
              'text-emerald-400'
            }`}>
              -{stats.current.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Stats Strip */}
        <div className="grid grid-cols-4 gap-2">
          <DrawdownStat
            label="Max Drawdown"
            value={`-${stats.max.toFixed(2)}%`}
            color="text-rose-400"
          />
          <DrawdownStat
            label="Average DD"
            value={`-${stats.avgDrawdown.toFixed(2)}%`}
            color="text-amber-400"
          />
          <DrawdownStat
            label="Time in DD"
            value={`${stats.timeInDrawdown.toFixed(1)}%`}
            color="text-slate-300"
          />
          <DrawdownStat
            label="Data Points"
            value={data.length.toString()}
            color="text-slate-300"
          />
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        {data.length === 0 ? (
          <div className="flex items-center justify-center h-[250px] text-slate-400">
            <div className="text-center">
              <p className="text-lg mb-2">No drawdown data available</p>
              <p className="text-sm text-slate-500">
                Data will appear after trades are executed
              </p>
            </div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <AreaChart
              data={data}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {/* Gradient Definition */}
              <defs>
                <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={colors.fill} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={colors.fill} stopOpacity={0.1} />
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

              {/* Y-Axis (inverted to show negative values below zero line) */}
              <YAxis
                domain={yDomain}
                tickFormatter={(val) => `${val}%`}
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={{ stroke: '#475569' }}
                width={50}
              />

              {/* Zero Reference Line */}
              <ReferenceLine
                y={0}
                stroke="#475569"
                strokeWidth={2}
              />

              {/* Warning Thresholds */}
              <ReferenceLine
                y={-5}
                stroke="#f59e0b"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
              />
              <ReferenceLine
                y={-10}
                stroke="#ea580c"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
              />
              <ReferenceLine
                y={-20}
                stroke="#dc2626"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
              />

              {/* Tooltip */}
              <Tooltip content={<CustomTooltip />} />

              {/* Drawdown Area (inverted - showing as negative values) */}
              <Area
                type="monotone"
                dataKey={(d) => -d.drawdownPercent}
                stroke={colors.stroke}
                strokeWidth={2}
                fill="url(#drawdownGradient)"
                isAnimationActive={false}
                name="Drawdown"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Footer - Risk Level Indicator */}
      <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
        <div className="flex items-center justify-between">
          {/* Risk Level */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Risk Level:</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
              stats.max >= 20 ? 'bg-rose-500/20 text-rose-400' :
              stats.max >= 10 ? 'bg-orange-500/20 text-orange-400' :
              stats.max >= 5 ? 'bg-amber-500/20 text-amber-400' :
              'bg-emerald-500/20 text-emerald-400'
            }`}>
              {stats.max >= 20 ? 'CRITICAL' :
               stats.max >= 10 ? 'HIGH' :
               stats.max >= 5 ? 'MODERATE' : 'LOW'}
            </span>
          </div>

          {/* Threshold Legend */}
          <div className="flex items-center gap-3 text-[10px] text-slate-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
              5% Warning
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-orange-500 rounded-full"></span>
              10% Alert
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-rose-500 rounded-full"></span>
              20% Critical
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// PropTypes
DrawdownChart.propTypes = {
  data: PropTypes.arrayOf(
    PropTypes.shape({
      timestamp: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
      drawdown: PropTypes.number,
      drawdownPercent: PropTypes.number.isRequired,
      drawdownValue: PropTypes.number,
      equity: PropTypes.number,
      peak: PropTypes.number,
    })
  ),
  loading: PropTypes.bool,
  period: PropTypes.string,
  height: PropTypes.number,
  className: PropTypes.string,
}

export default DrawdownChart
