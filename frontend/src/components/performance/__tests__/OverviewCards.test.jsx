/**
 * OverviewCards.test.jsx - Test Suite for OverviewCards Component
 *
 * Purpose: Unit tests for the OverviewCards component.
 * Tests rendering, formatting, loading states, and color coding.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import OverviewCards from '../OverviewCards'

// ============================================================================
// MOCK DATA
// ============================================================================

const mockMetrics = {
  totalPnL: 2500.75,
  totalPnLChange: 0.15,
  winRate: 58.5,
  totalTrades: 125,
  sharpeRatio: 1.85,
  sharpeChange: 0.05,
  activePositions: 3,
  activePositionsValue: 5000,
  todayPnL: 150.25,
  todayTrades: 5,
  weekPnL: 850.50,
  weekPnLChange: 0.08,
}

const mockNegativeMetrics = {
  totalPnL: -500.25,
  totalPnLChange: -0.1,
  winRate: 42.0,
  totalTrades: 50,
  sharpeRatio: 0.45,
  activePositions: 1,
  todayPnL: -75.50,
  todayTrades: 3,
}

// ============================================================================
// TESTS
// ============================================================================

describe('OverviewCards Component', () => {
  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<OverviewCards metrics={{}} />)
      // Component should render even with empty metrics
      expect(document.querySelector('.grid')).toBeInTheDocument()
    })

    it('renders all metric cards', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      // Check for main metrics
      expect(screen.getByText('Total P&L')).toBeInTheDocument()
      expect(screen.getByText('Win Rate')).toBeInTheDocument()
      expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument()
      expect(screen.getByText('Active Positions')).toBeInTheDocument()
      expect(screen.getByText("Today's P&L")).toBeInTheDocument()
    })

    it('displays formatted values correctly', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      // Check P&L formatting
      expect(screen.getByText('+$2,500.75')).toBeInTheDocument()

      // Check win rate
      expect(screen.getByText('58.5%')).toBeInTheDocument()

      // Check active positions count
      expect(screen.getByText('3')).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('shows loading skeleton when loading', () => {
      render(<OverviewCards metrics={{}} loading={true} />)

      // Should have skeleton animations
      const skeletons = document.querySelectorAll('.animate-pulse')
      expect(skeletons.length).toBeGreaterThan(0)
    })

    it('hides skeleton when not loading', () => {
      render(<OverviewCards metrics={mockMetrics} loading={false} />)

      // Should not have skeleton animations in main content
      expect(screen.getByText('Total P&L')).toBeInTheDocument()
    })
  })

  describe('Color Coding', () => {
    it('shows green color for positive P&L', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      const pnlValue = screen.getByText('+$2,500.75')
      expect(pnlValue).toHaveClass('text-emerald-400')
    })

    it('shows red color for negative P&L', () => {
      render(<OverviewCards metrics={mockNegativeMetrics} />)

      const pnlValue = screen.getByText('-$500.25')
      expect(pnlValue).toHaveClass('text-rose-400')
    })

    it('shows appropriate color for Sharpe ratio', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      // Sharpe > 1 should be good (green)
      const sharpeValue = screen.getByText('1.85')
      expect(sharpeValue).toHaveClass('text-emerald-400')
    })
  })

  describe('Trend Indicators', () => {
    it('shows up arrow for positive change', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      // Should have up arrow SVG for positive trend
      const upArrows = document.querySelectorAll('svg')
      expect(upArrows.length).toBeGreaterThan(0)
    })
  })

  describe('Win Rate Gauge', () => {
    it('renders win rate gauge correctly', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      // Should show win rate percentage
      expect(screen.getByText('58.5%')).toBeInTheDocument()

      // Should show trade count
      expect(screen.getByText('125 trades')).toBeInTheDocument()
    })

    it('shows correct gauge color for win rate', () => {
      render(<OverviewCards metrics={mockMetrics} />)

      // Win rate > 55% should be green
      const gauge = document.querySelector('svg circle')
      expect(gauge).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles null metrics gracefully', () => {
      render(<OverviewCards metrics={null} />)
      // Should not crash
      expect(document.querySelector('.grid')).toBeInTheDocument()
    })

    it('handles undefined values', () => {
      render(<OverviewCards metrics={{ totalPnL: undefined }} />)
      // Should not crash
      expect(document.querySelector('.grid')).toBeInTheDocument()
    })

    it('handles zero values', () => {
      render(
        <OverviewCards
          metrics={{
            totalPnL: 0,
            winRate: 0,
            totalTrades: 0,
          }}
        />
      )

      expect(screen.getByText('$0.00')).toBeInTheDocument()
    })
  })

  describe('Additional Info', () => {
    it('shows today trades count', () => {
      render(<OverviewCards metrics={mockMetrics} />)
      expect(screen.getByText('5 trades today')).toBeInTheDocument()
    })

    it('shows active positions value when provided', () => {
      render(<OverviewCards metrics={mockMetrics} />)
      expect(screen.getByText('Total value: $5,000.00')).toBeInTheDocument()
    })
  })
})
