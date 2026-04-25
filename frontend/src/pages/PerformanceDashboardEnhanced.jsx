/**
 * PerformanceDashboardEnhanced.jsx - Comprehensive Performance Analytics Page
 *
 * Purpose: Enhanced dashboard page integrating all new performance analytics
 * components with real-time updates, date range selection, and export functionality.
 *
 * Features:
 * - Overview cards with prominent KPIs
 * - Detailed metrics grid with all statistics
 * - Equity curve with drawdown shading
 * - Daily P&L bar chart with cumulative line
 * - Returns distribution histogram
 * - Recent trades table with virtual scrolling
 * - Strategy performance breakdown
 * - Asset correlation heatmap
 * - Date range selector (1D, 7D, 30D, 90D, YTD, ALL)
 * - Export functionality (PDF, CSV)
 * - Real-time WebSocket updates
 * - Auto-refresh every 5 seconds
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState, useCallback, useMemo } from 'react'

// Hooks
import { usePerformanceMetrics } from '../hooks/usePerformanceMetrics'
import { useDateRange } from '../hooks/useDateRange'
import { useChartData, useDailyPnLChart } from '../hooks/useChartData'

// Performance components
import {
  EquityCurveChart,
  DrawdownChart,
  ReturnsDistribution,
  CorrelationHeatmap,
  DailyPnLChart,
  OverviewCards,
  MetricsGrid,
  RecentTrades,
  ExportButton,
} from '../components/performance'

// Import ExportPanel from PerformanceDashboard directory
import ExportPanel from '../components/PerformanceDashboard/ExportPanel'
import StrategyAttribution from '../components/PerformanceDashboard/StrategyAttribution'
import RiskMetrics from '../components/PerformanceDashboard/RiskMetrics'

// ============================================================================
// CONSTANTS
// ============================================================================

const AUTO_REFRESH_INTERVAL = 5000 // 5 seconds

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/**
 * Dashboard Header Component
 */
