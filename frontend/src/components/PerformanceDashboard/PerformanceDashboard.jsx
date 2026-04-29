/**
 * PerformanceDashboard.jsx - Main Performance Dashboard Container
 *
 * Purpose: Main container component that orchestrates all performance metrics
 * components and provides a comprehensive real-time trading performance view.
 *
 * Features:
 * - Real-time performance metrics via WebSocket
 * - Multiple time period selection
 * - Collapsible sections for customization
 * - Export functionality (CSV/PDF)
 * - Responsive layout
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState, useCallback, useMemo } from 'react'
import PropTypes from 'prop-types'

// Import hooks
import { usePerformanceMetrics } from '../../hooks/usePerformanceMetrics'

// Import existing performance components from performance directory
import {
  MetricsCard,
  SharpeRatioCard,
  SortinoRatioCard,
  MaxDrawdownCard,
  WinRateCard,
  ProfitFactorCard,
  TotalPnLCard,
  VaRCard,
  CVaRCard,
  EquityCurveChart,
  DrawdownChart,
  ReturnsDistribution,
  CorrelationHeatmap,
} from '../performance'

// Import local components
import StrategyAttribution from './StrategyAttribution'
import RiskMetrics from './RiskMetrics'
import ExportPanel from './ExportPanel'

// ============================================================================
// CONSTANTS
// ============================================================================

const TIME_PERIODS = [
  { value: '1d', label: '1D', description: 'Last 24 hours' },
  { value: '7d', label: '7D', description: 'Last 7 days' },
  { value: '30d', label: '30D', description: 'Last 30 days' },
  { value: '90d', label: '90D', description: 'Last 90 days' },
  { value: 'all', label: 'All', description: 'All time' },
]

// ============================================================================
// SECTION HEADER COMPONENT
// ============================================================================

const SectionHeader = ({ title, description, isCollapsed, onToggle, actions }) => (
  <div className="flex items-center justify-between mb-4">
    <div className="flex items-center gap-3">
      <button
        onClick={onToggle}
        className="text-slate-400 hover:text-slate-200 transition-colors"
        aria-label={isCollapsed ? 'Expand section' : 'Collapse section'}
      >
        <svg
          className={`w-5 h-5 transition-transform ${isCollapsed ? '-rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div>
        <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
        {description && <p className="text-xs text-slate-500">{description}</p>}
      </div>
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
)

// ============================================================================
// CONNECTION STATUS INDICATOR
// ============================================================================

const ConnectionStatus = ({ isConnected, dataSource }) => (
  <div className="flex items-center gap-2">
    <span
      className={`w-2 h-2 rounded-full ${
        isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-500'
      }`}
    ></span>
    <span className="text-xs text-slate-400">
      {isConnected ? `Live (${dataSource})` : 'Polling'}
    </span>
  </div>
)

// ============================================================================
// REFRESH BUTTON
// ============================================================================

const RefreshButton = ({ onClick, isLoading }) => (
  <button
    onClick={onClick}
    disabled={isLoading}
    className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-300 bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
  >
    <svg
      className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
      />
    </svg>
    Refresh
  </button>
)

// ============================================================================
// TIME PERIOD SELECTOR
// ============================================================================

const PeriodSelector = ({ value, onChange }) => (
  <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
    {TIME_PERIODS.map((option) => (
      <button
        key={option.value}
        onClick={() => onChange(option.value)}
        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
          value === option.value
            ? 'bg-slate-700 text-slate-100'
            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
        }`}
        title={option.description}
      >
        {option.label}
      </button>
    ))}
  </div>
)

// ============================================================================
// METRICS OVERVIEW GRID
// ============================================================================

const MetricsOverview = ({ metrics, loading }) => (
  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
    <TotalPnLCard value={metrics?.totalPnL} loading={loading} variant="compact" />
    <WinRateCard value={metrics?.winRate} loading={loading} variant="compact" />
    <ProfitFactorCard value={metrics?.profitFactor} loading={loading} variant="compact" />
    <SharpeRatioCard value={metrics?.sharpeRatio} loading={loading} variant="compact" />
    <SortinoRatioCard value={metrics?.sortinoRatio} loading={loading} variant="compact" />
    <MaxDrawdownCard value={metrics?.maxDrawdownPercent} loading={loading} variant="compact" />
    <VaRCard value={metrics?.var95} loading={loading} variant="compact" />
    <MetricsCard
      title="Trades"
      value={metrics?.totalTrades}
      format="integer"
      loading={loading}
      variant="compact"
    />
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * PerformanceDashboard - Main Dashboard Container
 *
 * @param {Object} props - Component props
 * @param {string} props.className - Additional CSS classes
 * @param {number} props.pollingInterval - Polling interval in ms
 */
