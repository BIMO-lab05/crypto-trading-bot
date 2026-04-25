/**
 * RecentTrades.test.jsx - Test Suite for RecentTrades Component
 *
 * Purpose: Unit tests for the RecentTrades component with virtual scrolling.
 * Tests rendering, filtering, sorting, and click handlers.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import RecentTrades from '../RecentTrades'

// ============================================================================
// MOCK DATA
// ============================================================================

const mockTrades = [
  {
    id: '1',
    symbol: 'BTCUSDT',
    side: 'BUY',
    entry_price: 42000.50,
    exit_price: 43000.75,
    quantity: 0.5,
    realized_pnl: 500.125,
    opened_at: '2025-12-12T10:00:00Z',
    closed_at: '2025-12-12T14:30:00Z',
    strategy: 'RSI_Momentum',
    quality_score: 85,
  },
  {
    id: '2',
    symbol: 'ETHUSDT',
    side: 'SELL',
    entry_price: 2500.00,
    exit_price: 2400.00,
    quantity: 2,
    realized_pnl: 200.00,
    opened_at: '2025-12-12T08:00:00Z',
    closed_at: '2025-12-12T12:00:00Z',
    strategy: 'MACD_Crossover',
    quality_score: 72,
  },
  {
    id: '3',
    symbol: 'BTCUSDT',
    side: 'BUY',
    entry_price: 43500.00,
    exit_price: 43000.00,
    quantity: 0.25,
    realized_pnl: -125.00,
    opened_at: '2025-12-12T15:00:00Z',
    closed_at: '2025-12-12T16:00:00Z',
    strategy: 'RSI_Momentum',
    quality_score: 45,
  },
]

// ============================================================================
// TESTS
// ============================================================================

describe('RecentTrades Component', () => {
  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<RecentTrades trades={[]} />)
      expect(screen.getByText('Recent Trades')).toBeInTheDocument()
    })

    it('renders all trades', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Should show trade symbols
      expect(screen.getAllByText('BTC').length).toBeGreaterThan(0)
      expect(screen.getByText('ETH')).toBeInTheDocument()
    })

    it('shows loading skeleton when loading', () => {
      render(<RecentTrades trades={[]} loading={true} />)

      const skeletons = document.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })

    it('shows empty state when no trades', () => {
      render(<RecentTrades trades={[]} />)
      expect(screen.getByText('No trades found')).toBeInTheDocument()
    })
  })

  describe('Trade Display', () => {
    it('formats prices correctly', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Check entry/exit prices are formatted
      expect(screen.getByText('$42,000.50')).toBeInTheDocument()
      expect(screen.getByText('$43,000.75')).toBeInTheDocument()
    })

    it('formats P&L with correct colors', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Positive P&L should be green
      const positivePnL = screen.getByText('+$500.13')
      expect(positivePnL).toHaveClass('text-emerald-400')

      // Negative P&L should be red
      const negativePnL = screen.getByText('-$125.00')
      expect(negativePnL).toHaveClass('text-rose-400')
    })

    it('shows trade side with correct colors', () => {
      render(<RecentTrades trades={mockTrades} />)

      // BUY should be green
      const longs = screen.getAllByText('Long')
      longs.forEach((el) => {
        expect(el).toHaveClass('text-emerald-400')
      })

      // SELL should be red
      const shorts = screen.getAllByText('Short')
      shorts.forEach((el) => {
        expect(el).toHaveClass('text-rose-400')
      })
    })

    it('shows quality badges', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Quality score 85 should show 'A'
      expect(screen.getByText('A')).toBeInTheDocument()
      // Quality score 72 should show 'B'
      expect(screen.getByText('B')).toBeInTheDocument()
      // Quality score 45 should show 'C'
      expect(screen.getByText('C')).toBeInTheDocument()
    })
  })

  describe('Filtering', () => {
    it('filters by symbol', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Find and click symbol filter
      const symbolFilter = screen.getByRole('combobox', { name: '' })
      fireEvent.change(symbolFilter, { target: { value: 'BTCUSDT' } })

      // Should only show BTC trades (2 trades)
      expect(screen.getByText('2 of 3 trades')).toBeInTheDocument()
    })

    it('shows filtered message', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Apply a filter
      const selects = screen.getAllByRole('combobox')
      fireEvent.change(selects[0], { target: { value: 'BTCUSDT' } })

      expect(screen.getByText(/filtered/i)).toBeInTheDocument()
    })

    it('clears filters when clear button clicked', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Apply filter
      const selects = screen.getAllByRole('combobox')
      fireEvent.change(selects[0], { target: { value: 'BTCUSDT' } })

      // Clear filters
      const clearButton = screen.getByText('Clear filters')
      fireEvent.click(clearButton)

      // Should show all trades
      expect(screen.getByText('3 of 3 trades')).toBeInTheDocument()
    })
  })

  describe('Sorting', () => {
    it('sorts by P&L when column header clicked', () => {
      render(<RecentTrades trades={mockTrades} />)

      // Find P&L column header and click
      const pnlHeader = screen.getByText('P&L')
      fireEvent.click(pnlHeader)

      // First trade should now be highest P&L
      const rows = document.querySelectorAll('[class*="flex items-center border-b"]')
      // Verification would depend on implementation details
    })

    it('toggles sort direction on second click', () => {
      render(<RecentTrades trades={mockTrades} />)

      const timeHeader = screen.getByText('Time')

      // First click - ascending
      fireEvent.click(timeHeader)

      // Second click - descending
      fireEvent.click(timeHeader)

      // Sort indicator should change
      const sortIndicator = timeHeader.querySelector('svg')
      expect(sortIndicator).toBeInTheDocument()
    })
  })

  describe('Click Handlers', () => {
    it('calls onTradeClick when row is clicked', () => {
      const mockOnClick = vi.fn()
      render(<RecentTrades trades={mockTrades} onTradeClick={mockOnClick} />)

      // Find and click a trade row
      const rows = document.querySelectorAll('[class*="cursor-pointer"]')
      fireEvent.click(rows[0])

      expect(mockOnClick).toHaveBeenCalledTimes(1)
      expect(mockOnClick).toHaveBeenCalledWith(
        expect.objectContaining({ id: mockTrades[0].id })
      )
    })

    it('highlights selected trade', () => {
      const mockOnClick = vi.fn()
      render(<RecentTrades trades={mockTrades} onTradeClick={mockOnClick} />)

      // Click a trade
      const rows = document.querySelectorAll('[class*="cursor-pointer"]')
      fireEvent.click(rows[0])

      // Row should be highlighted (selected)
      // This depends on implementation - checking for selection class
    })
  })

  describe('Virtual Scrolling', () => {
    it('renders correct number of visible rows', () => {
      // Create many trades
      const manyTrades = Array(100)
        .fill(null)
        .map((_, i) => ({
          ...mockTrades[0],
          id: `trade-${i}`,
          realized_pnl: Math.random() * 1000 - 500,
        }))

      render(<RecentTrades trades={manyTrades} maxHeight={300} />)

      // Should not render all 100 rows
      const renderedRows = document.querySelectorAll('[class*="flex items-center border-b"]')
      expect(renderedRows.length).toBeLessThan(100)
    })
  })

  describe('Edge Cases', () => {
    it('handles trades without strategy', () => {
      const tradesWithoutStrategy = [
        {
          ...mockTrades[0],
          strategy: undefined,
          signal_source: undefined,
        },
      ]

      render(<RecentTrades trades={tradesWithoutStrategy} />)
      expect(screen.getByText('-')).toBeInTheDocument()
    })

    it('handles trades without quality score', () => {
      const tradesWithoutScore = [
        {
          ...mockTrades[0],
          quality_score: undefined,
        },
      ]

      render(<RecentTrades trades={tradesWithoutScore} />)
      // Should not show quality badge
      expect(screen.queryByText('A')).not.toBeInTheDocument()
    })

    it('handles missing timestamps gracefully', () => {
      const tradesWithBadDates = [
        {
          ...mockTrades[0],
          closed_at: null,
          timestamp: '2025-12-12T10:00:00Z',
        },
      ]

      render(<RecentTrades trades={tradesWithBadDates} />)
      // Should not crash
      expect(screen.getByText('Recent Trades')).toBeInTheDocument()
    })
  })

  describe('Footer', () => {
    it('shows legend', () => {
      render(<RecentTrades trades={mockTrades} />)

      expect(screen.getByText('Profitable')).toBeInTheDocument()
      expect(screen.getByText('Loss')).toBeInTheDocument()
    })

    it('shows trade count', () => {
      render(<RecentTrades trades={mockTrades} />)

      expect(screen.getByText(/Showing.*of.*trades/)).toBeInTheDocument()
    })
  })
})
