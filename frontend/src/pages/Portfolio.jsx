/**
 * Portfolio.jsx - Portfolio Management Page with Dark Mode Support
 *
 * Purpose: Displays comprehensive portfolio information including:
 * - Total balance and value summary cards
 * - Asset allocation pie chart
 * - Holdings table with position details
 * - P&L history and performance metrics
 *
 * Features:
 * - Full dark mode support with smooth transitions
 * - Real-time data updates
 * - Responsive design for all screen sizes
 * - Financial data color coding (profit/loss)
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

import React, { useMemo } from 'react';
import { useTheme } from '../contexts/ThemeContext.tsx';
import { usePortfolio, usePortfolioPerformance, useTradeHistory } from '../hooks/usePortfolio';
import { usePositions, useTradingStatus } from '../hooks/usePositions';
import TileState from '../components/TileState';

/**
 * Plan 06-05 DASH-05: this page is audit-verdict LABELED_STALE because
 * /api/portfolio returns 503 (portfolio-manager container 'unhealthy'
 * at audit time, 2026-05-13). Other hooks (positions/status/perf) are
 * 200. The portfolioQuery drives the <TileState forceStale/> wrapper
 * below — if /api/portfolio is 503 the Failed (...) UI takes precedence
 * (F-05). When portfolio-manager is restored, the page renders normally
 * with a corner stale badge until Phase 7+ removes the forceStale flag.
 */

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Formats a number as currency with proper sign and decimals
 * @param {number} value - The value to format
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted currency string
 */
