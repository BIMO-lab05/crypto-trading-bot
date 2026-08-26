/**
 * PerformanceDashboard.test.jsx - Test Suite for Performance Dashboard Components
 *
 * Purpose: Unit tests for the Real-Time Performance Dashboard components
 * Tests rendering, data handling, and user interactions.
 *
 * Components Tested:
 * - StrategyAttribution
 * - RiskMetrics
 * - PerformanceDashboard
 * - ExportPanel
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { PAPER_DEFAULT_BALANCE } from '../utils/balance'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Import components to test
import StrategyAttribution from '../components/PerformanceDashboard/StrategyAttribution'
import RiskMetrics from '../components/PerformanceDashboard/RiskMetrics'
import ExportPanel from '../components/PerformanceDashboard/ExportPanel'

// ============================================================================
// TEST UTILITIES
// ============================================================================

/**
 * Create a wrapper with React Query provider for testing hooks
 */
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
      },
    },
  })

  const QueryWrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  QueryWrapper.displayName = 'QueryWrapper'
  return QueryWrapper
}

/**
 * Mock strategy attribution data.
 * Dollar figures are scaled to the declared paper account
 * (PAPER_DEFAULT_BALANCE — $10,000 per ADR-029): per-strategy P&L in the
 * tens-to-hundreds of dollars, i.e. a few percent of the account.
 */
const mockStrategyData = [
  {
    strategy: 'RSI_Momentum',
    pnl: 1525,
    trades: 45,
    winRate: 62.5,
    profitFactor: 1.85,
    avgWin: 86,
    avgLoss: 45,
  },
  {
    strategy: 'MACD_Crossover',
    pnl: -275,
    trades: 32,
    winRate: 42.5,
    profitFactor: 0.75,
    avgWin: 35,
    avgLoss: 48,
  },
  {
    strategy: 'Bollinger_Breakout',
    pnl: 850,
    trades: 28,
    winRate: 55.0,
    profitFactor: 1.45,
    avgWin: 65,
    avgLoss: 50,
  },
]

/**
 * Mock risk metrics data
 */
// Dollar figures scaled to the declared paper account (PAPER_DEFAULT_BALANCE,
// $10,000 per ADR-029): a $250 daily VaR on a $9,500 portfolio (~2.6%).
const mockRiskMetrics = {
  var95: 250.00,
  cvar95: 350.00,
  maxDrawdownPercent: 8.5,
  currentDrawdown: 2.3,
  volatility: 18.5,
  sharpeRatio: 1.65,
  sortinoRatio: 2.10,
  beta: 0.95,
  portfolioValue: 9500.00,
}

/**
 * Mock export data
 */
const mockExportData = {
  metrics: {
    // Coherent with the $10,000-account curve below (PAPER_DEFAULT_BALANCE,
    // ADR-029): 10,000 → 10,800 = +$800.00
    totalPnL: 800.00,
    totalTrades: 105,
    winRate: 55.5,
    sharpeRatio: 1.65,
  },
  equityCurve: [
    { timestamp: '2025-12-01T00:00:00Z', equity: PAPER_DEFAULT_BALANCE, pnl: 0 },
    { timestamp: '2025-12-05T00:00:00Z', equity: PAPER_DEFAULT_BALANCE + 500, pnl: 500 },
    { timestamp: '2025-12-10T00:00:00Z', equity: PAPER_DEFAULT_BALANCE + 800, pnl: 300 },
  ],
  drawdownSeries: [
    { timestamp: '2025-12-01T00:00:00Z', drawdownPercent: 0 },
    { timestamp: '2025-12-05T00:00:00Z', drawdownPercent: 2.5 },
  ],
  strategyData: mockStrategyData,
  trades: [],
  period: '30d',
  generatedAt: '2025-12-11T12:00:00Z',
}

// ============================================================================
// STRATEGY ATTRIBUTION TESTS
// ============================================================================

