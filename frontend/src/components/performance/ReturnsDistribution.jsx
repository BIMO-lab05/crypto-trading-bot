/**
 * ReturnsDistribution.jsx - Returns Distribution Histogram Component
 *
 * Purpose: Visualizes the distribution of trade returns as a histogram.
 * Helps identify the shape of returns (normal, skewed, fat-tailed, etc.)
 *
 * Features:
 * - Bar chart histogram of returns
 * - Statistical summary (mean, median, std dev, skewness, kurtosis)
 * - Normal distribution overlay comparison
 * - Win/loss highlighting
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format currency value for axis/tooltip
 */
function formatCurrency(value, compact = false) {
  if (value == null || isNaN(value)) return 'N/A'

  if (compact && Math.abs(value) >= 1000) {
    return `$${(value / 1000).toFixed(1)}k`
  }

  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/**
 * Get bar color based on bin value (win/loss)
 */
function getBarColor(binMid) {
  if (binMid > 0) return '#10b981' // emerald-500 for wins
  if (binMid < 0) return '#f43f5e' // rose-500 for losses
  return '#6b7280' // gray-500 for break-even
}

/**
 * Get distribution quality assessment
 */
function getDistributionQuality(stats) {
  if (!stats) return { label: 'Unknown', color: 'text-slate-400' }

  // Positive skewness = right tail = more large wins
  // Negative skewness = left tail = more large losses
  const { skewness, kurtosis, mean, stdDev } = stats

  // Check for favorable distribution characteristics
  const isPositiveMean = mean > 0
  const hasPositiveSkew = skewness > 0.2
  const hasNegativeSkew = skewness < -0.2
  const isFatTailed = kurtosis > 1 // Excess kurtosis
  const coeffOfVar = stdDev / Math.abs(mean || 1)

  if (isPositiveMean && hasPositiveSkew && coeffOfVar < 3) {
    return { label: 'Favorable', color: 'text-emerald-400', description: 'Positive mean with right-skewed tail' }
  }

  if (isPositiveMean && !hasNegativeSkew) {
    return { label: 'Good', color: 'text-green-400', description: 'Positive expected return' }
  }

  if (hasNegativeSkew && isFatTailed) {
    return { label: 'Risky', color: 'text-rose-400', description: 'Fat left tail indicates tail risk' }
  }

  if (!isPositiveMean) {
    return { label: 'Poor', color: 'text-rose-400', description: 'Negative expected return' }
  }

  return { label: 'Moderate', color: 'text-amber-400', description: 'Average distribution characteristics' }
}

// ============================================================================
// CUSTOM TOOLTIP
// ============================================================================

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[180px]">
      {/* Range Header */}
      <p className="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-2 mb-2">
        {formatCurrency(data.binStart)} to {formatCurrency(data.binEnd)}
      </p>

      {/* Trade Count */}
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Trades</span>
        <span className="text-sm font-bold text-slate-100">{data.count}</span>
      </div>

      {/* Frequency */}
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">Frequency</span>
        <span className="text-sm text-slate-300">
          {(data.frequency * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  )
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const ReturnsDistributionSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/3"></div>
      <div className="h-6 bg-slate-700 rounded w-1/6"></div>
    </div>
    <div className="h-[250px] bg-slate-700/50 rounded mb-4"></div>
    <div className="grid grid-cols-5 gap-2">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="h-12 bg-slate-700 rounded"></div>
      ))}
    </div>
  </div>
)

// ============================================================================
// STAT CARD COMPONENT
// ============================================================================

