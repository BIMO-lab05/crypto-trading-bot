/**
 * StrategyAttribution.jsx - Strategy Performance Breakdown Component
 *
 * Purpose: Displays performance attribution by strategy, showing which
 * trading strategies contribute most to overall P&L.
 *
 * Features:
 * - Bar chart showing P&L by strategy
 * - Pie chart showing P&L distribution
 * - Table with detailed strategy metrics
 * - Win rate, profit factor per strategy
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
} from 'recharts'

// ============================================================================
// CONSTANTS
// ============================================================================

// Color palette for strategies (consistent colors for same strategies)
const STRATEGY_COLORS = [
  '#06b6d4', // cyan-500
  '#8b5cf6', // violet-500
  '#f59e0b', // amber-500
  '#10b981', // emerald-500
  '#f43f5e', // rose-500
  '#3b82f6', // blue-500
  '#ec4899', // pink-500
  '#14b8a6', // teal-500
  '#f97316', // orange-500
  '#a855f7', // purple-500
]

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format currency value
 */
function formatCurrency(value) {
  if (value == null || isNaN(value)) return 'N/A'
  const sign = value >= 0 ? '+' : ''
  return `${sign}$${Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/**
 * Format percentage value
 */
function formatPercent(value) {
  if (value == null || isNaN(value)) return 'N/A'
  return `${value.toFixed(1)}%`
}

/**
 * Get color for strategy by index (consistent mapping)
 */
function getStrategyColor(index) {
  return STRATEGY_COLORS[index % STRATEGY_COLORS.length]
}

/**
 * Get P&L color based on value
 */
function getPnLColor(value) {
  if (value > 0) return 'text-emerald-400'
  if (value < 0) return 'text-rose-400'
  return 'text-slate-400'
}

// ============================================================================
// CUSTOM TOOLTIP COMPONENTS
// ============================================================================

/**
 * Custom tooltip for bar chart
 */
const BarChartTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[200px]">
      {/* Strategy Name */}
      <p className="text-sm font-semibold text-slate-100 border-b border-slate-700 pb-2 mb-2">
        {data.strategy}
      </p>

      {/* P&L */}
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Total P&L</span>
        <span className={`text-sm font-bold ${getPnLColor(data.pnl)}`}>
          {formatCurrency(data.pnl)}
        </span>
      </div>

      {/* Trade Count */}
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Trades</span>
        <span className="text-sm text-slate-200">{data.trades}</span>
      </div>

      {/* Win Rate */}
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Win Rate</span>
        <span className="text-sm text-slate-200">{formatPercent(data.winRate)}</span>
      </div>

      {/* Profit Factor */}
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">Profit Factor</span>
        <span className="text-sm text-slate-200">{data.profitFactor?.toFixed(2) || 'N/A'}</span>
      </div>
    </div>
  )
}

/**
 * Custom tooltip for pie chart
 */
const PieChartTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[160px]">
      <p className="text-sm font-semibold text-slate-100 mb-2">{data.strategy}</p>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-slate-400">Contribution</span>
        <span className="text-sm font-bold text-slate-100">{formatPercent(data.contribution)}</span>
      </div>
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">P&L</span>
        <span className={`text-sm ${getPnLColor(data.pnl)}`}>{formatCurrency(data.pnl)}</span>
      </div>
    </div>
  )
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const StrategyAttributionSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/3"></div>
      <div className="flex gap-2">
        <div className="h-8 w-16 bg-slate-700 rounded"></div>
        <div className="h-8 w-16 bg-slate-700 rounded"></div>
      </div>
    </div>
    <div className="grid grid-cols-2 gap-4">
      <div className="h-[300px] bg-slate-700/50 rounded"></div>
      <div className="h-[300px] bg-slate-700/50 rounded"></div>
    </div>
  </div>
)

// ============================================================================
// STRATEGY TABLE COMPONENT
// ============================================================================

const StrategyTable = ({ data }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-700/50">
          <th className="text-left py-2 px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
            Strategy
          </th>
          <th className="text-right py-2 px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
            P&L
          </th>
          <th className="text-right py-2 px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
            Trades
          </th>
          <th className="text-right py-2 px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
            Win Rate
          </th>
          <th className="text-right py-2 px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
            PF
          </th>
          <th className="text-right py-2 px-3 text-xs font-medium text-slate-400 uppercase tracking-wide">
            Contrib
          </th>
        </tr>
      </thead>
      <tbody>
        {data.map((strategy, index) => (
          <tr
            key={strategy.strategy}
            className="border-b border-slate-700/30 hover:bg-slate-700/20 transition-colors"
          >
            <td className="py-2 px-3">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: getStrategyColor(index) }}
                ></span>
                <span className="text-slate-200 font-medium">{strategy.strategy}</span>
              </div>
            </td>
            <td className={`text-right py-2 px-3 font-semibold ${getPnLColor(strategy.pnl)}`}>
              {formatCurrency(strategy.pnl)}
            </td>
            <td className="text-right py-2 px-3 text-slate-300">{strategy.trades}</td>
            <td className="text-right py-2 px-3">
              <span
                className={
                  strategy.winRate >= 55
                    ? 'text-emerald-400'
                    : strategy.winRate >= 45
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }
              >
                {formatPercent(strategy.winRate)}
              </span>
            </td>
            <td className="text-right py-2 px-3">
              <span
                className={
                  strategy.profitFactor >= 1.5
                    ? 'text-emerald-400'
                    : strategy.profitFactor >= 1
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }
              >
                {strategy.profitFactor?.toFixed(2) || 'N/A'}
              </span>
            </td>
            <td className="text-right py-2 px-3 text-slate-400">
              {formatPercent(strategy.contribution)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * StrategyAttribution - Strategy Performance Breakdown
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Strategy performance data
 * @param {boolean} props.loading - Loading state
 * @param {number} props.height - Chart height
 * @param {string} props.className - Additional CSS classes
 */
function StrategyAttribution({
  data = [],
  loading = false,
  height = 300,
  className = '',
}) {
  // View toggle: 'chart' or 'table'
  const [viewMode, setViewMode] = useState('chart')

  // Process data for charts
  const processedData = useMemo(() => {
    if (!data || data.length === 0) return []

    // Calculate total P&L (absolute value for contribution calculation)
    const totalAbsPnL = data.reduce((sum, s) => sum + Math.abs(s.pnl || 0), 0)

    return data.map((strategy, index) => ({
      ...strategy,
      contribution: totalAbsPnL > 0 ? (Math.abs(strategy.pnl || 0) / totalAbsPnL) * 100 : 0,
      color: getStrategyColor(index),
    }))
  }, [data])

  // Sort by absolute P&L for bar chart
  const sortedData = useMemo(() => {
    return [...processedData].sort((a, b) => Math.abs(b.pnl || 0) - Math.abs(a.pnl || 0))
  }, [processedData])

  // Calculate summary stats
  const summaryStats = useMemo(() => {
    if (!data || data.length === 0) {
      return { totalPnL: 0, bestStrategy: null, worstStrategy: null, avgWinRate: 0 }
    }

    const totalPnL = data.reduce((sum, s) => sum + (s.pnl || 0), 0)
    const sorted = [...data].sort((a, b) => (b.pnl || 0) - (a.pnl || 0))
    const bestStrategy = sorted[0]
    const worstStrategy = sorted[sorted.length - 1]
    const avgWinRate = data.reduce((sum, s) => sum + (s.winRate || 0), 0) / data.length

    return { totalPnL, bestStrategy, worstStrategy, avgWinRate }
  }, [data])

  if (loading) {
    return <StrategyAttributionSkeleton />
  }

  return (
    <div
      className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-100">Strategy Attribution</h3>
            <p className="text-xs text-slate-500 mt-0.5">P&L breakdown by trading strategy</p>
          </div>

          {/* View Toggle */}
          <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
            <button
              onClick={() => setViewMode('chart')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'chart'
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Chart
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'table'
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Table
            </button>
          </div>
        </div>

        {/* Summary Stats */}
        {data.length > 0 && (
          <div className="grid grid-cols-4 gap-3 mt-4">
            <div className="bg-slate-900/50 rounded-lg px-3 py-2">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Total P&L</p>
              <p className={`text-lg font-bold ${getPnLColor(summaryStats.totalPnL)}`}>
                {formatCurrency(summaryStats.totalPnL)}
              </p>
            </div>
            <div className="bg-slate-900/50 rounded-lg px-3 py-2">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Best Strategy</p>
              <p className="text-sm font-semibold text-emerald-400">
                {summaryStats.bestStrategy?.strategy || 'N/A'}
              </p>
            </div>
            <div className="bg-slate-900/50 rounded-lg px-3 py-2">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Worst Strategy</p>
              <p className="text-sm font-semibold text-rose-400">
                {summaryStats.worstStrategy?.strategy || 'N/A'}
              </p>
            </div>
            <div className="bg-slate-900/50 rounded-lg px-3 py-2">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Avg Win Rate</p>
              <p className="text-sm font-semibold text-slate-100">
                {formatPercent(summaryStats.avgWinRate)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {data.length === 0 ? (
          <div className="flex items-center justify-center h-[300px] text-slate-400">
            <div className="text-center">
              <p className="text-lg mb-2">No strategy data available</p>
              <p className="text-sm text-slate-500">Data will appear after trades are executed</p>
            </div>
          </div>
        ) : viewMode === 'chart' ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Bar Chart - P&L by Strategy */}
            <div>
              <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                P&L by Strategy
              </h4>
              <ResponsiveContainer width="100%" height={height}>
                <BarChart
                  data={sortedData}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={true} />
                  <XAxis
                    type="number"
                    stroke="#64748b"
                    tick={{ fill: '#94a3b8', fontSize: 10 }}
                    tickFormatter={(v) =>
                      Math.abs(v) >= 1000
                        ? `$${(v / 1000).toFixed(0)}k`
                        : `$${Number(v).toFixed(0)}`
                    }
                    axisLine={{ stroke: '#475569' }}
                  />
                  <YAxis
                    type="category"
                    dataKey="strategy"
                    stroke="#64748b"
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    axisLine={{ stroke: '#475569' }}
                    width={70}
                  />
                  <Tooltip content={<BarChartTooltip />} />
                  <Bar dataKey="pnl" isAnimationActive={false} radius={[0, 4, 4, 0]}>
                    {sortedData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.pnl >= 0 ? '#10b981' : '#f43f5e'}
                        fillOpacity={0.8}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Pie Chart - Contribution Distribution */}
            <div>
              <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                P&L Contribution
              </h4>
              <ResponsiveContainer width="100%" height={height}>
                <PieChart>
                  <Pie
                    data={processedData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="contribution"
                    nameKey="strategy"
                    isAnimationActive={false}
                  >
                    {processedData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={getStrategyColor(index)}
                        stroke="#1e293b"
                        strokeWidth={2}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<PieChartTooltip />} />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => <span className="text-slate-300 text-xs">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          /* Table View */
          <StrategyTable data={processedData} />
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-2 bg-slate-800/30 border-t border-slate-700/50">
        <div className="flex items-center justify-between text-[10px] text-slate-500">
          <span>Strategies: {data.length}</span>
          <span>Total Trades: {data.reduce((sum, s) => sum + (s.trades || 0), 0)}</span>
        </div>
      </div>
    </div>
  )
}

// PropTypes
StrategyAttribution.propTypes = {
  data: PropTypes.arrayOf(
    PropTypes.shape({
      strategy: PropTypes.string.isRequired,
      pnl: PropTypes.number.isRequired,
      trades: PropTypes.number.isRequired,
      winRate: PropTypes.number,
      profitFactor: PropTypes.number,
      avgWin: PropTypes.number,
      avgLoss: PropTypes.number,
    })
  ),
  loading: PropTypes.bool,
  height: PropTypes.number,
  className: PropTypes.string,
}

export default StrategyAttribution
