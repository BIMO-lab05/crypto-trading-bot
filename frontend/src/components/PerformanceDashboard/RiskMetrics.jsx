/**
 * RiskMetrics.jsx - Risk Metrics Display Component
 *
 * Purpose: Displays key risk metrics including VaR, CVaR, Beta, and
 * other risk indicators with visual gauge representations.
 *
 * Features:
 * - Gauge charts for risk metrics
 * - Risk level indicators
 * - Trend comparison with previous period
 * - Detailed tooltips with explanations
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo } from 'react'
import PropTypes from 'prop-types'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Format currency value
 */
function formatCurrency(value) {
  if (value == null || isNaN(value)) return 'N/A'
  return `$${Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/**
 * Format percentage value
 */
function formatPercent(value) {
  if (value == null || isNaN(value)) return 'N/A'
  return `${value.toFixed(2)}%`
}

/**
 * Format ratio value
 */
function formatRatio(value) {
  if (value == null || isNaN(value)) return 'N/A'
  return value.toFixed(2)
}

/**
 * Get risk level configuration based on metric type and value
 */
function getRiskLevel(metricType, value) {
  if (value == null) return { level: 'unknown', color: 'slate', label: 'Unknown' }

  const configs = {
    var: {
      // VaR - lower is better, thresholds as % of portfolio
      thresholds: [2, 5, 10],
      levels: ['low', 'moderate', 'high', 'critical'],
      colors: ['emerald', 'amber', 'orange', 'rose'],
      labels: ['Low Risk', 'Moderate Risk', 'High Risk', 'Critical Risk'],
    },
    cvar: {
      // CVaR - lower is better
      thresholds: [3, 7.5, 15],
      levels: ['low', 'moderate', 'high', 'critical'],
      colors: ['emerald', 'amber', 'orange', 'rose'],
      labels: ['Low Risk', 'Moderate Risk', 'High Risk', 'Critical Risk'],
    },
    beta: {
      // Beta - 1 is market neutral, deviation is risk
      thresholds: [0.8, 1.2, 1.5],
      levels: ['low', 'moderate', 'high', 'extreme'],
      colors: ['emerald', 'cyan', 'amber', 'rose'],
      labels: ['Defensive', 'Neutral', 'Aggressive', 'Very Aggressive'],
    },
    volatility: {
      // Volatility - lower is typically better
      thresholds: [15, 25, 40],
      levels: ['low', 'moderate', 'high', 'extreme'],
      colors: ['emerald', 'amber', 'orange', 'rose'],
      labels: ['Low Vol', 'Moderate Vol', 'High Vol', 'Extreme Vol'],
    },
    maxDrawdown: {
      // Max Drawdown - lower is better
      thresholds: [5, 10, 20],
      levels: ['low', 'moderate', 'high', 'critical'],
      colors: ['emerald', 'amber', 'orange', 'rose'],
      labels: ['Healthy', 'Moderate', 'Elevated', 'Critical'],
    },
    sharpe: {
      // Sharpe Ratio - higher is better (inverted)
      thresholds: [2, 1, 0.5],
      levels: ['excellent', 'good', 'moderate', 'poor'],
      colors: ['emerald', 'cyan', 'amber', 'rose'],
      labels: ['Excellent', 'Good', 'Moderate', 'Poor'],
      inverted: true,
    },
  }

  const config = configs[metricType] || configs.var
  const absValue = Math.abs(value)

  let levelIndex = 0
  if (config.inverted) {
    // Higher is better
    for (let i = 0; i < config.thresholds.length; i++) {
      if (value < config.thresholds[i]) {
        levelIndex = config.thresholds.length - i
        break
      }
    }
  } else {
    // Lower is better
    for (let i = 0; i < config.thresholds.length; i++) {
      if (absValue >= config.thresholds[i]) {
        levelIndex = i + 1
      }
    }
  }

  return {
    level: config.levels[levelIndex],
    color: config.colors[levelIndex],
    label: config.labels[levelIndex],
    threshold: config.thresholds[Math.min(levelIndex, config.thresholds.length - 1)],
  }
}

// ============================================================================
// GAUGE COMPONENT
// ============================================================================

/**
 * Semi-circular gauge chart component
 */
const GaugeChart = ({ value, maxValue, color, size = 120 }) => {
  const radius = (size - 20) / 2
  const circumference = Math.PI * radius
  const percentage = Math.min(Math.abs(value) / maxValue, 1)
  const strokeDashoffset = circumference * (1 - percentage)

  const colorMap = {
    emerald: { stroke: '#10b981', glow: 'rgba(16, 185, 129, 0.4)' },
    cyan: { stroke: '#06b6d4', glow: 'rgba(6, 182, 212, 0.4)' },
    amber: { stroke: '#f59e0b', glow: 'rgba(245, 158, 11, 0.4)' },
    orange: { stroke: '#f97316', glow: 'rgba(249, 115, 22, 0.4)' },
    rose: { stroke: '#f43f5e', glow: 'rgba(244, 63, 94, 0.4)' },
    slate: { stroke: '#64748b', glow: 'rgba(100, 116, 139, 0.4)' },
  }

  const colors = colorMap[color] || colorMap.slate

  return (
    <svg width={size} height={size / 2 + 10} className="transform -rotate-0">
      {/* Background arc */}
      <path
        d={`M ${10} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - 10} ${size / 2}`}
        fill="none"
        stroke="#334155"
        strokeWidth="8"
        strokeLinecap="round"
      />
      {/* Value arc */}
      <path
        d={`M ${10} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - 10} ${size / 2}`}
        fill="none"
        stroke={colors.stroke}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        style={{
          filter: `drop-shadow(0 0 6px ${colors.glow})`,
          transition: 'stroke-dashoffset 0.5s ease-out',
        }}
      />
      {/* Center marker */}
      <circle cx={size / 2} cy={size / 2} r="4" fill={colors.stroke} />
    </svg>
  )
}

// ============================================================================
// RISK METRIC CARD COMPONENT
// ============================================================================

const RiskMetricCard = ({
  title,
  value,
  format = 'currency',
  metricType,
  description,
  change,
  maxGaugeValue = 100,
  showGauge = true,
}) => {
  const riskLevel = useMemo(() => getRiskLevel(metricType, value), [metricType, value])

  // Format the value based on type
  const formattedValue = useMemo(() => {
    if (value == null) return 'N/A'
    switch (format) {
      case 'currency':
        return formatCurrency(value)
      case 'percent':
        return formatPercent(value)
      case 'ratio':
        return formatRatio(value)
      default:
        return value.toString()
    }
  }, [value, format])

  // Determine change direction and color
  const changeInfo = useMemo(() => {
    if (change == null) return null

    // For risk metrics, decrease is usually good
    const isImprovement = change < 0
    return {
      direction: change > 0 ? 'up' : 'down',
      color: isImprovement ? 'text-emerald-400' : 'text-rose-400',
      icon: change > 0 ? '↑' : '↓',
      value: Math.abs(change),
    }
  }, [change])

  return (
    <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 p-4 hover:border-slate-600/50 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide">{title}</h4>
          {description && <p className="text-[10px] text-slate-500 mt-0.5">{description}</p>}
        </div>
        {/* Risk Level Badge */}
        <span
          className={`text-[10px] font-semibold px-2 py-0.5 rounded bg-${riskLevel.color}-500/20 text-${riskLevel.color}-400`}
          style={{
            backgroundColor:
              riskLevel.color === 'emerald'
                ? 'rgba(16, 185, 129, 0.2)'
                : riskLevel.color === 'cyan'
                ? 'rgba(6, 182, 212, 0.2)'
                : riskLevel.color === 'amber'
                ? 'rgba(245, 158, 11, 0.2)'
                : riskLevel.color === 'orange'
                ? 'rgba(249, 115, 22, 0.2)'
                : riskLevel.color === 'rose'
                ? 'rgba(244, 63, 94, 0.2)'
                : 'rgba(100, 116, 139, 0.2)',
            color:
              riskLevel.color === 'emerald'
                ? '#34d399'
                : riskLevel.color === 'cyan'
                ? '#22d3ee'
                : riskLevel.color === 'amber'
                ? '#fbbf24'
                : riskLevel.color === 'orange'
                ? '#fb923c'
                : riskLevel.color === 'rose'
                ? '#fb7185'
                : '#94a3b8',
          }}
        >
          {riskLevel.label}
        </span>
      </div>

      {/* Gauge and Value */}
      <div className="flex items-center justify-between">
        {showGauge && (
          <div className="flex-shrink-0">
            <GaugeChart
              value={Math.abs(value || 0)}
              maxValue={maxGaugeValue}
              color={riskLevel.color}
              size={80}
            />
          </div>
        )}
        <div className={`text-right ${showGauge ? '' : 'w-full'}`}>
          <p className="text-2xl font-bold text-slate-100">{formattedValue}</p>
          {changeInfo && (
            <p className={`text-xs font-medium ${changeInfo.color} mt-1`}>
              {changeInfo.icon} {changeInfo.value.toFixed(2)}%
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const RiskMetricsSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/3"></div>
      <div className="h-8 w-24 bg-slate-700 rounded"></div>
    </div>
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
        <div key={i} className="h-32 bg-slate-700/50 rounded-lg"></div>
      ))}
    </div>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * RiskMetrics - Risk Metrics Dashboard Component
 *
 * @param {Object} props - Component props
 * @param {Object} props.metrics - Risk metrics data
 * @param {boolean} props.loading - Loading state
 * @param {string} props.className - Additional CSS classes
 */
function RiskMetrics({ metrics = {}, loading = false, className = '' }) {
  // Calculate overall risk score (0-100)
  const overallRiskScore = useMemo(() => {
    if (!metrics || Object.keys(metrics).length === 0) return null

    // Weighted risk score based on different metrics
    const weights = {
      maxDrawdown: 0.25,
      var95: 0.2,
      cvar95: 0.2,
      volatility: 0.15,
      sharpeRatio: 0.2,
    }

    let score = 0
    let totalWeight = 0

    // Max Drawdown contribution (0-100, lower is better)
    if (metrics.maxDrawdownPercent != null) {
      const ddScore = Math.min((metrics.maxDrawdownPercent / 30) * 100, 100)
      score += ddScore * weights.maxDrawdown
      totalWeight += weights.maxDrawdown
    }

    // VaR contribution
    if (metrics.var95 != null && metrics.portfolioValue != null) {
      const varPercent = (metrics.var95 / metrics.portfolioValue) * 100
      const varScore = Math.min((varPercent / 15) * 100, 100)
      score += varScore * weights.var95
      totalWeight += weights.var95
    }

    // Volatility contribution
    if (metrics.volatility != null) {
      const volScore = Math.min((metrics.volatility / 50) * 100, 100)
      score += volScore * weights.volatility
      totalWeight += weights.volatility
    }

    // Sharpe Ratio contribution (inverted - higher Sharpe = lower risk)
    if (metrics.sharpeRatio != null) {
      const sharpeScore = Math.max(0, 100 - metrics.sharpeRatio * 25)
      score += sharpeScore * weights.sharpeRatio
      totalWeight += weights.sharpeRatio
    }

    return totalWeight > 0 ? Math.round(score / totalWeight) : null
  }, [metrics])

  // Get overall risk level
  const overallRiskLevel = useMemo(() => {
    if (overallRiskScore == null) return { label: 'Unknown', color: 'slate' }
    if (overallRiskScore < 30) return { label: 'Low Risk', color: 'emerald' }
    if (overallRiskScore < 50) return { label: 'Moderate Risk', color: 'amber' }
    if (overallRiskScore < 70) return { label: 'Elevated Risk', color: 'orange' }
    return { label: 'High Risk', color: 'rose' }
  }, [overallRiskScore])

  if (loading) {
    return <RiskMetricsSkeleton />
  }

  return (
    <div
      className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-100">Risk Metrics</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Portfolio risk indicators and measurements
            </p>
          </div>

          {/* Overall Risk Score */}
          {overallRiskScore != null && (
            <div
              className="px-4 py-2 rounded-lg"
              style={{
                backgroundColor:
                  overallRiskLevel.color === 'emerald'
                    ? 'rgba(16, 185, 129, 0.15)'
                    : overallRiskLevel.color === 'amber'
                    ? 'rgba(245, 158, 11, 0.15)'
                    : overallRiskLevel.color === 'orange'
                    ? 'rgba(249, 115, 22, 0.15)'
                    : overallRiskLevel.color === 'rose'
                    ? 'rgba(244, 63, 94, 0.15)'
                    : 'rgba(100, 116, 139, 0.15)',
                borderWidth: 1,
                borderStyle: 'solid',
                borderColor:
                  overallRiskLevel.color === 'emerald'
                    ? 'rgba(16, 185, 129, 0.3)'
                    : overallRiskLevel.color === 'amber'
                    ? 'rgba(245, 158, 11, 0.3)'
                    : overallRiskLevel.color === 'orange'
                    ? 'rgba(249, 115, 22, 0.3)'
                    : overallRiskLevel.color === 'rose'
                    ? 'rgba(244, 63, 94, 0.3)'
                    : 'rgba(100, 116, 139, 0.3)',
              }}
            >
              <p className="text-[10px] text-slate-400 uppercase tracking-wide">Overall Risk</p>
              <div className="flex items-center gap-2">
                <span
                  className="text-xl font-bold"
                  style={{
                    color:
                      overallRiskLevel.color === 'emerald'
                        ? '#34d399'
                        : overallRiskLevel.color === 'amber'
                        ? '#fbbf24'
                        : overallRiskLevel.color === 'orange'
                        ? '#fb923c'
                        : overallRiskLevel.color === 'rose'
                        ? '#fb7185'
                        : '#94a3b8',
                  }}
                >
                  {overallRiskScore}
                </span>
                <span className="text-xs text-slate-400">/100</span>
              </div>
              <p
                className="text-xs font-medium"
                style={{
                  color:
                    overallRiskLevel.color === 'emerald'
                      ? '#34d399'
                      : overallRiskLevel.color === 'amber'
                      ? '#fbbf24'
                      : overallRiskLevel.color === 'orange'
                      ? '#fb923c'
                      : overallRiskLevel.color === 'rose'
                      ? '#fb7185'
                      : '#94a3b8',
                }}
              >
                {overallRiskLevel.label}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="p-5">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {/* VaR (95%) */}
          <RiskMetricCard
            title="VaR (95%)"
            value={metrics.var95}
            format="currency"
            metricType="var"
            description="Max daily loss at 95% confidence"
            maxGaugeValue={metrics.portfolioValue ? metrics.portfolioValue * 0.15 : 5000}
          />

          {/* CVaR (95%) */}
          <RiskMetricCard
            title="CVaR (95%)"
            value={metrics.cvar95}
            format="currency"
            metricType="cvar"
            description="Expected shortfall beyond VaR"
            maxGaugeValue={metrics.portfolioValue ? metrics.portfolioValue * 0.2 : 7500}
          />

          {/* Max Drawdown */}
          <RiskMetricCard
            title="Max Drawdown"
            value={metrics.maxDrawdownPercent}
            format="percent"
            metricType="maxDrawdown"
            description="Largest peak-to-trough decline"
            maxGaugeValue={30}
          />

          {/* Current Drawdown */}
          <RiskMetricCard
            title="Current Drawdown"
            value={metrics.currentDrawdown}
            format="percent"
            metricType="maxDrawdown"
            description="Current decline from peak"
            maxGaugeValue={30}
          />

          {/* Volatility */}
          <RiskMetricCard
            title="Volatility"
            value={metrics.volatility}
            format="percent"
            metricType="volatility"
            description="Annualized standard deviation"
            maxGaugeValue={60}
          />

          {/* Sharpe Ratio */}
          <RiskMetricCard
            title="Sharpe Ratio"
            value={metrics.sharpeRatio}
            format="ratio"
            metricType="sharpe"
            description="Risk-adjusted return"
            maxGaugeValue={4}
          />

          {/* Sortino Ratio */}
          <RiskMetricCard
            title="Sortino Ratio"
            value={metrics.sortinoRatio}
            format="ratio"
            metricType="sharpe"
            description="Downside risk-adjusted return"
            maxGaugeValue={4}
          />

          {/* Beta */}
          <RiskMetricCard
            title="Beta"
            value={metrics.beta}
            format="ratio"
            metricType="beta"
            description="Market sensitivity (vs BTC)"
            maxGaugeValue={2}
          />
        </div>

        {/* Risk Indicators Legend */}
        <div className="mt-6 pt-4 border-t border-slate-700/50">
          <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
            Risk Level Guide
          </h4>
          <div className="flex flex-wrap gap-4 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
              <span className="text-slate-400">Low Risk</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-amber-500"></span>
              <span className="text-slate-400">Moderate Risk</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-orange-500"></span>
              <span className="text-slate-400">Elevated Risk</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-rose-500"></span>
              <span className="text-slate-400">High/Critical Risk</span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-5 py-2 bg-slate-800/30 border-t border-slate-700/50">
        <p className="text-[10px] text-slate-500">
          Risk metrics are calculated based on historical trade data. Past performance does not
          guarantee future results.
        </p>
      </div>
    </div>
  )
}

// PropTypes
RiskMetrics.propTypes = {
  metrics: PropTypes.shape({
    var95: PropTypes.number,
    cvar95: PropTypes.number,
    maxDrawdown: PropTypes.number,
    maxDrawdownPercent: PropTypes.number,
    currentDrawdown: PropTypes.number,
    volatility: PropTypes.number,
    sharpeRatio: PropTypes.number,
    sortinoRatio: PropTypes.number,
    beta: PropTypes.number,
    portfolioValue: PropTypes.number,
  }),
  loading: PropTypes.bool,
  className: PropTypes.string,
}

export default RiskMetrics
