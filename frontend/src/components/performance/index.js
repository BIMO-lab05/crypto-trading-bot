/**
 * Performance Components Index
 *
 * Purpose: Barrel export file for all performance dashboard components.
 * Provides clean imports for consuming components.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

// Core metric display components
export { default as MetricsCard } from './MetricsCard'
export {
  SharpeRatioCard,
  SortinoRatioCard,
  MaxDrawdownCard,
  WinRateCard,
  ProfitFactorCard,
  TotalPnLCard,
  VaRCard,
  CVaRCard,
} from './MetricsCard'

// Chart components
export { default as EquityCurveChart } from './EquityCurveChart'
export { default as DrawdownChart } from './DrawdownChart'
export { default as ReturnsDistribution } from './ReturnsDistribution'
export { default as CorrelationHeatmap } from './CorrelationHeatmap'
export { default as DailyPnLChart } from './DailyPnLChart'

// Overview and grid components
export { default as OverviewCards } from './OverviewCards'
export { default as MetricsGrid } from './MetricsGrid'

// Trade components
export { default as RecentTrades } from './RecentTrades'

// Export components
export { default as ExportButton } from './ExportButton'

// Re-export PerformanceDashboard components from dedicated directory
export {
  PerformanceDashboard,
  StrategyAttribution,
  RiskMetrics,
  ExportPanel,
} from '../PerformanceDashboard'