function PerformanceDashboard({
  className = '',
  pollingInterval = 30000,
}) {
  // State for period selection
  const [period, setPeriod] = useState('30d')

  // State for collapsed sections
  const [collapsedSections, setCollapsedSections] = useState({
    overview: false,
    equity: false,
    drawdown: false,
    distribution: false,
    strategy: false,
    risk: false,
    correlation: false,
  })

  // State for export panel
  const [showExportPanel, setShowExportPanel] = useState(false)

  // Fetch performance data using hook
  const {
    isLoading,
    isError,
    error,
    dataSource,
    metrics,
    equityCurve,
    drawdownSeries,
    returnsDistribution,
    trades,
    tradeCount,
    refresh,
  } = usePerformanceMetrics({
    period,
    pollingInterval,
  })

  // Toggle section collapse
  const toggleSection = useCallback((section) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }))
  }, [])

  // Handle period change
  const handlePeriodChange = useCallback((newPeriod) => {
    setPeriod(newPeriod)
  }, [])

  // Calculate strategy attribution data from trades
  const strategyData = useMemo(() => {
    if (!trades || trades.length === 0) return []

    // Group trades by strategy
    const strategyMap = new Map()

    trades.forEach((trade) => {
      const strategy = trade.strategy || trade.signal_type || 'Unknown'
      if (!strategyMap.has(strategy)) {
        strategyMap.set(strategy, {
          strategy,
          trades: 0,
          wins: 0,
          losses: 0,
          pnl: 0,
          grossProfit: 0,
          grossLoss: 0,
        })
      }

      const stats = strategyMap.get(strategy)
      stats.trades += 1
      const pnl = parseFloat(trade.realized_pnl || 0)
      stats.pnl += pnl

      if (pnl > 0) {
        stats.wins += 1
        stats.grossProfit += pnl
      } else if (pnl < 0) {
        stats.losses += 1
        stats.grossLoss += Math.abs(pnl)
      }
    })

    // Calculate derived metrics
    return Array.from(strategyMap.values()).map((stats) => ({
      ...stats,
      winRate: stats.trades > 0 ? (stats.wins / stats.trades) * 100 : 0,
      profitFactor: stats.grossLoss > 0 ? stats.grossProfit / stats.grossLoss : stats.grossProfit > 0 ? Infinity : 0,
      avgWin: stats.wins > 0 ? stats.grossProfit / stats.wins : 0,
      avgLoss: stats.losses > 0 ? stats.grossLoss / stats.losses : 0,
    }))
  }, [trades])

  // Prepare risk metrics object
  const riskMetrics = useMemo(() => ({
    var95: metrics?.var95,
    cvar95: metrics?.cvar95,
    maxDrawdownPercent: metrics?.maxDrawdownPercent,
    currentDrawdown: drawdownSeries.length > 0
      ? drawdownSeries[drawdownSeries.length - 1]?.drawdownPercent
      : 0,
    volatility: metrics?.stdDev ? metrics.stdDev * Math.sqrt(252) : null, // Annualized
    sharpeRatio: metrics?.sharpeRatio,
    sortinoRatio: metrics?.sortinoRatio,
    beta: null, // Would need market data to calculate
    portfolioValue: equityCurve.length > 0
      ? equityCurve[equityCurve.length - 1]?.equity
      : 10000,
  }), [metrics, drawdownSeries, equityCurve])

  // Prepare export data
  const exportData = useMemo(() => ({
    metrics,
    equityCurve,
    drawdownSeries,
    returnsDistribution,
    strategyData,
    trades,
    period,
    generatedAt: new Date().toISOString(),
  }), [metrics, equityCurve, drawdownSeries, returnsDistribution, strategyData, trades, period])

  // Error state
  if (isError) {
    return (
      <div className={`bg-slate-800/30 rounded-lg border border-rose-500/30 p-8 ${className}`}>
        <div className="flex flex-col items-center justify-center text-center">
          <svg
            className="w-12 h-12 text-rose-400 mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <h3 className="text-lg font-semibold text-rose-400 mb-2">Error Loading Performance Data</h3>
          <p className="text-sm text-slate-400 mb-4">{error?.message || 'An unexpected error occurred'}</p>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Dashboard Header */}
      <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-4">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-100">Performance Dashboard</h1>
            <p className="text-sm text-slate-400 mt-1">
              Real-time trading performance metrics and analytics
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            {/* Hook is REST-polling-only after the WebSocket strip;
                show "Polling" indicator unconditionally. */}
            <ConnectionStatus isConnected={false} dataSource={dataSource} />
            <PeriodSelector value={period} onChange={handlePeriodChange} />
            <RefreshButton onClick={refresh} isLoading={isLoading} />
            <button
              onClick={() => setShowExportPanel(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-300 bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              Export
            </button>
          </div>
        </div>
      </div>

      {/* Metrics Overview Section */}
      <section>
        <SectionHeader
          title="Key Metrics"
          description="At-a-glance performance indicators"
          isCollapsed={collapsedSections.overview}
          onToggle={() => toggleSection('overview')}
        />
        {!collapsedSections.overview && (
          <MetricsOverview metrics={metrics} loading={isLoading} />
        )}
      </section>

      {/* Equity Curve Section */}
      <section>
        <SectionHeader
          title="Equity Curve"
          description="Portfolio value over time"
          isCollapsed={collapsedSections.equity}
          onToggle={() => toggleSection('equity')}
        />
        {!collapsedSections.equity && (
          <EquityCurveChart
            data={equityCurve}
            loading={isLoading}
            period={period}
            onPeriodChange={handlePeriodChange}
            height={350}
          />
        )}
      </section>

      {/* Drawdown Section */}
      <section>
        <SectionHeader
          title="Drawdown Analysis"
          description="Peak-to-trough portfolio decline"
          isCollapsed={collapsedSections.drawdown}
          onToggle={() => toggleSection('drawdown')}
        />
        {!collapsedSections.drawdown && (
          <DrawdownChart
            data={drawdownSeries}
            loading={isLoading}
            period={period}
            height={300}
          />
        )}
      </section>

      {/* Returns Distribution Section */}
      <section>
        <SectionHeader
          title="Returns Distribution"
          description="Statistical analysis of trade returns"
          isCollapsed={collapsedSections.distribution}
          onToggle={() => toggleSection('distribution')}
        />
        {!collapsedSections.distribution && (
          <ReturnsDistribution
            bins={returnsDistribution.bins}
            stats={returnsDistribution.stats}
            loading={isLoading}
            height={280}
          />
        )}
      </section>

      {/* Strategy Attribution Section */}
      <section>
        <SectionHeader
          title="Strategy Attribution"
          description="Performance breakdown by trading strategy"
          isCollapsed={collapsedSections.strategy}
          onToggle={() => toggleSection('strategy')}
        />
        {!collapsedSections.strategy && (
          <StrategyAttribution
            data={strategyData}
            loading={isLoading}
            height={300}
          />
        )}
      </section>

      {/* Risk Metrics Section */}
      <section>
        <SectionHeader
          title="Risk Analysis"
          description="Portfolio risk indicators and measurements"
          isCollapsed={collapsedSections.risk}
          onToggle={() => toggleSection('risk')}
        />
        {!collapsedSections.risk && (
          <RiskMetrics
            metrics={riskMetrics}
            loading={isLoading}
          />
        )}
      </section>

      {/* Correlation Heatmap Section (if available) */}
      <section>
        <SectionHeader
          title="Asset Correlations"
          description="Correlation matrix between traded assets"
          isCollapsed={collapsedSections.correlation}
          onToggle={() => toggleSection('correlation')}
        />
        {!collapsedSections.correlation && (
          <CorrelationHeatmap
            loading={isLoading}
            period={period}
          />
        )}
      </section>

      {/* Export Panel Modal */}
      {showExportPanel && (
        <ExportPanel
          data={exportData}
          onClose={() => setShowExportPanel(false)}
        />
      )}

      {/* Footer */}
      <div className="text-center text-xs text-slate-500 py-4">
        <p>
          Data updated: {new Date(metrics?.lastUpdated || Date.now()).toLocaleString()} |
          Trades analyzed: {tradeCount} |
          Period: {TIME_PERIODS.find((p) => p.value === period)?.description}
        </p>
      </div>
    </div>
  )
}

// PropTypes
PerformanceDashboard.propTypes = {
  className: PropTypes.string,
  pollingInterval: PropTypes.number,
}

export default PerformanceDashboard
