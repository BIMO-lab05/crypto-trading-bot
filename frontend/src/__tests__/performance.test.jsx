/**
 * Performance Dashboard Component Tests
 *
 * Purpose: Basic tests for performance dashboard components.
 * Tests rendering, data display, and user interactions.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Import components to test
import MetricsCard, {
  SharpeRatioCard,
  SortinoRatioCard,
  MaxDrawdownCard,
  WinRateCard,
} from '../components/performance/MetricsCard'
import EquityCurveChart from '../components/performance/EquityCurveChart'
import DrawdownChart from '../components/performance/DrawdownChart'
import ReturnsDistribution from '../components/performance/ReturnsDistribution'
import CorrelationHeatmap from '../components/performance/CorrelationHeatmap'

// Import utilities for testing
import {
  calculateEquityCurve,
  calculateDrawdownSeries,
  calculateReturnsDistribution,
  calculatePerformanceMetrics,
} from '../services/analyticsApi'
import { PAPER_DEFAULT_BALANCE } from '../utils/balance'

// ============================================================================
// TEST UTILITIES
// ============================================================================

/**
 * Create a QueryClient for testing
 */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })
}

/**
 * Wrapper component for tests requiring providers
 */
function TestWrapper({ children }) {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  )
}

/**
 * Generate mock trade data for testing.
 * Parameterized on PAPER_DEFAULT_BALANCE (the declared paper account —
 * $10,000 per ADR-029) so the fixtures track the real account size instead
 * of hardcoding one that can go stale.
 */
function generateMockTrades(count = 20) {
  const trades = []
  let balance = PAPER_DEFAULT_BALANCE

  for (let i = 0; i < count; i++) {
    // Random per-trade P&L between −5% and +8% of the account
    // (slightly positive bias)
    const pnl = (Math.random() * 0.13 - 0.05) * PAPER_DEFAULT_BALANCE
    balance += pnl

    trades.push({
      id: `trade-${i}`,
      symbol: ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'][i % 3],
      side: pnl > 0 ? 'BUY' : 'SELL',
      quantity: 0.1,
      entry_price: 50000 + Math.random() * 1000,
      exit_price: 50000 + Math.random() * 1000 + pnl,
      realized_pnl: pnl,
      status: 'CLOSED',
      opened_at: new Date(Date.now() - (count - i) * 86400000).toISOString(),
      closed_at: new Date(Date.now() - (count - i) * 86400000 + 3600000).toISOString(),
    })
  }

  return trades
}

/**
 * Mock equity curve data, parameterized on PAPER_DEFAULT_BALANCE.
 * Cumulative P&L moves are fractions of the account (0–6.5%) so the fixture
 * stays realistic at any declared account size.
 */
const BASE = PAPER_DEFAULT_BALANCE
const pct = (fraction) => BASE * fraction

const mockEquityCurve = [
  { timestamp: Date.now() - 6 * 86400000, equity: BASE, pnl: 0, cumulativePnl: 0 },
  { timestamp: Date.now() - 5 * 86400000, equity: BASE + pct(0.02), pnl: pct(0.02), cumulativePnl: pct(0.02) },
  { timestamp: Date.now() - 4 * 86400000, equity: BASE + pct(0.015), pnl: -pct(0.005), cumulativePnl: pct(0.015) },
  { timestamp: Date.now() - 3 * 86400000, equity: BASE + pct(0.04), pnl: pct(0.025), cumulativePnl: pct(0.04) },
  { timestamp: Date.now() - 2 * 86400000, equity: BASE + pct(0.035), pnl: -pct(0.005), cumulativePnl: pct(0.035) },
  { timestamp: Date.now() - 1 * 86400000, equity: BASE + pct(0.05), pnl: pct(0.015), cumulativePnl: pct(0.05) },
  { timestamp: Date.now(), equity: BASE + pct(0.065), pnl: pct(0.015), cumulativePnl: pct(0.065) },
]

/**
 * Mock drawdown data (equity scaled to PAPER_DEFAULT_BALANCE; drawdown
 * percentages are scale-invariant, so they match the equity ratios above).
 */
const mockDrawdownData = [
  { timestamp: Date.now() - 6 * 86400000, drawdownPercent: 0, equity: BASE, peak: BASE },
  { timestamp: Date.now() - 5 * 86400000, drawdownPercent: 0, equity: pct(1.02), peak: pct(1.02) },
  { timestamp: Date.now() - 4 * 86400000, drawdownPercent: 0.49, equity: pct(1.015), peak: pct(1.02) },
  { timestamp: Date.now() - 3 * 86400000, drawdownPercent: 0, equity: pct(1.04), peak: pct(1.04) },
  { timestamp: Date.now() - 2 * 86400000, drawdownPercent: 0.48, equity: pct(1.035), peak: pct(1.04) },
  { timestamp: Date.now() - 1 * 86400000, drawdownPercent: 0, equity: pct(1.05), peak: pct(1.05) },
  { timestamp: Date.now(), drawdownPercent: 0, equity: pct(1.065), peak: pct(1.065) },
]

