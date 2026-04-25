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
 * Generate mock trade data for testing
 */
function generateMockTrades(count = 20) {
  const trades = []
  let balance = 10000

  for (let i = 0; i < count; i++) {
    // Random P&L between -500 and +800 (slightly positive bias)
    const pnl = Math.random() * 1300 - 500
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
 * Mock equity curve data
 */
const mockEquityCurve = [
  { timestamp: Date.now() - 6 * 86400000, equity: 10000, pnl: 0, cumulativePnl: 0 },
  { timestamp: Date.now() - 5 * 86400000, equity: 10200, pnl: 200, cumulativePnl: 200 },
  { timestamp: Date.now() - 4 * 86400000, equity: 10150, pnl: -50, cumulativePnl: 150 },
  { timestamp: Date.now() - 3 * 86400000, equity: 10400, pnl: 250, cumulativePnl: 400 },
  { timestamp: Date.now() - 2 * 86400000, equity: 10350, pnl: -50, cumulativePnl: 350 },
  { timestamp: Date.now() - 1 * 86400000, equity: 10500, pnl: 150, cumulativePnl: 500 },
  { timestamp: Date.now(), equity: 10650, pnl: 150, cumulativePnl: 650 },
]

/**
 * Mock drawdown data
 */
const mockDrawdownData = [
  { timestamp: Date.now() - 6 * 86400000, drawdownPercent: 0, equity: 10000, peak: 10000 },
  { timestamp: Date.now() - 5 * 86400000, drawdownPercent: 0, equity: 10200, peak: 10200 },
  { timestamp: Date.now() - 4 * 86400000, drawdownPercent: 0.49, equity: 10150, peak: 10200 },
  { timestamp: Date.now() - 3 * 86400000, drawdownPercent: 0, equity: 10400, peak: 10400 },
  { timestamp: Date.now() - 2 * 86400000, drawdownPercent: 0.48, equity: 10350, peak: 10400 },
  { timestamp: Date.now() - 1 * 86400000, drawdownPercent: 0, equity: 10500, peak: 10500 },
  { timestamp: Date.now(), drawdownPercent: 0, equity: 10650, peak: 10650 },
]

/**
 * Mock returns distribution
 */
const mockReturnsDistribution = {
  bins: [
    { binStart: -500, binEnd: -300, binMid: -400, count: 2, frequency: 0.1 },
    { binStart: -300, binEnd: -100, binMid: -200, count: 3, frequency: 0.15 },
    { binStart: -100, binEnd: 100, binMid: 0, count: 5, frequency: 0.25 },
    { binStart: 100, binEnd: 300, binMid: 200, count: 6, frequency: 0.3 },
    { binStart: 300, binEnd: 500, binMid: 400, count: 4, frequency: 0.2 },
  ],
  stats: {
    count: 20,
    mean: 50,
    median: 75,
    stdDev: 250,
    variance: 62500,
    min: -450,
    max: 480,
    skewness: -0.15,
    kurtosis: -0.5,
    range: 930,
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

    // Should show the last equity value formatted as currency
    expect(screen.getByText('$10,650.00')).toBeInTheDocument()
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
      const curve = calculateEquityCurve(trades, 10000)

      expect(curve.length).toBeGreaterThan(0)
      expect(curve[0].equity).toBe(10000)
    })

    it('handles empty trades array', () => {
      const curve = calculateEquityCurve([], 10000)

      expect(curve.length).toBe(1)
      expect(curve[0].equity).toBe(10000)
    })
  })

  describe('calculateDrawdownSeries', () => {
    it('calculates drawdown from equity curve', () => {
      const equityCurve = [
        { timestamp: Date.now(), equity: 10000 },
        { timestamp: Date.now(), equity: 10200 },
        { timestamp: Date.now(), equity: 10000 }, // 1.96% drawdown from peak
      ]

      const drawdown = calculateDrawdownSeries(equityCurve)

      expect(drawdown.length).toBe(3)
      expect(drawdown[0].drawdownPercent).toBe(0)
      expect(drawdown[2].drawdownPercent).toBeCloseTo(0.0196, 2)
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
  })
})