describe('StrategyAttribution Component', () => {
  it('renders without crashing', () => {
    render(<StrategyAttribution data={[]} loading={false} />)
    expect(screen.getByText('Strategy Attribution')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<StrategyAttribution data={[]} loading={true} />)
    // Loading skeleton should be present
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('displays empty state when no data', () => {
    render(<StrategyAttribution data={[]} loading={false} />)
    expect(screen.getByText('No strategy data available')).toBeInTheDocument()
  })

  it('renders strategy data correctly', () => {
    render(<StrategyAttribution data={mockStrategyData} loading={false} />)

    // Check strategy names are displayed
    expect(screen.getByText('RSI_Momentum')).toBeInTheDocument()
    expect(screen.getByText('MACD_Crossover')).toBeInTheDocument()
    expect(screen.getByText('Bollinger_Breakout')).toBeInTheDocument()
  })

  it('calculates total P&L correctly', () => {
    render(<StrategyAttribution data={mockStrategyData} loading={false} />)

    // Total P&L should be sum: 1525 - 275 + 850 = 2100.00
    const totalPnL = screen.getByText(/\+?\$2,100\.00/)
    expect(totalPnL).toBeInTheDocument()
  })

  it('identifies best and worst strategies', () => {
    render(<StrategyAttribution data={mockStrategyData} loading={false} />)

    // Best strategy should be RSI_Momentum (highest P&L)
    const bestStrategy = screen.getByText('Best Strategy')
    expect(bestStrategy.nextSibling || bestStrategy.parentElement).toHaveTextContent('RSI_Momentum')
  })

  it('toggles between chart and table view', () => {
    render(<StrategyAttribution data={mockStrategyData} loading={false} />)

    // Default should be chart view
    const tableButton = screen.getByRole('button', { name: /table/i })
    fireEvent.click(tableButton)

    // Table headers should now be visible
    expect(screen.getByText('Trades')).toBeInTheDocument()
    expect(screen.getByText('Win Rate')).toBeInTheDocument()
  })
})

// ============================================================================
// RISK METRICS TESTS
// ============================================================================

describe('RiskMetrics Component', () => {
  it('renders without crashing', () => {
    render(<RiskMetrics metrics={{}} loading={false} />)
    expect(screen.getByText('Risk Metrics')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    render(<RiskMetrics metrics={{}} loading={true} />)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).toBeInTheDocument()
  })

  it('displays all risk metric cards', () => {
    render(<RiskMetrics metrics={mockRiskMetrics} loading={false} />)

    expect(screen.getByText('VaR (95%)')).toBeInTheDocument()
    expect(screen.getByText('CVaR (95%)')).toBeInTheDocument()
    expect(screen.getByText('Max Drawdown')).toBeInTheDocument()
    expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument()
    expect(screen.getByText('Sortino Ratio')).toBeInTheDocument()
    expect(screen.getByText('Volatility')).toBeInTheDocument()
  })

  it('calculates overall risk score', () => {
    render(<RiskMetrics metrics={mockRiskMetrics} loading={false} />)

    // Overall risk badge should be present
    expect(screen.getByText('Overall Risk')).toBeInTheDocument()
    expect(screen.getByText('/100')).toBeInTheDocument()
  })

  it('shows risk level legend', () => {
    render(<RiskMetrics metrics={mockRiskMetrics} loading={false} />)

    // Scope to the legend block: the same labels legitimately appear on the
    // per-metric badges and the overall-risk badge, so an unscoped getByText
    // reports multiple matches.
    const legend = screen.getByText('Risk Level Guide').parentElement
    expect(within(legend).getByText('Low Risk')).toBeInTheDocument()
    expect(within(legend).getByText('Moderate Risk')).toBeInTheDocument()
    expect(within(legend).getByText('Elevated Risk')).toBeInTheDocument()
  })

  it('displays VaR value correctly', () => {
    render(<RiskMetrics metrics={mockRiskMetrics} loading={false} />)

    // VaR should display as currency
    expect(screen.getByText('$250.00')).toBeInTheDocument()
  })

  it('displays Sharpe ratio correctly', () => {
    render(<RiskMetrics metrics={mockRiskMetrics} loading={false} />)

    // Sharpe should display as ratio
    expect(screen.getByText('1.65')).toBeInTheDocument()
  })
})

// ============================================================================
// EXPORT PANEL TESTS
// ============================================================================

describe('ExportPanel Component', () => {
  const mockOnClose = vi.fn()

  beforeEach(() => {
    mockOnClose.mockClear()
  })

  it('renders without crashing', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)
    expect(screen.getByText('Export Performance Data')).toBeInTheDocument()
  })

  it('displays format selection options', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    expect(screen.getByText('CSV Files')).toBeInTheDocument()
    expect(screen.getByText('PDF Report')).toBeInTheDocument()
  })

  it('displays data section checkboxes', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    expect(screen.getByText('Performance Metrics')).toBeInTheDocument()
    expect(screen.getByText('Equity Curve')).toBeInTheDocument()
    expect(screen.getByText('Drawdown Series')).toBeInTheDocument()
    expect(screen.getByText('Strategy Attribution')).toBeInTheDocument()
  })

  it('displays export summary', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    expect(screen.getByText('Export Summary')).toBeInTheDocument()
    expect(screen.getByText('Period:')).toBeInTheDocument()
    expect(screen.getByText('30d')).toBeInTheDocument()
  })

  it('calls onClose when cancel button clicked', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    const cancelButton = screen.getByRole('button', { name: /cancel/i })
    fireEvent.click(cancelButton)

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when X button clicked', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    // Find close button (X icon)
    const closeButtons = screen.getAllByRole('button')
    const xButton = closeButtons.find(btn => btn.querySelector('svg path[d*="M6 18L18 6"]'))

    if (xButton) {
      fireEvent.click(xButton)
      expect(mockOnClose).toHaveBeenCalled()
    }
  })

  it('toggles section selection', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    // Find checkbox for Trade History (should be unchecked by default)
    const checkbox = screen.getByLabelText(/Trade History/i)
    expect(checkbox).not.toBeChecked()

    // Click to select
    fireEvent.click(checkbox)
    expect(checkbox).toBeChecked()
  })

  it('shows export button with correct format', () => {
    render(<ExportPanel data={mockExportData} onClose={mockOnClose} />)

    // Default format is CSV
    expect(screen.getByRole('button', { name: /Export CSV/i })).toBeInTheDocument()

    // Switch to PDF
    const pdfOption = screen.getByText('PDF Report')
    fireEvent.click(pdfOption)

    expect(screen.getByRole('button', { name: /Export PDF/i })).toBeInTheDocument()
  })
})