/**
 * Mock returns distribution
 */
const mockReturnsDistribution = {
  bins: [
    { binStart: -5, binEnd: -3, binMid: -4, count: 2, frequency: 0.1 },
    { binStart: -3, binEnd: -1, binMid: -2, count: 3, frequency: 0.15 },
    { binStart: -1, binEnd: 1, binMid: 0, count: 5, frequency: 0.25 },
    { binStart: 1, binEnd: 3, binMid: 2, count: 6, frequency: 0.3 },
    { binStart: 3, binEnd: 5, binMid: 4, count: 4, frequency: 0.2 },
  ],
  stats: {
    count: 20,
    mean: 0.5,
    median: 0.75,
    stdDev: 2.5,
    variance: 6.25,
    min: -4.5,
    max: 4.8,
    skewness: -0.15,
    kurtosis: -0.5,
    range: 9.3,
  },
}

// ============================================================================
// METRICS CARD TESTS
// ============================================================================

describe('MetricsCard Component', () => {
  it('renders with title and value', () => {
    render(<MetricsCard title="Test Metric" value={1.5} format="ratio" />)

    expect(screen.getByText('Test Metric')).toBeInTheDocument()
    expect(screen.getByText('1.50')).toBeInTheDocument()
  })

  it('displays N/A when value is null', () => {
    render(<MetricsCard title="Test Metric" value={null} format="ratio" />)

    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('formats currency values correctly', () => {
    render(<MetricsCard title="P&L" value={1234.56} format="currency" />)

    expect(screen.getByText('$1,234.56')).toBeInTheDocument()
  })

  it('formats percentage values correctly', () => {
    render(<MetricsCard title="Win Rate" value={0.65} format="percent" />)

    expect(screen.getByText('65.00%')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<MetricsCard title="Test Metric" value={1.5} loading={true} />)

    // Should show skeleton (animated elements)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('applies correct color based on thresholds', () => {
    const { container } = render(
      <MetricsCard
        title="Sharpe"
        value={2.5}
        format="ratio"
        thresholds={{ good: 2, warning: 1, bad: 0 }}
      />
    )

    // Good value should have emerald/green color
    const valueElement = container.querySelector('.text-emerald-500, .text-emerald-400')
    expect(valueElement).toBeTruthy()
  })
})

describe('Pre-configured Metric Cards', () => {
  it('SharpeRatioCard renders correctly', () => {
    render(<SharpeRatioCard value={1.8} />)

    expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument()
    expect(screen.getByText('1.80')).toBeInTheDocument()
  })

  it('SortinoRatioCard renders correctly', () => {
    render(<SortinoRatioCard value={2.1} />)

    expect(screen.getByText('Sortino Ratio')).toBeInTheDocument()
    expect(screen.getByText('2.10')).toBeInTheDocument()
  })

  it('MaxDrawdownCard renders correctly', () => {
    render(<MaxDrawdownCard value={8.5} />)

    expect(screen.getByText('Max Drawdown')).toBeInTheDocument()
    expect(screen.getByText('8.50%')).toBeInTheDocument()
  })

  it('WinRateCard renders correctly', () => {
    render(<WinRateCard value={58.5} />)

    expect(screen.getByText('Win Rate')).toBeInTheDocument()
    expect(screen.getByText('58.50%')).toBeInTheDocument()
  })
})

// ============================================================================
// EQUITY CURVE CHART TESTS
// ============================================================================

describe('EquityCurveChart Component', () => {
  it('renders with data', () => {
    render(<EquityCurveChart data={mockEquityCurve} loading={false} />)

    expect(screen.getByText('Equity Curve')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<EquityCurveChart data={[]} loading={true} />)

    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('shows no data message when empty', () => {
    render(<EquityCurveChart data={[]} loading={false} />)

    expect(screen.getByText('No equity data available')).toBeInTheDocument()
  })

  it('displays current equity value', () => {
    render(<EquityCurveChart data={mockEquityCurve} loading={false} />)

    // Should show the last equity value formatted as currency. The figure
    // legitimately repeats (header, footer High, accessible data table), so
    // assert presence rather than uniqueness. Computed from the fixture so
    // the assertion tracks PAPER_DEFAULT_BALANCE.
    const finalEquity = mockEquityCurve[mockEquityCurve.length - 1].equity
    const expected = `$${finalEquity.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
    expect(screen.getAllByText(expected).length).toBeGreaterThan(0)
  })

  it('renders period selector buttons', () => {
    const onPeriodChange = vi.fn()
    render(
      <EquityCurveChart
        data={mockEquityCurve}
        loading={false}
        period="30d"
        onPeriodChange={onPeriodChange}
      />
    )

    expect(screen.getByText('1D')).toBeInTheDocument()
    expect(screen.getByText('7D')).toBeInTheDocument()
    expect(screen.getByText('30D')).toBeInTheDocument()
    expect(screen.getByText('90D')).toBeInTheDocument()
    expect(screen.getByText('All')).toBeInTheDocument()
  })

  it('calls onPeriodChange when period button clicked', () => {
    const onPeriodChange = vi.fn()
    render(
      <EquityCurveChart
        data={mockEquityCurve}
        loading={false}
        period="30d"
        onPeriodChange={onPeriodChange}
      />
    )

    fireEvent.click(screen.getByText('7D'))
    expect(onPeriodChange).toHaveBeenCalledWith('7d')
  })
})

// ============================================================================
// DRAWDOWN CHART TESTS
// ============================================================================

describe('DrawdownChart Component', () => {
  it('renders with data', () => {
    render(<DrawdownChart data={mockDrawdownData} loading={false} />)

    expect(screen.getByText('Drawdown Analysis')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<DrawdownChart data={[]} loading={true} />)

    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('shows no data message when empty', () => {
    render(<DrawdownChart data={[]} loading={false} />)

    expect(screen.getByText('No drawdown data available')).toBeInTheDocument()
  })

  it('displays current drawdown', () => {
    render(<DrawdownChart data={mockDrawdownData} loading={false} />)

    // Current drawdown should be displayed
    expect(screen.getByText('Current')).toBeInTheDocument()
  })

  it('displays risk level indicator', () => {
    render(<DrawdownChart data={mockDrawdownData} loading={false} />)

    expect(screen.getByText('Risk Level:')).toBeInTheDocument()
  })
})

// ============================================================================
// RETURNS DISTRIBUTION TESTS
// ============================================================================

describe('ReturnsDistribution Component', () => {
  it('renders with data', () => {
    render(
      <ReturnsDistribution
        bins={mockReturnsDistribution.bins}
        stats={mockReturnsDistribution.stats}
        loading={false}
      />
    )

    expect(screen.getByText('Returns Distribution')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<ReturnsDistribution bins={[]} stats={null} loading={true} />)

    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('shows no data message when empty', () => {
    render(<ReturnsDistribution bins={[]} stats={null} loading={false} />)

    expect(screen.getByText('No returns data available')).toBeInTheDocument()
  })

  it('displays statistical summary', () => {
    render(
      <ReturnsDistribution
        bins={mockReturnsDistribution.bins}
        stats={mockReturnsDistribution.stats}
        loading={false}
      />
    )

    expect(screen.getByText('Statistical Summary')).toBeInTheDocument()
    expect(screen.getByText('Mean')).toBeInTheDocument()
    expect(screen.getByText('Median')).toBeInTheDocument()
    expect(screen.getByText('Std Dev')).toBeInTheDocument()
    expect(screen.getByText('Skewness')).toBeInTheDocument()
  })
})

// ============================================================================
// CORRELATION HEATMAP TESTS
// ============================================================================

describe('CorrelationHeatmap Component', () => {
  it('renders with mock data', () => {
    render(<CorrelationHeatmap loading={false} useMockData={true} />)

    expect(screen.getByText('Asset Correlation Matrix')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<CorrelationHeatmap loading={true} />)

    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('displays correlation values in cells', () => {
    render(<CorrelationHeatmap loading={false} useMockData={true} />)

    // Self-correlation should be 1.00
    expect(screen.getAllByText('1.00').length).toBeGreaterThan(0)
  })

  it('displays average correlation', () => {
    render(<CorrelationHeatmap loading={false} useMockData={true} />)

    expect(screen.getByText('Avg Correlation')).toBeInTheDocument()
  })

  it('shows detail panel on cell click', () => {
    render(<CorrelationHeatmap loading={false} useMockData={true} />)

    // Initially shows instruction to click
    expect(screen.getByText('Click a cell to view correlation details')).toBeInTheDocument()
  })
})

// ============================================================================
// UTILITY FUNCTION TESTS
// ============================================================================

describe('Analytics Utility Functions', () => {
  describe('calculateEquityCurve', () => {
    it('calculates equity curve from trades', () => {
      const trades = generateMockTrades(5)
      const curve = calculateEquityCurve(trades, PAPER_DEFAULT_BALANCE)

      expect(curve.length).toBeGreaterThan(0)
      expect(curve[0].equity).toBe(PAPER_DEFAULT_BALANCE)
    })

    it('handles empty trades array', () => {
      const curve = calculateEquityCurve([], PAPER_DEFAULT_BALANCE)

      expect(curve.length).toBe(1)
      expect(curve[0].equity).toBe(PAPER_DEFAULT_BALANCE)
    })
  })

  describe('calculateDrawdownSeries', () => {
    it('calculates drawdown from equity curve', () => {
      const equityCurve = [
        { timestamp: Date.now(), equity: 100 },
        { timestamp: Date.now(), equity: 102 },
        { timestamp: Date.now(), equity: 100 }, // 1.96% drawdown from peak
      ]

      const drawdown = calculateDrawdownSeries(equityCurve)

      expect(drawdown.length).toBe(3)
      expect(drawdown[0].drawdownPercent).toBe(0)
      // drawdownPercent is in percent units (0–100), per analyticsApi.js
      // ("drawdown * 100"): (102 - 100) / 102 * 100 = 1.9608.
      // The old expectation (0.0196) was in fraction units and never matched.
      expect(drawdown[2].drawdownPercent).toBeCloseTo(1.9608, 2)
    })

    it('handles empty equity curve', () => {
      const drawdown = calculateDrawdownSeries([])
      expect(drawdown.length).toBe(0)
    })
  })

  describe('calculateReturnsDistribution', () => {
    it('calculates distribution from trades', () => {
      const trades = generateMockTrades(20)
      const distribution = calculateReturnsDistribution(trades, 5)

      expect(distribution.bins.length).toBe(5)
      expect(distribution.stats).toBeTruthy()
      expect(distribution.stats.count).toBe(20)
    })

    it('handles empty trades array', () => {
      const distribution = calculateReturnsDistribution([], 5)

      expect(distribution.bins.length).toBe(0)
      expect(distribution.stats).toBeNull()
    })
  })

  describe('calculatePerformanceMetrics', () => {
    it('calculates metrics from trades', () => {
      const trades = generateMockTrades(20)
      const metrics = calculatePerformanceMetrics(trades)

      expect(metrics).toBeTruthy()
      expect(metrics.totalTrades).toBe(20)
      expect(metrics.winRate).toBeGreaterThanOrEqual(0)
      expect(metrics.winRate).toBeLessThanOrEqual(100)
      expect(typeof metrics.sharpeRatio).toBe('number')
      expect(typeof metrics.sortinoRatio).toBe('number')
      expect(typeof metrics.maxDrawdown).toBe('number')
    })

    it('returns null for empty trades', () => {
      const metrics = calculatePerformanceMetrics([])
      expect(metrics).toBeNull()
    })

    it('keeps maxDrawdownPercent bounded to 0–100 even when losses exceed peak gains', () => {
      // Win-then-cascading-losses sequence used to overflow the old formula
      // (cumulativePnL / peak_at_end) and produce >100% drawdown.
      const trades = [
        { realized_pnl: 0.1, closed_at: '2026-05-01T00:00:00Z' },
        { realized_pnl: -0.05, closed_at: '2026-05-01T01:00:00Z' },
        { realized_pnl: -0.2, closed_at: '2026-05-01T02:00:00Z' },
        { realized_pnl: -0.2, closed_at: '2026-05-01T03:00:00Z' },
        { realized_pnl: -0.05, closed_at: '2026-05-01T04:00:00Z' },
      ]
      const metrics = calculatePerformanceMetrics(trades, PAPER_DEFAULT_BALANCE)

      expect(metrics.maxDrawdownPercent).toBeGreaterThanOrEqual(0)
      expect(metrics.maxDrawdownPercent).toBeLessThanOrEqual(100)
      expect(metrics.maxDrawdown).toBeGreaterThan(0)
    })

    it('matches calculateDrawdownSeries when using the same initialBalance', () => {
      const trades = generateMockTrades(30)
      const initialBalance = PAPER_DEFAULT_BALANCE
      const metrics = calculatePerformanceMetrics(trades, initialBalance)
      const equity = calculateEquityCurve(trades, initialBalance)
      const ddSeries = calculateDrawdownSeries(equity)
      const expectedMaxPct = Math.max(...ddSeries.map((d) => d.drawdownPercent), 0)

      expect(metrics.maxDrawdownPercent).toBeCloseTo(expectedMaxPct, 6)
    })
  })
})