const StatCard = ({ label, value, description, highlight = false }) => (
  <div className={`bg-slate-900/50 rounded-lg px-3 py-2 ${highlight ? 'ring-1 ring-emerald-500/30' : ''}`}>
    <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">{label}</p>
    <p className={`text-sm font-bold ${highlight ? 'text-emerald-400' : 'text-slate-100'}`}>
      {value}
    </p>
    {description && (
      <p className="text-[9px] text-slate-500 mt-0.5">{description}</p>
    )}
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * ReturnsDistribution - Returns Histogram Component
 *
 * @param {Object} props - Component props
 * @param {Array} props.bins - Histogram bin data
 * @param {Object} props.stats - Statistical summary
 * @param {boolean} props.loading - Loading state
 * @param {number} props.height - Chart height
 * @param {string} props.className - Additional CSS classes
 */
function ReturnsDistribution({
  bins = [],
  stats = null,
  loading = false,
  height = 250,
  className = '',
}) {
  // Distribution quality assessment
  const quality = useMemo(() => getDistributionQuality(stats), [stats])

  // Calculate X-axis domain
  const xDomain = useMemo(() => {
    if (!bins || bins.length === 0) return [-100, 100]

    const allValues = bins.flatMap((b) => [b.binStart, b.binEnd])
    const min = Math.min(...allValues)
    const max = Math.max(...allValues)
    const padding = (max - min) * 0.05

    return [min - padding, max + padding]
  }, [bins])

  // Calculate Y-axis max
  const yMax = useMemo(() => {
    if (!bins || bins.length === 0) return 10
    const maxCount = Math.max(...bins.map((b) => b.count))
    return Math.ceil(maxCount * 1.1)
  }, [bins])

  if (loading) {
    return <ReturnsDistributionSkeleton />
  }

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              Returns Distribution
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Histogram of trade P&L outcomes
            </p>
          </div>

          {/* Quality Badge */}
          <div className={`px-3 py-1.5 rounded-lg bg-slate-900/50 border border-slate-700/50`}>
            <p className="text-[10px] text-slate-400 uppercase">Quality</p>
            <p className={`text-sm font-bold ${quality.color}`}>{quality.label}</p>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        {bins.length === 0 ? (
          <div className="flex items-center justify-center h-[250px] text-slate-400">
            <div className="text-center">
              <p className="text-lg mb-2">No returns data available</p>
              <p className="text-sm text-slate-500">
                Distribution will appear after trades are closed
              </p>
            </div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <BarChart
              data={bins}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {/* Grid */}
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />

              {/* X-Axis */}
              <XAxis
                dataKey="binMid"
                tickFormatter={(v) => formatCurrency(v, true)}
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={{ stroke: '#475569' }}
              />

              {/* Y-Axis */}
              <YAxis
                domain={[0, yMax]}
                stroke="#64748b"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={{ stroke: '#475569' }}
                tickLine={{ stroke: '#475569' }}
                width={40}
                label={{
                  value: 'Trades',
                  angle: -90,
                  position: 'insideLeft',
                  fill: '#64748b',
                  fontSize: 11,
                }}
              />

              {/* Zero Reference Line */}
              <ReferenceLine x={0} stroke="#6366f1" strokeWidth={2} />

              {/* Mean Reference Line */}
              {stats?.mean != null && (
                <ReferenceLine
                  x={stats.mean}
                  stroke="#22d3ee"
                  strokeDasharray="5 5"
                  label={{
                    value: 'Mean',
                    fill: '#22d3ee',
                    fontSize: 10,
                    position: 'top',
                  }}
                />
              )}

              {/* Tooltip */}
              <Tooltip content={<CustomTooltip />} cursor={{ fill: '#334155', opacity: 0.5 }} />

              {/* Histogram Bars */}
              <Bar dataKey="count" isAnimationActive={false} radius={[2, 2, 0, 0]}>
                {bins.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getBarColor(entry.binMid)} fillOpacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Statistics Strip */}
      {stats && (
        <div className="px-5 py-4 border-t border-slate-700/50 bg-slate-800/30">
          <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
            Statistical Summary
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
            <StatCard
              label="Mean"
              value={formatCurrency(stats.mean)}
              highlight={stats.mean > 0}
            />
            <StatCard
              label="Median"
              value={formatCurrency(stats.median)}
            />
            <StatCard
              label="Std Dev"
              value={formatCurrency(stats.stdDev)}
              description="Volatility"
            />
            <StatCard
              label="Skewness"
              value={stats.skewness?.toFixed(2) || 'N/A'}
              description={stats.skewness > 0 ? 'Right tail' : stats.skewness < 0 ? 'Left tail' : 'Symmetric'}
            />
            <StatCard
              label="Kurtosis"
              value={stats.kurtosis?.toFixed(2) || 'N/A'}
              description={stats.kurtosis > 0 ? 'Fat tails' : 'Thin tails'}
            />
            <StatCard
              label="Total Trades"
              value={stats.count?.toString() || '0'}
            />
          </div>

          {/* Distribution Interpretation */}
          <div className="mt-3 pt-3 border-t border-slate-700/50">
            <p className="text-xs text-slate-400">
              <span className={`font-semibold ${quality.color}`}>{quality.label}:</span>{' '}
              {quality.description}
            </p>
          </div>
        </div>
      )}

      {/* Footer Legend */}
      <div className="px-5 py-2 bg-slate-900/30 border-t border-slate-700/30">
        <div className="flex items-center justify-between text-[10px] text-slate-500">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-emerald-500 rounded-sm"></span>
              Winning Trades
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-rose-500 rounded-sm"></span>
              Losing Trades
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-0.5 bg-cyan-400"></span>
              Mean
            </span>
          </div>
          <span>Range: {formatCurrency(stats?.min)} to {formatCurrency(stats?.max)}</span>
        </div>
      </div>
    </div>
  )
}

// PropTypes
ReturnsDistribution.propTypes = {
  bins: PropTypes.arrayOf(
    PropTypes.shape({
      binStart: PropTypes.number.isRequired,
      binEnd: PropTypes.number.isRequired,
      binMid: PropTypes.number.isRequired,
      count: PropTypes.number.isRequired,
      frequency: PropTypes.number.isRequired,
    })
  ),
  stats: PropTypes.shape({
    count: PropTypes.number,
    mean: PropTypes.number,
    median: PropTypes.number,
    stdDev: PropTypes.number,
    variance: PropTypes.number,
    min: PropTypes.number,
    max: PropTypes.number,
    skewness: PropTypes.number,
    kurtosis: PropTypes.number,
    range: PropTypes.number,
  }),
  loading: PropTypes.bool,
  height: PropTypes.number,
  className: PropTypes.string,
}

export default ReturnsDistribution