const formatCurrency = (value, decimals = 2) => {
  const num = parseFloat(value) || 0;
  return `$${num.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
};

/**
 * Formats a percentage value with sign
 * @param {number} value - The percentage value
 * @returns {string} Formatted percentage string
 */
const formatPercentage = (value) => {
  const num = parseFloat(value) || 0;
  const sign = num >= 0 ? '+' : '';
  return `${sign}${num.toFixed(2)}%`;
};

/**
 * Returns the appropriate color class based on value sign
 * @param {number} value - The numeric value
 * @returns {string} Tailwind CSS class for color
 */
const getPnLColorClass = (value) => {
  const num = parseFloat(value) || 0;
  if (num > 0) return 'text-emerald-500';
  if (num < 0) return 'text-red-500';
  return 'text-slate-400 dark:text-slate-500';
};

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/**
 * SummaryCard - Displays a single metric with label and value
 * Supports dark mode and profit/loss styling
 */
const SummaryCard = ({ label, value, subValue, isPnL = false, icon }) => {
  // Determine value color based on whether it's P&L data
  const valueColorClass = isPnL ? getPnLColorClass(value) : 'text-slate-900 dark:text-slate-100';
  const formattedValue = typeof value === 'number' ? formatCurrency(value) : value;

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4 shadow-sm hover:shadow-md dark:shadow-slate-900/20 transition-all duration-200">
      {/* Card Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
          {label}
        </span>
        {icon && (
          <span className="text-slate-400 dark:text-slate-500">
            {icon}
          </span>
        )}
      </div>

      {/* Main Value */}
      <p className={`text-2xl font-bold ${valueColorClass} transition-colors duration-200`}>
        {formattedValue}
      </p>

      {/* Sub-value (optional - e.g., percentage change) */}
      {subValue !== undefined && (
        <p className={`text-sm mt-1 ${getPnLColorClass(subValue)} transition-colors duration-200`}>
          {formatPercentage(subValue)}
        </p>
      )}
    </div>
  );
};

/**
 * LoadingState - Skeleton loading component with dark mode support
 */
const LoadingState = () => (
  <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-6 transition-colors duration-200">
    <div className="max-w-7xl mx-auto">
      {/* Header Skeleton */}
      <div className="animate-pulse mb-6">
        <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-48 mb-2"></div>
        <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-32"></div>
      </div>

      {/* Summary Cards Skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4"
          >
            <div className="animate-pulse">
              <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-24 mb-3"></div>
              <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-32"></div>
            </div>
          </div>
        ))}
      </div>

      {/* Table Skeleton */}
      <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-40"></div>
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-slate-200 dark:bg-slate-700 rounded"></div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

/**
 * ErrorState - Error display component with dark mode support
 */
const ErrorState = ({ message }) => (
  <div className="min-h-screen bg-slate-50 dark:bg-slate-900 p-6 flex items-center justify-center transition-colors duration-200">
    <div className="bg-white dark:bg-slate-800 rounded-lg border border-red-200 dark:border-red-900 p-6 max-w-md w-full shadow-lg">
      <div className="flex items-center space-x-3 text-red-500">
        {/* Error Icon */}
        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <h3 className="text-lg font-semibold">Error Loading Portfolio</h3>
      </div>
      <p className="mt-3 text-slate-600 dark:text-slate-400 transition-colors duration-200">
        {message || 'An unexpected error occurred while loading portfolio data.'}
      </p>
      <button
        onClick={() => window.location.reload()}
        className="mt-4 w-full bg-red-500 hover:bg-red-600 text-white font-medium py-2 px-4 rounded-lg transition-colors duration-200"
      >
        Retry
      </button>
    </div>
  </div>
);

/**
 * AssetAllocationChart - Simple pie chart for asset distribution
 * Uses SVG for visual representation with dark mode colors
 */
const AssetAllocationChart = ({ positions, totalValue }) => {
  // Calculate allocation percentages
  const allocations = useMemo(() => {
    if (!positions || positions.length === 0 || !totalValue) {
      return [];
    }

    return positions.map((pos, index) => {
      const value = parseFloat(pos.current_value) ||
        (parseFloat(pos.entry_price) * parseFloat(pos.quantity)) || 0;
      const percentage = totalValue > 0 ? (value / totalValue) * 100 : 0;

      // Color palette for pie chart segments (visible in both modes)
      const colors = [
        '#3b82f6', // blue-500
        '#10b981', // emerald-500
        '#f59e0b', // amber-500
        '#ef4444', // red-500
        '#8b5cf6', // violet-500
        '#06b6d4', // cyan-500
        '#ec4899', // pink-500
        '#f97316', // orange-500
      ];

      return {
        symbol: pos.symbol,
        value,
        percentage,
        color: colors[index % colors.length],
      };
    }).sort((a, b) => b.value - a.value);
  }, [positions, totalValue]);

  // If no allocations, show empty state
  if (allocations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-400 dark:text-slate-500">
        <svg className="w-16 h-16 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z"
          />
        </svg>
        <p className="text-sm">No asset allocation data</p>
      </div>
    );
  }

  // Calculate pie chart segments
  let cumulativePercentage = 0;
  const segments = allocations.map((allocation) => {
    const startAngle = cumulativePercentage * 3.6; // Convert percentage to degrees
    cumulativePercentage += allocation.percentage;
    const endAngle = cumulativePercentage * 3.6;

    return {
      ...allocation,
      startAngle,
      endAngle,
    };
  });

  return (
    <div className="flex flex-col lg:flex-row items-center gap-6">
      {/* Pie Chart SVG */}
      <div className="relative w-48 h-48 flex-shrink-0">
        <svg viewBox="0 0 100 100" className="transform -rotate-90">
          {segments.map((segment, index) => {
            const startAngle = (segment.startAngle * Math.PI) / 180;
            const endAngle = (segment.endAngle * Math.PI) / 180;

            const x1 = 50 + 40 * Math.cos(startAngle);
            const y1 = 50 + 40 * Math.sin(startAngle);
            const x2 = 50 + 40 * Math.cos(endAngle);
            const y2 = 50 + 40 * Math.sin(endAngle);

            const largeArcFlag = segment.percentage > 50 ? 1 : 0;

            const pathData =
              segment.percentage === 100
                ? `M 50 10 A 40 40 0 1 1 49.99 10` // Full circle
                : `M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArcFlag} 1 ${x2} ${y2} Z`;

            return (
              <path
                key={index}
                d={pathData}
                fill={segment.color}
                className="hover:opacity-80 transition-opacity duration-200"
              />
            );
          })}
          {/* Center hole for donut effect */}
          <circle cx="50" cy="50" r="25" className="fill-white dark:fill-slate-800 transition-colors duration-200" />
        </svg>
      </div>

      {/* Legend */}
      <div className="flex-1 space-y-2">
        {allocations.slice(0, 6).map((allocation, index) => (
          <div
            key={index}
            className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 transition-colors duration-200"
          >
            <div className="flex items-center space-x-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: allocation.color }}
              />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300 transition-colors duration-200">
                {allocation.symbol}
              </span>
            </div>
            <div className="text-right">
              <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 transition-colors duration-200">
                {allocation.percentage.toFixed(1)}%
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400 ml-2 transition-colors duration-200">
                {formatCurrency(allocation.value)}
              </span>
            </div>
          </div>
        ))}
        {allocations.length > 6 && (
          <p className="text-xs text-slate-500 dark:text-slate-400 text-center pt-2 transition-colors duration-200">
            +{allocations.length - 6} more assets
          </p>
        )}
      </div>
    </div>
  );
};

/**
 * HoldingsTable - Displays portfolio holdings in a table format
 * Full dark mode support with alternating row colors
 */
const HoldingsTable = ({ positions }) => {
  if (!positions || positions.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500 dark:text-slate-400 transition-colors duration-200">
        <svg className="w-12 h-12 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
          />
        </svg>
        <p className="font-medium">No Holdings</p>
        <p className="text-sm mt-1">Your portfolio is currently empty</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        {/* Table Header */}
        <thead className="bg-slate-100 dark:bg-slate-700 transition-colors duration-200">
          <tr>
            <th className="px-4 py-3 text-left font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Asset
            </th>
            <th className="px-4 py-3 text-left font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Side
            </th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Quantity
            </th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Entry Price
            </th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Current Price
            </th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Value
            </th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300 transition-colors duration-200">
              Unrealized P&L
            </th>
          </tr>
        </thead>

        {/* Table Body */}
        <tbody>
          {positions.map((position, index) => {
            // Extract position data (handle different API formats)
            const symbol = position.symbol || 'Unknown';
            const side = position.side || 'LONG';
            const quantity = parseFloat(position.quantity) || 0;
            const entryPrice = parseFloat(position.entry_price) || parseFloat(position.avg_entry_price) || 0;
            const currentPrice = parseFloat(position.current_price) || entryPrice;
            const positionValue = currentPrice * quantity;
            const unrealizedPnl = parseFloat(position.unrealized_pnl) || 0;
            const pnlPercentage = entryPrice > 0
              ? ((currentPrice - entryPrice) / entryPrice * 100) * (side === 'SHORT' ? -1 : 1)
              : 0;

            return (
              <tr
                key={position.id || index}
                className="bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 even:bg-slate-50 dark:even:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700 transition-colors duration-200"
              >
                {/* Asset Symbol */}
                <td className="px-4 py-3">
                  <span className="font-semibold text-slate-900 dark:text-slate-100 transition-colors duration-200">
                    {symbol}
                  </span>
                </td>

                {/* Side */}
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-1 rounded text-xs font-bold ${
                      side === 'LONG'
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-400'
                        : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-400'
                    } transition-colors duration-200`}
                  >
                    {side}
                  </span>
                </td>

                {/* Quantity */}
                <td className="px-4 py-3 text-right text-slate-700 dark:text-slate-300 transition-colors duration-200">
                  {quantity.toFixed(8)}
                </td>

                {/* Entry Price */}
                <td className="px-4 py-3 text-right text-slate-700 dark:text-slate-300 transition-colors duration-200">
                  {formatCurrency(entryPrice)}
                </td>

                {/* Current Price */}
                <td className="px-4 py-3 text-right text-slate-700 dark:text-slate-300 transition-colors duration-200">
                  {formatCurrency(currentPrice)}
                </td>

                {/* Value */}
                <td className="px-4 py-3 text-right font-medium text-slate-900 dark:text-slate-100 transition-colors duration-200">
                  {formatCurrency(positionValue)}
                </td>

                {/* Unrealized P&L */}
                <td className="px-4 py-3 text-right">
                  <div className={`font-semibold ${getPnLColorClass(unrealizedPnl)}`}>
                    {formatCurrency(unrealizedPnl)}
                  </div>
                  <div className={`text-xs ${getPnLColorClass(pnlPercentage)}`}>
                    {formatPercentage(pnlPercentage)}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

