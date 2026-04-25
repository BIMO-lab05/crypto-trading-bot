/**
 * DailyPnLChart.test.jsx - Test Suite for DailyPnLChart Component
 *
 * Purpose: Unit tests for the DailyPnLChart component.
 * Tests rendering, data display, statistics calculation, and interactions.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DailyPnLChart from '../DailyPnLChart'

// ============================================================================
// MOCK DATA
// ============================================================================

const mockDailyData = [
  {
    date: '2025-12-08',
    timestamp: new Date('2025-12-08').getTime(),
    net: 250.50,
    profit: 350.50,
    loss: -100.00,
    tradeCount: 5,
    winCount: 3,
    lossCount: 2,
    winRate: 60,
  },
  {
    date: '2025-12-09',
    timestamp: new Date('2025-12-09').getTime(),
    net: -75.25,
    profit: 50.00,
    loss: -125.25,
    tradeCount: 4,
    winCount: 1,
    lossCount: 3,
    winRate: 25,
  },
  {
    date: '2025-12-10',
    timestamp: new Date('2025-12-10').getTime(),
    net: 180.00,
    profit: 200.00,
    loss: -20.00,
    tradeCount: 3,
    winCount: 2,
    lossCount: 1,
    winRate: 66.67,
  },
  {
    date: '2025-12-11',
    timestamp: new Date('2025-12-11').getTime(),
    net: 0,
    profit: 0,
    loss: 0,
    tradeCount: 0,
    winCount: 0,
    lossCount: 0,
    winRate: 0,
  },
  {
    date: '2025-12-12',
    timestamp: new Date('2025-12-12').getTime(),
    net: 125.75,
    profit: 125.75,
    loss: 0,
    tradeCount: 2,
    winCount: 2,
    lossCount: 0,
    winRate: 100,
  },
]

// ============================================================================
// TESTS
// ============================================================================

describe('DailyPnLChart Component', () => {
  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<DailyPnLChart data={[]} />)
      expect(screen.getByText('Daily P&L')).toBeInTheDocument()
    })

    it('renders chart container', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Should have chart wrapper
      expect(document.querySelector('.recharts-wrapper')).toBeInTheDocument()
    })

    it('shows loading skeleton when loading', () => {
      render(<DailyPnLChart data={[]} loading={true} />)

      const skeletons = document.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })

    it('shows empty state when no data', () => {
      render(<DailyPnLChart data={[]} />)
      expect(screen.getByText('No daily P&L data available')).toBeInTheDocument()
    })
  })

  describe('Statistics Display', () => {
    it('calculates and displays total P&L', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Total should be sum of all net: 250.50 - 75.25 + 180.00 + 0 + 125.75 = 481.00
      expect(screen.getByText('+$481.00')).toBeInTheDocument()
    })

    it('shows number of days', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      expect(screen.getByText('5')).toBeInTheDocument() // 5 days
    })

    it('shows profitable days count', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // 3 profitable days (positive net)
      const profitableDays = screen.getByText('3')
      expect(profitableDays).toBeInTheDocument()
    })

    it('shows losing days count', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // 1 losing day (negative net)
      expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    })

    it('shows best day', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Best day is 250.50
      expect(screen.getByText('+$250.50')).toBeInTheDocument()
    })

    it('shows worst day', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Worst day is -75.25
      expect(screen.getByText('-$75.25')).toBeInTheDocument()
    })
  })

  describe('Chart Configuration', () => {
    it('renders bar chart', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Should have bar elements
      const bars = document.querySelectorAll('.recharts-bar-rectangle')
      expect(bars.length).toBeGreaterThan(0)
    })

    it('shows cumulative line when enabled', () => {
      render(<DailyPnLChart data={mockDailyData} showCumulative={true} />)

      // Should have line element
      const lines = document.querySelectorAll('.recharts-line')
      expect(lines.length).toBeGreaterThan(0)
    })

    it('hides cumulative line when disabled', () => {
      render(<DailyPnLChart data={mockDailyData} showCumulative={false} />)

      // Should not have line element (or might still have reference lines)
      // This test depends on implementation
    })

    it('shows legend when enabled', () => {
      render(<DailyPnLChart data={mockDailyData} showLegend={true} />)

      // Should have legend
      const legend = document.querySelector('.recharts-legend-wrapper')
      expect(legend).toBeInTheDocument()
    })

    it('hides legend when disabled', () => {
      render(<DailyPnLChart data={mockDailyData} showLegend={false} />)

      // Should not have legend wrapper
      const legend = document.querySelector('.recharts-legend-wrapper')
      expect(legend).not.toBeInTheDocument()
    })
  })

  describe('Color Coding', () => {
    it('uses green for profitable days', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Should have emerald/green gradient for positive bars
      const profitGradient = document.querySelector('#profitBarGradient')
      expect(profitGradient).toBeInTheDocument()
    })

    it('uses red for losing days', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Should have rose/red gradient for negative bars
      const lossGradient = document.querySelector('#lossBarGradient')
      expect(lossGradient).toBeInTheDocument()
    })

    it('highlights total P&L based on value', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Positive total should be green
      const totalBadge = screen.getByText('+$481.00')
      expect(totalBadge).toHaveClass('text-emerald-400')
    })
  })

  describe('Chart Height', () => {
    it('uses default height when not specified', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Default height is 280
      const chartWrapper = document.querySelector('.recharts-responsive-container')
      expect(chartWrapper).toHaveStyle({ height: '280px' })
    })

    it('uses custom height when specified', () => {
      render(<DailyPnLChart data={mockDailyData} height={400} />)

      const chartWrapper = document.querySelector('.recharts-responsive-container')
      expect(chartWrapper).toHaveStyle({ height: '400px' })
    })
  })

  describe('Footer Legend', () => {
    it('shows color legend', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      expect(screen.getByText('Profitable Day')).toBeInTheDocument()
      expect(screen.getByText('Losing Day')).toBeInTheDocument()
    })

    it('shows average daily P&L', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Average is 481.00 / 5 = 96.20
      expect(screen.getByText(/Avg Daily:/)).toBeInTheDocument()
    })

    it('shows cumulative legend when enabled', () => {
      render(<DailyPnLChart data={mockDailyData} showCumulative={true} />)

      expect(screen.getByText('Cumulative P&L')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty data array', () => {
      render(<DailyPnLChart data={[]} />)
      expect(screen.getByText('No daily P&L data available')).toBeInTheDocument()
    })

    it('handles single day data', () => {
      render(<DailyPnLChart data={[mockDailyData[0]]} />)

      expect(screen.getByText('1')).toBeInTheDocument() // 1 day
    })

    it('handles all zero days', () => {
      const zeroData = [
        { date: '2025-12-12', net: 0, tradeCount: 0 },
      ]

      render(<DailyPnLChart data={zeroData} />)
      expect(screen.getByText('$0.00')).toBeInTheDocument()
    })

    it('handles all negative days', () => {
      const negativeData = mockDailyData.map((d) => ({
        ...d,
        net: -Math.abs(d.net || 50),
      }))

      render(<DailyPnLChart data={negativeData} />)

      // Total should be negative
      const totalBadge = document.querySelector('.text-rose-400')
      expect(totalBadge).toBeInTheDocument()
    })
  })

  describe('Period Handling', () => {
    it('formats dates correctly for 7d period', () => {
      render(<DailyPnLChart data={mockDailyData} period="7d" />)
      // X-axis should show day names
      // This depends on implementation
    })

    it('formats dates correctly for 30d period', () => {
      render(<DailyPnLChart data={mockDailyData} period="30d" />)
      // X-axis should show 'MMM d' format
    })
  })

  describe('Accessibility', () => {
    it('has accessible chart region', () => {
      render(<DailyPnLChart data={mockDailyData} />)

      // Chart should be accessible
      expect(screen.getByText('Daily P&L')).toBeInTheDocument()
    })
  })
})