const DashboardHeader = ({
  dateRange,
  onPeriodChange,
  presetOptions,
  wsConnected,
  dataSource,
  lastUpdated,
  isLoading,
  onRefresh,
  onExport,
}) => (
  <header className="bg-slate-800/50 border-b border-slate-700/50 backdrop-blur-sm sticky top-0 z-40">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        {/* Title and Status */}
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            Performance Dashboard
          </h1>
          <div className="flex items-center gap-4 mt-1">
            {/* Connection Status */}
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
                }`}
              ></span>
              <span className="text-xs text-slate-400">
                {wsConnected ? `Live (${dataSource})` : 'Polling'}
              </span>
            </div>

            {/* Last Updated */}
            {lastUpdated && (
              <span className="text-xs text-slate-500">
                Updated: {new Date(lastUpdated).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Period Selector */}
          <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
            {presetOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => onPeriodChange(option.value)}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  option.isActive
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {option.shortLabel}
              </button>
            ))}
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-300 bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
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

          {/* Export Button */}
          <ExportButton
            onOpenModal={onExport}
            variant="default"
          />
        </div>
      </div>
    </div>
  </header>
)

/**
 * Section Header Component
 */
const SectionHeader = ({ title, description, children }) => (
  <div className="flex items-center justify-between mb-4">
    <div>
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      {description && (
        <p className="text-sm text-slate-500 mt-0.5">{description}</p>
      )}
    </div>
    {children}
  </div>
)

/**
 * Error Display Component
 */
const ErrorDisplay = ({ error, onRetry }) => (
  <div className="bg-rose-900/20 border border-rose-500/30 rounded-lg p-6 text-center">
    <svg
      className="w-12 h-12 text-rose-400 mx-auto mb-4"
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
    <h3 className="text-lg font-semibold text-rose-300 mb-2">
      Error Loading Performance Data
    </h3>
    <p className="text-sm text-rose-400/80 mb-4">
      {error?.message || 'An unexpected error occurred'}
    </p>
    <button
      onClick={onRetry}
      className="px-4 py-2 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded-lg transition-colors"
    >
      Retry
    </button>
  </div>
)

/**
 * No Data Placeholder
 */
const NoDataPlaceholder = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-8 text-center">
    <svg
      className="w-16 h-16 text-slate-600 mx-auto mb-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
      />
    </svg>
    <h3 className="text-xl font-semibold text-slate-300 mb-2">
      No Trading Data Yet
    </h3>
    <p className="text-sm text-slate-500 max-w-md mx-auto">
      Performance metrics will appear once trades are executed. Start the auto
      trader or execute manual trades to see your performance analytics.
    </p>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * PerformanceDashboardEnhanced - Main Enhanced Performance Dashboard Page
 */
export default function PerformanceDashboardEnhanced() {
  // Date range management
  const {
    preset: period,
    setPreset,
    presetOptions,
    queryParams,
  } = useDateRange({
    defaultPreset: '30d',
    persist: true,
  })

  // Export panel state
  const [showExportPanel, setShowExportPanel] = useState(false)

  // Selected trade state
  const [selectedTrade, setSelectedTrade] = useState(null)

  // Fetch performance metrics
  const {
    isLoading,
    isError,
    error,
    wsConnected,
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
    pollingInterval: AUTO_REFRESH_INTERVAL,
    enableWebSocket: true,
  })

  // Transform data for charts
  const chartData = useChartData({
    trades,
    equityCurve,
    initialBalance: 10000,
    period,
  })

  // Daily P&L chart data
  const dailyPnLData = useDailyPnLChart(trades)

  // Determine if we have data
  const hasData = tradeCount > 0 || equityCurve.length > 0

  // Calculate overview metrics for cards
  const overviewMetrics = useMemo(() => {
    if (!metrics) return {}

    // Calculate today's P&L from trades
    const today = new Date().toISOString().split('T')[0]
    const todayTrades = trades.filter((t) => {
      const tradeDate = new Date(t.closed_at || t.timestamp).toISOString().split('T')[0]
      return tradeDate === today
    })
    const todayPnL = todayTrades.reduce(
      (sum, t) => sum + parseFloat(t.realized_pnl || 0),
      0
    )

    // Calculate week's P&L
    const oneWeekAgo = new Date()
    oneWeekAgo.setDate(oneWeekAgo.getDate() - 7)
    const weekTrades = trades.filter((t) => {
      const tradeDate = new Date(t.closed_at || t.timestamp)
      return tradeDate >= oneWeekAgo
    })
    const weekPnL = weekTrades.reduce(
      (sum, t) => sum + parseFloat(t.realized_pnl || 0),
      0
    )

    return {
      totalPnL: metrics.totalPnL,
      totalPnLChange: metrics.totalPnLChange,
      winRate: metrics.winRate,
      totalTrades: metrics.totalTrades,
      sharpeRatio: metrics.sharpeRatio,
      sharpeChange: metrics.sharpeChange,
      activePositions: metrics.activePositions || 0,
      activePositionsValue: metrics.activePositionsValue,
      todayPnL,
      todayTrades: todayTrades.length,
      weekPnL,
      weekPnLChange: metrics.weekPnLChange,
    }
  }, [metrics, trades])

  // Calculate detailed metrics for grid
  const detailedMetrics = useMemo(() => {
    if (!metrics) return {}

    return {
      // Risk-adjusted metrics
      sharpeRatio: metrics.sharpeRatio,
      sortinoRatio: metrics.sortinoRatio,
      calmarRatio: metrics.calmarRatio,
      profitFactor: metrics.profitFactor,
      expectancy: metrics.expectancy,
      recoveryFactor: metrics.recoveryFactor,

      // Drawdown metrics
      maxDrawdown: metrics.maxDrawdown,
      maxDrawdownPercent: metrics.maxDrawdownPercent,
      avgDrawdown: metrics.avgDrawdown,
      currentDrawdown:
        drawdownSeries.length > 0
          ? drawdownSeries[drawdownSeries.length - 1]?.drawdownPercent
          : 0,
      maxDrawdownDuration: metrics.maxDrawdownDuration,

      // Win/Loss statistics
      totalTrades: metrics.totalTrades,
      winningTrades: metrics.winningTrades,
      losingTrades: metrics.losingTrades,
      winRate: metrics.winRate,
      avgWin: metrics.avgWin,
      avgLoss: metrics.avgLoss,
      largestWin: metrics.largestWin,
      largestLoss: metrics.largestLoss,
      consecutiveWins: metrics.consecutiveWins,
      consecutiveLosses: metrics.consecutiveLosses,

      // P&L metrics
      totalPnL: metrics.totalPnL,
      grossProfit: metrics.grossProfit,
      grossLoss: metrics.grossLoss,
      avgPnL: metrics.avgPnL,

      // Risk metrics
      var95: metrics.var95,
      cvar95: metrics.cvar95,
      var99: metrics.var99,
      stdDev: metrics.stdDev,
      volatility: metrics.volatility,
      downsideDeviation: metrics.downsideDeviation,
    }
  }, [metrics, drawdownSeries])

  // Calculate strategy attribution data
  const strategyData = useMemo(() => {
    if (!trades || trades.length === 0) return []

    const strategyMap = new Map()

    trades.forEach((trade) => {
      const strategy = trade.strategy || trade.signal_source || 'Unknown'

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
      const pnl = parseFloat(trade.realized_pnl || 0)
      stats.trades += 1
      stats.pnl += pnl

      if (pnl > 0) {
        stats.wins += 1
        stats.grossProfit += pnl
      } else if (pnl < 0) {
        stats.losses += 1
        stats.grossLoss += Math.abs(pnl)
      }
    })

    return Array.from(strategyMap.values()).map((stats) => ({
      ...stats,
      winRate: stats.trades > 0 ? (stats.wins / stats.trades) * 100 : 0,
      profitFactor:
        stats.grossLoss > 0
          ? stats.grossProfit / stats.grossLoss
          : stats.grossProfit > 0
          ? 999
          : 0,
      avgWin: stats.wins > 0 ? stats.grossProfit / stats.wins : 0,
      avgLoss: stats.losses > 0 ? stats.grossLoss / stats.losses : 0,
    }))
  }, [trades])

  // Risk metrics for RiskMetrics component
  const riskMetrics = useMemo(
    () => ({
      var95: metrics?.var95,
      cvar95: metrics?.cvar95,
      maxDrawdownPercent: metrics?.maxDrawdownPercent,
      currentDrawdown:
        drawdownSeries.length > 0
          ? drawdownSeries[drawdownSeries.length - 1]?.drawdownPercent
          : 0,
      volatility: metrics?.volatility,
      sharpeRatio: metrics?.sharpeRatio,
      sortinoRatio: metrics?.sortinoRatio,
      portfolioValue:
        equityCurve.length > 0
          ? equityCurve[equityCurve.length - 1]?.equity
          : 10000,
    }),
    [metrics, drawdownSeries, equityCurve]
  )

  // Export data
  const exportData = useMemo(
    () => ({
      metrics,
      equityCurve,
      drawdownSeries,
      returnsDistribution,
      strategyData,
      trades,
      period,
      generatedAt: new Date().toISOString(),
    }),
    [
      metrics,
      equityCurve,
      drawdownSeries,
      returnsDistribution,
      strategyData,
      trades,
      period,
    ]
  )

  // Handle trade click
  const handleTradeClick = useCallback((trade) => {
    setSelectedTrade(trade)
    // Could open a trade detail modal here
  }, [])

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Dashboard Header */}
      <DashboardHeader
        dateRange={{ preset: period }}
        onPeriodChange={setPreset}
        presetOptions={presetOptions}
        wsConnected={wsConnected}
        dataSource={dataSource}
        lastUpdated={metrics?.lastUpdated}
        isLoading={isLoading}
        onRefresh={refresh}
        onExport={() => setShowExportPanel(true)}
      />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Error State */}
        {isError && <ErrorDisplay error={error} onRetry={refresh} />}

        {/* No Data State */}
        {!isLoading && !isError && !hasData && <NoDataPlaceholder />}

        {/* Dashboard Content */}
        {(hasData || isLoading) && (
          <div className="space-y-6">
            {/* ============================================================ */}
            {/* OVERVIEW SECTION */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Overview"
                description="Key performance indicators at a glance"
              />
              <OverviewCards metrics={overviewMetrics} loading={isLoading} />
            </section>

            {/* ============================================================ */}
            {/* EQUITY CURVE SECTION */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Portfolio Performance"
                description="Equity curve showing portfolio value over time"
              />
              <EquityCurveChart
                data={equityCurve}
                loading={isLoading}
                period={period}
                onPeriodChange={setPreset}
                height={350}
              />
            </section>

            {/* ============================================================ */}
            {/* DAILY P&L + DRAWDOWN - TWO COLUMN LAYOUT */}
            {/* ============================================================ */}
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <SectionHeader
                  title="Daily P&L"
                  description="Daily profit and loss with cumulative view"
                />
                <DailyPnLChart
                  data={dailyPnLData}
                  loading={isLoading}
                  period={period}
                  showCumulative={true}
                  height={280}
                />
              </div>

              <div>
                <SectionHeader
                  title="Drawdown Analysis"
                  description="Peak-to-trough portfolio decline"
                />
                <DrawdownChart
                  data={drawdownSeries}
                  loading={isLoading}
                  period={period}
                  height={280}
                />
              </div>
            </section>

            {/* ============================================================ */}
            {/* DETAILED METRICS GRID */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Detailed Metrics"
                description="Comprehensive performance statistics and risk analysis"
              />
              <MetricsGrid metrics={detailedMetrics} loading={isLoading} />
            </section>

            {/* ============================================================ */}
            {/* RETURNS DISTRIBUTION + STRATEGY ATTRIBUTION */}
            {/* ============================================================ */}
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <SectionHeader
                  title="Returns Distribution"
                  description="Histogram of trade P&L outcomes"
                />
                <ReturnsDistribution
                  bins={returnsDistribution?.bins}
                  stats={returnsDistribution?.stats}
                  loading={isLoading}
                  height={280}
                />
              </div>

              <div>
                <SectionHeader
                  title="Strategy Performance"
                  description="Performance breakdown by trading strategy"
                />
                <StrategyAttribution
                  data={strategyData}
                  loading={isLoading}
                  height={280}
                />
              </div>
            </section>

            {/* ============================================================ */}
            {/* RECENT TRADES TABLE */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Recent Trades"
                description="Last 50 trades with detailed information"
              />
              <RecentTrades
                trades={trades}
                loading={isLoading}
                maxHeight={450}
                onTradeClick={handleTradeClick}
              />
            </section>

            {/* ============================================================ */}
            {/* RISK METRICS + CORRELATION */}
            {/* ============================================================ */}
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <SectionHeader
                  title="Risk Analysis"
                  description="Portfolio risk indicators"
                />
                <RiskMetrics metrics={riskMetrics} loading={isLoading} />
              </div>

              <div>
                <SectionHeader
                  title="Asset Correlations"
                  description="Correlation matrix between traded pairs"
                />
                <CorrelationHeatmap
                  loading={isLoading}
                  useMockData={true}
                  cellSize="default"
                />
              </div>
            </section>

            {/* ============================================================ */}
            {/* FOOTER INFO */}
            {/* ============================================================ */}
            <section className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div className="text-xs text-slate-500">
                  <p>
                    Data refreshes every {AUTO_REFRESH_INTERVAL / 1000} seconds |
                    {tradeCount} trades analyzed | Period: {period}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <button
                    onClick={refresh}
                    disabled={isLoading}
                    className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors disabled:opacity-50"
                  >
                    Force Refresh
                  </button>
                  <button
                    onClick={() => setShowExportPanel(true)}
                    className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    Export All Data
                  </button>
                </div>
              </div>
            </section>
          </div>
        )}
      </main>

      {/* Export Panel Modal */}
      {showExportPanel && (
        <ExportPanel data={exportData} onClose={() => setShowExportPanel(false)} />
      )}
    </div>
  )
}