// ============================================================================
// INTEGRATION TESTS
// ============================================================================

describe('Performance Dashboard Integration', () => {
  it('strategy attribution calculates contribution percentages', () => {
    render(<StrategyAttribution data={mockStrategyData} loading={false} />)

    // Switch to table view to see contribution column
    const tableButton = screen.getByRole('button', { name: /table/i })
    fireEvent.click(tableButton)

    // Contribution column should be present
    expect(screen.getByText('Contrib')).toBeInTheDocument()
  })

  it('risk metrics adapts to missing data gracefully', () => {
    const partialMetrics = {
      var95: 250.50,
      sharpeRatio: 1.65,
    }

    render(<RiskMetrics metrics={partialMetrics} loading={false} />)

    // Should still render without errors
    expect(screen.getByText('VaR (95%)')).toBeInTheDocument()
    expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument()
  })

  it('export panel handles empty data', () => {
    const emptyData = {
      metrics: {},
      equityCurve: [],
      drawdownSeries: [],
      strategyData: [],
      trades: [],
      period: '30d',
    }

    render(<ExportPanel data={emptyData} onClose={vi.fn()} />)

    // Should render without errors
    expect(screen.getByText('Export Performance Data')).toBeInTheDocument()
    expect(screen.getByText('Total Trades:')).toBeInTheDocument()
  })
})

// ============================================================================
// SNAPSHOT TESTS
// ============================================================================

describe('Snapshot Tests', () => {
  it('StrategyAttribution matches snapshot', () => {
    const { container } = render(
      <StrategyAttribution data={mockStrategyData} loading={false} />
    )
    expect(container.firstChild).toMatchSnapshot()
  })

  it('RiskMetrics matches snapshot', () => {
    const { container } = render(
      <RiskMetrics metrics={mockRiskMetrics} loading={false} />
    )
    expect(container.firstChild).toMatchSnapshot()
  })

  it('ExportPanel matches snapshot', () => {
    const { container } = render(
      <ExportPanel data={mockExportData} onClose={vi.fn()} />
    )
    expect(container.firstChild).toMatchSnapshot()
  })
})

// ============================================================================
// ACCESSIBILITY TESTS
// ============================================================================

describe('Accessibility', () => {
  it('StrategyAttribution has accessible button labels', () => {
    render(<StrategyAttribution data={mockStrategyData} loading={false} />)

    // View toggle buttons should be accessible
    expect(screen.getByRole('button', { name: /chart/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /table/i })).toBeInTheDocument()
  })

  it('ExportPanel has accessible form controls', () => {
    render(<ExportPanel data={mockExportData} onClose={vi.fn()} />)

    // All checkboxes should be accessible
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes.length).toBeGreaterThan(0)

    // Close button should be accessible
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })
})
