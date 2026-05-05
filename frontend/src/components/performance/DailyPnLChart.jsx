/**
 * DailyPnLChart.jsx - Daily P&L Bar Chart Component
 *
 * Purpose: Visualizes daily profit/loss as a bar chart with positive (green)
 * and negative (red) bars showing daily trading performance.
 *
 * Features:
 * - Stacked or grouped bar display
 * - Win/Loss color coding
 * - Trade count overlay
 * - Custom tooltips with detailed info
 * - Cumulative P&L line overlay (optional)
 * - Period selection
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
  Legend,
} from 'recharts'
import { format, parseISO, isValid } from 'date-fns'
import { formatCurrency, formatPnL } from '../../utils/formatters'
import { colors, gridConfig, axisConfig } from '../../utils/chartConfig'
import ChartFigure from '../a11y/ChartFigure'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format X-axis date label based on period
 */
function formatXAxis(dateStr, period) {
  const date = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr)
  if (!isValid(date)) return ''

  switch (period) {
    case '7d':
      return format(date, 'EEE')
    case '30d':
      return format(date, 'MMM d')
    case '90d':
    case '365d':
    case 'all':
      return format(date, 'MMM d')
    default:
      return format(date, 'MMM d')
  }
}

/**
 * Get bar color based on P&L value
 */
function getBarColor(value) {
  if (value > 0) return colors.profit
  if (value < 0) return colors.loss
  return colors.neutral
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const DailyPnLChartSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/4"></div>
      <div className="flex gap-2">
        <div className="h-6 w-12 bg-slate-700 rounded"></div>
        <div className="h-6 w-12 bg-slate-700 rounded"></div>
      </div>
    </div>
    <div className="h-[280px] bg-slate-700/50 rounded"></div>
    <div className="flex justify-between mt-4">
      <div className="h-4 w-20 bg-slate-700 rounded"></div>
      <div className="h-4 w-20 bg-slate-700 rounded"></div>
    </div>
  </div>
)