/**
 * TradeHistoryTable - Displays recent trade history
 */
const TradeHistoryTable = ({ trades }) => {
  if (!trades || trades.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 dark:text-slate-400 transition-colors duration-200">
        <p className="font-medium">No Recent Trades</p>
        <p className="text-sm mt-1">Trade history will appear here</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-100 dark:bg-slate-700 transition-colors duration-200">
          <tr>
            <th className="px-4 py-3 text-left font-semibold text-slate-700 dark:text-slate-300">Date</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-700 dark:text-slate-300">Asset</th>
            <th className="px-4 py-3 text-left font-semibold text-slate-700 dark:text-slate-300">Type</th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300">Quantity</th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300">Price</th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300">Total</th>
            <th className="px-4 py-3 text-right font-semibold text-slate-700 dark:text-slate-300">P&L</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, 10).map((trade, index) => {
            const pnl = parseFloat(trade.pnl) || parseFloat(trade.realized_pnl) || 0;
            const tradeType = trade.side || trade.type || 'BUY';
            const isBuy = tradeType.toUpperCase() === 'BUY' || tradeType.toUpperCase() === 'LONG';

            return (
              <tr
                key={trade.id || index}
                className="bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 even:bg-slate-50 dark:even:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700 transition-colors duration-200"
              >
                <td className="px-4 py-3 text-slate-600 dark:text-slate-400">
                  {trade.executed_at || trade.timestamp
                    ? new Date(trade.executed_at || trade.timestamp).toLocaleDateString()
                    : 'N/A'}
                </td>
                <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                  {trade.symbol || 'Unknown'}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-1 rounded text-xs font-bold ${
                      isBuy
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-400'
                        : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-400'
                    }`}
                  >
                    {tradeType}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-slate-700 dark:text-slate-300">
                  {parseFloat(trade.quantity || 0).toFixed(8)}
                </td>
                <td className="px-4 py-3 text-right text-slate-700 dark:text-slate-300">
                  {formatCurrency(trade.price || trade.executed_price)}
                </td>
                <td className="px-4 py-3 text-right font-medium text-slate-900 dark:text-slate-100">
                  {formatCurrency((parseFloat(trade.quantity) || 0) * (parseFloat(trade.price || trade.executed_price) || 0))}
                </td>
                <td className={`px-4 py-3 text-right font-semibold ${getPnLColorClass(pnl)}`}>
                  {pnl !== 0 ? formatCurrency(pnl) : '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * Portfolio - Main portfolio page component
 *
 * Displays comprehensive portfolio information with full dark mode support.
 * Fetches data from multiple API endpoints and combines them into a cohesive view.
 */
const Portfolio = () => {
  // Access theme context for conditional styling
  const { theme, isDarkMode } = useTheme();

  // Fetch portfolio data from various hooks.
  // Plan 06-05 DASH-05: portfolioQuery is the load-bearing query for the
  // page-level <TileState forceStale/> wrapper (LABELED_STALE verdict).
  const portfolioQuery = usePortfolio();
  const { data: portfolioData } = portfolioQuery;
  const { data: performanceData, isLoading: performanceLoading } = usePortfolioPerformance();
  const { data: positionsData, isLoading: positionsLoading, error: positionsError } = usePositions();
  const { data: statusData } = useTradingStatus();
  const { data: tradesData, isLoading: tradesLoading } = useTradeHistory({ limit: 10 });

  // Loading and combined-error states are now surfaced by the page-level
  // <TileState forceStale/> wrapper below; inline LoadingState/ErrorState
  // early-returns removed.

  // Extract and process data
  const portfolio = portfolioData?.portfolio || {};
  const tradingPositions = positionsData?.positions || [];
  const portfolioHoldings = portfolio.holdings || [];
  const positions = tradingPositions.length > 0 ? tradingPositions : portfolioHoldings;
  const tradingStatus = statusData?.status || {};
  const trades = tradesData?.trades || [];

  // Calculate summary values
  const cashBalance = parseFloat(portfolio.cash_balance) || 0;
  const totalValue = parseFloat(portfolio.total_value) || 0;
  const totalPnl = parseFloat(portfolio.total_pnl) || 0;
  const totalPnlPct = parseFloat(portfolio.total_pnl_percentage) || parseFloat(portfolio.total_return_pct) || 0;

  // Calculate unrealized P&L from positions
  const unrealizedPnl = positions.reduce((sum, pos) => {
    return sum + (parseFloat(pos.unrealized_pnl) || 0);
  }, 0);

  // Calculate realized P&L (from performance data or trades)
  const realizedPnl = parseFloat(performanceData?.realized_pnl) ||
    trades.reduce((sum, t) => sum + (parseFloat(t.pnl || t.realized_pnl) || 0), 0);

  // Calculate available margin (cash balance - positions value if needed)
  const totalExposure = positions.reduce((sum, pos) => {
    const posValue = parseFloat(pos.current_value) ||
      (parseFloat(pos.entry_price) * parseFloat(pos.quantity)) || 0;
    return sum + posValue;
  }, 0);
  const availableMargin = cashBalance;

  return (
    <div data-testid="portfolio-page" style={{ display: 'contents' }}>
    <TileState
      query={portfolioQuery}
      title="Portfolio"
      thresholdKey="portfolio"
      lastUpdatedAt={undefined}
      forceStale
      isEmpty={(d) => !d || !d.portfolio}
    >
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      <div className="max-w-7xl mx-auto p-6">
        {/* Page Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100 transition-colors duration-200">
                Portfolio
              </h1>
              <p className="text-slate-600 dark:text-slate-400 mt-1 transition-colors duration-200">
                Track your assets and performance
              </p>
            </div>

            {/* Trading Status Indicator */}
            {tradingStatus.is_running !== undefined && (
              <div
                className={`flex items-center space-x-2 px-3 py-2 rounded-lg ${
                  tradingStatus.is_running
                    ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-400'
                    : 'bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-400'
                } transition-colors duration-200`}
              >
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    tradingStatus.is_running
                      ? 'bg-emerald-500 animate-pulse'
                      : 'bg-red-500'
                  }`}
                />
                <span className="text-sm font-medium">
                  {tradingStatus.is_running ? 'Bot Active' : 'Bot Stopped'}
                </span>
              </div>
            )}
          </div>

          {/* Last Updated */}
          <p className="text-sm text-slate-500 dark:text-slate-500 mt-2 transition-colors duration-200">
            Last updated: {new Date().toLocaleString()}
          </p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <SummaryCard
            label="Total Balance"
            value={totalValue}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
          />

          <SummaryCard
            label="Unrealized P&L"
            value={unrealizedPnl}
            isPnL={true}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            }
          />

          <SummaryCard
            label="Realized P&L"
            value={realizedPnl}
            isPnL={true}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
          />

          <SummaryCard
            label="Available Margin"
            value={availableMargin}
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            }
          />
        </div>

        {/* Asset Allocation Section */}
        <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-6 mb-6 shadow-sm transition-all duration-200">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 mb-6 transition-colors duration-200">
            Asset Allocation
          </h2>
          <AssetAllocationChart positions={positions} totalValue={totalValue} />
        </div>

        {/* Holdings Table */}
        <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 shadow-sm mb-6 transition-all duration-200">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 transition-colors duration-200">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 transition-colors duration-200">
              Holdings ({positions.length})
            </h2>
          </div>
          <HoldingsTable positions={positions} />
        </div>

        {/* Recent Trades */}
        <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 shadow-sm transition-all duration-200">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 transition-colors duration-200">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 transition-colors duration-200">
              Recent Trades
            </h2>
          </div>
          {tradesLoading ? (
            <div className="p-6">
              <div className="animate-pulse space-y-3">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-10 bg-slate-200 dark:bg-slate-700 rounded"></div>
                ))}
              </div>
            </div>
          ) : (
            <TradeHistoryTable trades={trades} />
          )}
        </div>

        {/* Trading Activity Stats (if available) */}
        {tradingStatus.total_trades_executed !== undefined && (
          <div className="mt-6 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800 p-6 transition-all duration-200">
            <h3 className="text-lg font-semibold text-blue-800 dark:text-blue-300 mb-4 transition-colors duration-200">
              Trading Activity Summary
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white dark:bg-slate-800 rounded-lg p-3 transition-colors duration-200">
                <p className="text-sm text-slate-600 dark:text-slate-400">Signals Checked</p>
                <p className="text-xl font-bold text-slate-900 dark:text-slate-100">
                  {tradingStatus.total_signals_checked || 0}
                </p>
              </div>
              <div className="bg-white dark:bg-slate-800 rounded-lg p-3 transition-colors duration-200">
                <p className="text-sm text-slate-600 dark:text-slate-400">Trades Executed</p>
                <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
                  {tradingStatus.total_trades_executed || 0}
                </p>
              </div>
              <div className="bg-white dark:bg-slate-800 rounded-lg p-3 transition-colors duration-200">
                <p className="text-sm text-slate-600 dark:text-slate-400">Trades Rejected</p>
                <p className="text-xl font-bold text-red-600 dark:text-red-400">
                  {tradingStatus.total_trades_rejected || 0}
                </p>
              </div>
              <div className="bg-white dark:bg-slate-800 rounded-lg p-3 transition-colors duration-200">
                <p className="text-sm text-slate-600 dark:text-slate-400">Last Check</p>
                <p className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  {tradingStatus.last_check_time
                    ? new Date(tradingStatus.last_check_time).toLocaleTimeString()
                    : 'N/A'}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
    </TileState>
    </div>
  );
};

// ============================================================================
// EXPORTS
// ============================================================================

export default Portfolio;
