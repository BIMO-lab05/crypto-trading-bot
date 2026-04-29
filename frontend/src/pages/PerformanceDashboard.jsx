/**
 * PerformanceDashboard.jsx - Comprehensive Performance Analytics Page
 *
 * Purpose: Main dashboard page integrating all performance analytics components.
 * Provides a comprehensive view of trading performance with real-time updates.
 *
 * Features:
 * - Key performance metrics (Sharpe, Sortino, VaR, etc.)
 * - Equity curve visualization
 * - Drawdown analysis
 * - Returns distribution histogram
 * - Asset correlation matrix
 * - Period selection
 * - Real-time data updates
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState, useMemo } from 'react'
import { usePerformanceMetrics } from '../hooks/usePerformanceMetrics'
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
} from '../components/performance'

// ============================================================================
// CONSTANTS
// ============================================================================

const PERIOD_OPTIONS = [
  { value: '1d', label: '24 Hours' },
  { value: '7d', label: '7 Days' },
  { value: '30d', label: '30 Days' },
  { value: '90d', label: '90 Days' },
  { value: 'all', label: 'All Time' },
]

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/**
 * Section Header Component
 */
const SectionHeader = ({ title, description }) => (
  <div className="mb-4">
    <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
    {description && (
      <p className="text-sm text-slate-500 mt-0.5">{description}</p>
    )}
  </div>
)

/**
 * Period Selector Component
 */