// ============================================================================
// CUSTOM TOOLTIP
// ============================================================================

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload
  const date = typeof label === 'string' ? parseISO(label) : new Date(label)

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[200px]">
      {/* Date Header */}
      <p className="text-sm font-semibold text-slate-200 border-b border-slate-700 pb-2 mb-2">
        {isValid(date) ? format(date, 'EEEE, MMM d, yyyy') : 'N/A'}
      </p>

      {/* Net P&L */}
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs text-slate-400">Net P&L</span>
        <span className={`text-sm font-bold ${
          (data.net || data.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
        }`}>
          {formatPnL(data.net || data.pnl || 0)}
        </span>
      </div>

      {/* Wins/Losses if available */}
      {(data.profit != null || data.loss != null) && (
        <>
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-slate-400">Profit</span>
            <span className="text-sm font-semibold text-emerald-400">
              {formatCurrency(data.profit || 0)}
            </span>
          </div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-slate-400">Loss</span>
            <span className="text-sm font-semibold text-rose-400">
              {formatCurrency(Math.abs(data.loss || 0))}
            </span>
          </div>
        </>
      )}

      {/* Cumulative P&L if available */}
      {data.cumulativePnl != null && (
        <div className="flex justify-between items-center pt-2 border-t border-slate-700 mt-2">
          <span className="text-xs text-slate-400">Cumulative</span>
          <span className={`text-sm font-semibold ${
            data.cumulativePnl >= 0 ? 'text-cyan-400' : 'text-orange-400'
          }`}>
            {formatPnL(data.cumulativePnl)}
          </span>
        </div>
      )}

      {/* Trade Count */}
      {data.tradeCount != null && (
        <div className="flex justify-between items-center mt-1">
          <span className="text-xs text-slate-400">Trades</span>
          <span className="text-sm text-slate-300">
            {data.tradeCount} ({data.winCount || 0}W / {data.lossCount || 0}L)
          </span>
        </div>
      )}

      {/* Win Rate if available */}
      {data.winRate != null && (
        <div className="flex justify-between items-center mt-1">
          <span className="text-xs text-slate-400">Win Rate</span>
          <span className="text-sm text-slate-300">
            {data.winRate.toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// STATS CARD COMPONENT
// ============================================================================

const StatCard = ({ label, value, color = 'text-slate-100' }) => (
  <div className="bg-slate-900/50 rounded-lg px-3 py-2 text-center">
    <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">{label}</p>
    <p className={`text-sm font-bold ${color}`}>{value}</p>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * DailyPnLChart - Daily P&L Bar Chart Component
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Daily P&L data array
 * @param {boolean} props.loading - Loading state
 * @param {string} props.period - Time period
 * @param {boolean} props.showCumulative - Show cumulative P&L line
 * @param {boolean} props.showLegend - Show chart legend
 * @param {number} props.height - Chart height
 * @param {string} props.className - Additional CSS classes
 */
function DailyPnLChart({
  data = [],
  loading = false,
  period = '30d',
  showCumulative = true,
  showLegend = true,
  height = 280,
  className = '',
}) {
  // Calculate statistics
  const stats = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        totalDays: 0,
        profitableDays: 0,
        losingDays: 0,
        avgDailyPnL: 0,
        bestDay: 0,
        worstDay: 0,
        totalPnL: 0,
      }
    }

    const pnls = data.map((d) => d.net || d.pnl || 0)
    const profitableDays = pnls.filter((p) => p > 0).length
    const losingDays = pnls.filter((p) => p < 0).length
    const totalPnL = pnls.reduce((sum, p) => sum + p, 0)
    const avgDailyPnL = totalPnL / pnls.length

    return {
      totalDays: data.length,
      profitableDays,
      losingDays,
      avgDailyPnL,
      bestDay: Math.max(...pnls),
      worstDay: Math.min(...pnls),
      totalPnL,
    }
  }, [data])

  // Y-axis domain with padding
  const yDomain = useMemo(() => {
    if (!data || data.length === 0) return [-100, 100]

    const allPnLs = data.flatMap((d) => [
      d.net || d.pnl || 0,
      d.profit || 0,
      d.loss || 0,
    ])

    const min = Math.min(...allPnLs)
    const max = Math.max(...allPnLs)
    const padding = (max - min) * 0.1 || 50

    return [Math.floor(min - padding), Math.ceil(max + padding)]
  }, [data])

  // Cumulative P&L data
  const chartData = useMemo(() => {
    if (!showCumulative || data.length === 0) return data

    let cumulative = 0
    return data.map((d) => {
      cumulative += (d.net || d.pnl || 0)
      return {
        ...d,
        cumulativePnl: cumulative,
      }
    })
  }, [data, showCumulative])

  if (loading) {
    return <DailyPnLChartSkeleton />
  }

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              Daily P&L
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Daily profit and loss over time
            </p>
          </div>

          {/* Total P&L Badge */}
          <div className={`px-3 py-1.5 rounded-lg ${
            stats.totalPnL >= 0 ? 'bg-emerald-500/20 border border-emerald-500/30' : 'bg-rose-500/20 border border-rose-500/30'
          }`}>
            <p className="text-[10px] text-slate-400 uppercase">Total</p>
            <p className={`text-lg font-bold ${
              stats.totalPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {formatPnL(stats.totalPnL)}
            </p>
          </div>
        </div>

        {/* Stats Strip */}
        <div className="grid grid-cols-5 gap-2">
          <StatCard
            label="Days"
            value={stats.totalDays.toString()}
          />
          <StatCard
            label="Profitable"
            value={stats.profitableDays.toString()}
            color="text-emerald-400"
          />
          <StatCard
            label="Losing"
            value={stats.losingDays.toString()}
            color="text-rose-400"
          />
          <StatCard
            label="Best Day"
            value={formatPnL(stats.bestDay)}
            color="text-emerald-400"
          />
          <StatCard
            label="Worst Day"
            value={formatPnL(stats.worstDay)}
            color="text-rose-400"
          />
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        {data.length === 0 ? (
          <div className="flex items-center justify-center h-[280px] text-slate-400">
            <div className="text-center">
              <p className="text-lg mb-2">No daily P&L data available</p>
              <p className="text-sm text-slate-500">
                Data will appear after trades are executed
              </p>
            </div>
          </div>
        ) : (
          <ChartFigure
            summary={`Daily profit and loss. ${stats.totalDays} days. ${stats.profitableDays} profitable, ${stats.losingDays} losing. Total P&L ${formatPnL(stats.totalPnL)}. Average daily ${formatPnL(stats.avgDailyPnL)}. Best day ${formatPnL(stats.bestDay)}, worst day ${formatPnL(stats.worstDay)}.`}
            tableCaption="Daily P&L summary"
            columns={[
              { key: 'metric', label: 'Metric' },
              { key: 'value', label: 'Value' },
            ]}
            rows={[
              { metric: 'Total days', value: stats.totalDays.toString() },
              { metric: 'Profitable days', value: stats.profitableDays.toString() },
              { metric: 'Losing days', value: stats.losingDays.toString() },
              { metric: 'Total P&L', value: formatPnL(stats.totalPnL) },
              { metric: 'Average daily P&L', value: formatPnL(stats.avgDailyPnL) },
              { metric: 'Best day', value: formatPnL(stats.bestDay) },
              { metric: 'Worst day', value: formatPnL(stats.worstDay) },
            ]}
          >
          <ResponsiveContainer width="100%" height={height}>
            <ComposedChart
              data={chartData}
              margin={{ top: 10, right: 30, left: 10, bottom: 0 }}
            >
              {/* Gradient Definitions */}
              <defs>
                <linearGradient id="profitBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors.profit} stopOpacity={0.9} />
                  <stop offset="100%" stopColor={colors.profit} stopOpacity={0.6} />
                </linearGradient>
                <linearGradient id="lossBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors.loss} stopOpacity={0.6} />
                  <stop offset="100%" stopColor={colors.loss} stopOpacity={0.9} />
                </linearGradient>
              </defs>

              {/* Grid */}
              <CartesianGrid {...gridConfig.default} />

              {/* X-Axis */}
              <XAxis
                dataKey="date"
                tickFormatter={(date) => formatXAxis(date, period)}
                {...axisConfig.xAxis}
              />

              {/* Y-Axis for P&L */}
              <YAxis
                yAxisId="pnl"
                domain={yDomain}
                tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                {...axisConfig.yAxis}
              />

              {/* Y-Axis for Cumulative (right side) */}
              {showCumulative && (
                <YAxis
                  yAxisId="cumulative"
                  orientation="right"
                  tickFormatter={(val) => `$${(val / 1000).toFixed(1)}k`}
                  stroke={colors.highlight}
                  tick={{ fill: colors.highlight, fontSize: 10 }}
                  axisLine={{ stroke: colors.highlight, strokeOpacity: 0.5 }}
                />
              )}

              {/* Zero Reference Line */}
              <ReferenceLine
                yAxisId="pnl"
                y={0}
                stroke={colors.axis}
                strokeWidth={2}
              />

              {/* Tooltip */}
              <Tooltip content={<CustomTooltip />} />

              {/* Legend */}
              {showLegend && (
                <Legend
                  verticalAlign="bottom"
                  height={36}
                  iconType="rect"
                  iconSize={10}
                  formatter={(value) => (
                    <span className="text-xs text-slate-400">{value}</span>
                  )}
                />
              )}

              {/* P&L Bars */}
              <Bar
                yAxisId="pnl"
                dataKey="net"
                name="Daily P&L"
                radius={[4, 4, 0, 0]}
                maxBarSize={40}
              >
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={(entry.net || entry.pnl || 0) >= 0 ? 'url(#profitBarGradient)' : 'url(#lossBarGradient)'}
                  />
                ))}
              </Bar>

              {/* Cumulative P&L Line */}
              {showCumulative && (
                <Line
                  yAxisId="cumulative"
                  type="monotone"
                  dataKey="cumulativePnl"
                  name="Cumulative P&L"
                  stroke={colors.highlight}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 2 }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
          </ChartFigure>
        )}
      </div>

      {/* Footer - Legend */}
      <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
        <div className="flex items-center justify-between text-[10px] text-slate-500">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 bg-emerald-500 rounded-sm"></span>
              Profitable Day
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 bg-rose-500 rounded-sm"></span>
              Losing Day
            </span>
            {showCumulative && (
              <span className="flex items-center gap-1">
                <span className="w-4 h-0.5 bg-cyan-400"></span>
                Cumulative P&L
              </span>
            )}
          </div>
          <span>
            Avg Daily: <span className={stats.avgDailyPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {formatPnL(stats.avgDailyPnL)}
            </span>
          </span>
        </div>
      </div>
    </div>
  )
}

// PropTypes
DailyPnLChart.propTypes = {
  data: PropTypes.arrayOf(
    PropTypes.shape({
      date: PropTypes.string.isRequired,
      net: PropTypes.number,
      pnl: PropTypes.number,
      profit: PropTypes.number,
      loss: PropTypes.number,
      tradeCount: PropTypes.number,
      winCount: PropTypes.number,
      lossCount: PropTypes.number,
      winRate: PropTypes.number,
      cumulativePnl: PropTypes.number,
    })
  ),
  loading: PropTypes.bool,
  period: PropTypes.string,
  showCumulative: PropTypes.bool,
  showLegend: PropTypes.bool,
  height: PropTypes.number,
  className: PropTypes.string,
}

export default DailyPnLChart