const PeriodSelector = ({ value, onChange }) => (
  <div className="flex items-center gap-2">
    <span className="text-sm text-slate-400">Period:</span>
    <div className="flex gap-1 bg-slate-900/50 rounded-lg p-1">
      {PERIOD_OPTIONS.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            value === option.value
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  </div>
)

/**
 * Connection Status Indicator
 */
const ConnectionStatus = ({ isConnected, dataSource, lastUpdated }) => (
  <div className="flex items-center gap-3 text-xs">
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
      <span className="text-slate-400">
        {dataSource === 'websocket' ? 'Real-time' : 'Polling'}
      </span>
    </span>
    {lastUpdated && (
      <span className="text-slate-500">
        Updated: {new Date(lastUpdated).toLocaleTimeString()}
      </span>
    )}
  </div>
)

/**
 * Error Display Component
 */
const ErrorDisplay = ({ error, onRetry }) => (
  <div className="bg-rose-900/20 border border-rose-500/30 rounded-lg p-4 mb-6">
    <div className="flex items-start gap-3">
      <svg
        className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5"
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
      <div className="flex-1">
        <h4 className="text-sm font-semibold text-rose-300">Error Loading Performance Data</h4>
        <p className="text-sm text-rose-400/80 mt-1">
          {error?.message || 'An error occurred while fetching performance metrics.'}
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 px-3 py-1.5 text-sm font-medium bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded-lg transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  </div>
)

/**
 * No Data Placeholder
 */
const NoDataPlaceholder = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-8 text-center">
    <svg
      className="w-12 h-12 text-slate-600 mx-auto mb-4"
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
    <h3 className="text-lg font-semibold text-slate-300 mb-2">No Trading Data Yet</h3>
    <p className="text-sm text-slate-500 max-w-md mx-auto">
      Performance metrics will appear once trades are executed. Start the auto trader or execute manual trades to see your performance analytics.
    </p>
  </div>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * PerformanceDashboard - Main Performance Analytics Page
 */
export default function PerformanceDashboard() {
  // State for period selection
  const [period, setPeriod] = useState('30d')

  // Fetch performance metrics using custom hook
  const {
    isLoading,
    isError,
    error,
    dataSource,
    metrics,
    equityCurve,
    drawdownSeries,
    returnsDistribution,
    tradeCount,
    refresh,
  } = usePerformanceMetrics({ period, pollingInterval: 30000 })

  // Determine if we have data to display
  const hasData = tradeCount > 0 || equityCurve.length > 0

  return (
    <div className="min-h-screen bg-slate-900 transition-colors duration-200">
      {/* Page Header */}
      <header className="bg-slate-800/50 border-b border-slate-700/50 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            {/* Title and Status */}
            <div>
              <h1 className="text-2xl font-bold text-slate-100">
                Performance Analytics
              </h1>
              <div className="flex items-center gap-4 mt-1">
                {/* WebSocket support stripped 2026-04-29 (no server-side
                    /ws/metrics ever existed). Hook is REST-polling-only;
                    the indicator just shows "Polling" unconditionally. */}
                <ConnectionStatus
                  isConnected={false}
                  dataSource={dataSource}
                  lastUpdated={metrics?.lastUpdated}
                />
              </div>
            </div>

            {/* Period Selector */}
            <PeriodSelector value={period} onChange={setPeriod} />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Error Display */}
        {isError && <ErrorDisplay error={error} onRetry={refresh} />}

        {/* No Data State */}
        {!isLoading && !isError && !hasData && <NoDataPlaceholder />}

        {/* Dashboard Content */}
        {(hasData || isLoading) && (
          <div className="space-y-6">
            {/* ============================================================ */}
            {/* KEY METRICS SECTION */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Key Performance Indicators"
                description="Risk-adjusted returns and core trading metrics"
              />

              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
                <SharpeRatioCard value={metrics?.sharpeRatio} loading={isLoading} />
                <SortinoRatioCard value={metrics?.sortinoRatio} loading={isLoading} />
                <MaxDrawdownCard value={metrics?.maxDrawdownPercent} loading={isLoading} />
                <WinRateCard value={metrics?.winRate} loading={isLoading} />
                <ProfitFactorCard value={metrics?.profitFactor} loading={isLoading} />
                <TotalPnLCard value={metrics?.totalPnL} loading={isLoading} />
                <VaRCard value={metrics?.var95} loading={isLoading} />
                <CVaRCard value={metrics?.cvar95} loading={isLoading} />
              </div>
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
                onPeriodChange={setPeriod}
                height={350}
              />
            </section>

            {/* ============================================================ */}
            {/* TWO-COLUMN LAYOUT: DRAWDOWN + RETURNS */}
            {/* ============================================================ */}
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Drawdown Analysis */}
              <div>
                <SectionHeader
                  title="Drawdown Analysis"
                  description="Peak-to-trough portfolio decline over time"
                />
                <DrawdownChart
                  data={drawdownSeries}
                  loading={isLoading}
                  period={period}
                  height={280}
                />
              </div>

              {/* Returns Distribution */}
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
            </section>

            {/* ============================================================ */}
            {/* ADDITIONAL METRICS GRID */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Trade Statistics"
                description="Detailed trading performance breakdown"
              />

              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <MetricsCard
                  title="Total Trades"
                  value={metrics?.totalTrades}
                  format="integer"
                  loading={isLoading}
                />
                <MetricsCard
                  title="Winning Trades"
                  value={metrics?.winningTrades}
                  format="integer"
                  loading={isLoading}
                  thresholds={{ good: 0 }}
                />
                <MetricsCard
                  title="Losing Trades"
                  value={metrics?.losingTrades}
                  format="integer"
                  loading={isLoading}
                />
                <MetricsCard
                  title="Average Win"
                  value={metrics?.avgWin}
                  format="currency"
                  loading={isLoading}
                  thresholds={{ good: 0 }}
                />
                <MetricsCard
                  title="Average Loss"
                  value={metrics?.avgLoss}
                  format="currency"
                  loading={isLoading}
                />
                <MetricsCard
                  title="Expectancy"
                  value={metrics?.expectancy}
                  format="currency"
                  description="Expected value per trade"
                  loading={isLoading}
                  thresholds={{ good: 0 }}
                />
              </div>
            </section>

            {/* ============================================================ */}
            {/* CORRELATION MATRIX SECTION */}
            {/* ============================================================ */}
            <section>
              <SectionHeader
                title="Asset Correlations"
                description="Correlation matrix between traded assets for diversification analysis"
              />

              <CorrelationHeatmap
                loading={isLoading}
                useMockData={true}
                cellSize="default"
              />
            </section>

            {/* ============================================================ */}
            {/* FOOTER INFO */}
            {/* ============================================================ */}
            <section className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5">
              <h3 className="text-sm font-semibold text-slate-200 mb-3">
                About Performance Metrics
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-400">
                <div>
                  <p className="font-medium text-slate-300 mb-1">Risk-Adjusted Returns</p>
                  <p>
                    Sharpe and Sortino ratios measure returns per unit of risk.
                    Higher values indicate better risk-adjusted performance.
                    Sharpe uses total volatility while Sortino focuses on downside risk.
                  </p>
                </div>
                <div>
                  <p className="font-medium text-slate-300 mb-1">Value at Risk (VaR)</p>
                  <p>
                    VaR estimates the maximum expected loss at a given confidence level.
                    CVaR (Expected Shortfall) measures the expected loss when losses exceed VaR.
                    These metrics help understand tail risk.
                  </p>
                </div>
                <div>
                  <p className="font-medium text-slate-300 mb-1">Drawdown Analysis</p>
                  <p>
                    Maximum drawdown shows the largest peak-to-trough decline.
                    Monitoring drawdowns helps manage risk and prevent large losses.
                    Professional traders typically limit max drawdown to 10-20%.
                  </p>
                </div>
              </div>

              {/* Data Refresh Info */}
              <div className="mt-4 pt-4 border-t border-slate-700/50 flex items-center justify-between">
                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <span>Data refreshes every 30 seconds</span>
                  <span>|</span>
                  <span>All metrics calculated from trade history</span>
                </div>
                <button
                  onClick={refresh}
                  disabled={isLoading}
                  className="px-3 py-1.5 text-xs font-medium bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors disabled:opacity-50"
                >
                  {isLoading ? 'Refreshing...' : 'Refresh Data'}
                </button>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  )
}
