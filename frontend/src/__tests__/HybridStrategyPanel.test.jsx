/**
 * HybridStrategyPanel.test.jsx — the tile must never turn absent data into a
 * measured-looking zero (2026-08-21).
 *
 * Context. Before this suite the tile read `status.hybrid_strategy_stats || {}`
 * and `hybrid.trend_pct || 0`. The backend omitted `hybrid_strategy_stats`
 * entirely in ensemble mode, so a dead code path rendered as
 * "Trend-Following 0.0% — 0 signals routed" next to a hardcoded green "Live"
 * dot, indistinguishable from a working router in a one-sided market. See
 * docs/PIPELINE_MAP.md §0.
 *
 * These tests pin the three properties that make that impossible:
 *   1. null percentages render "n/a", never "0.0%"
 *   2. routing_mode is surfaced verbatim, so an ADVISORY router cannot be
 *      presented as one that steers execution
 *   3. a measured zero (0.0% with a real denominator) still renders as 0.0%
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getStatus = vi.fn()
vi.mock('../services/api', () => ({
  tradingAPI: {
    getStatus: (...a) => getStatus(...a),
  },
}))

import HybridStrategyPanel from '../components/HybridStrategyPanel'

function renderPanel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <HybridStrategyPanel />
    </QueryClientProvider>
  )
}

const INACTIVE_STATS = {
  routing_mode: 'inactive',
  adx_threshold: 25.0,
  total_signals: 0,
  trend_signals: 0,
  mean_reversion_signals: 0,
  executed_signals: 0,
  observed_signals: 0,
  trend_pct: null,
  mean_reversion_pct: null,
}

const ADVISORY_STATS = {
  routing_mode: 'advisory',
  adx_threshold: 25.0,
  total_signals: 180,
  trend_signals: 180,
  mean_reversion_signals: 0,
  executed_signals: 0,
  observed_signals: 180,
  trend_pct: 100.0,
  mean_reversion_pct: 0.0,
}

function payload(hybrid, extra = {}) {
  return {
    success: true,
    status: {
      strategy_mode: 'ensemble',
      hybrid_strategy_stats: hybrid,
      regime_detector_stats: {
        regime_distribution: { STRONG_TREND: 200, RANGING: 100 },
      },
      signal_funnel: { last_event_at: new Date().toISOString(), stages: [] },
      ...extra,
    },
  }
}

beforeEach(() => {
  getStatus.mockReset()
})

describe('HybridStrategyPanel honesty guarantees', () => {
  it('renders "n/a" — not "0.0%" — when the router has made no decisions', async () => {
    getStatus.mockResolvedValue(payload(INACTIVE_STATS))
    renderPanel()

    const trend = await screen.findByTestId('trend-pct')
    expect(trend.textContent).toBe('n/a')
    expect(screen.getByTestId('mean-rev-pct').textContent).toBe('n/a')
    expect(screen.getByTestId('total-routing-decisions').textContent).toBe('0')
  })

  it('says NO DECISIONS when routing_mode is inactive', async () => {
    getStatus.mockResolvedValue(payload(INACTIVE_STATS))
    renderPanel()

    const badge = await screen.findByTestId('routing-mode-badge')
    expect(badge.textContent).toContain('NO DECISIONS')
  })

  it('labels an advisory router as ADVISORY, not as the executing strategy', async () => {
    getStatus.mockResolvedValue(payload(ADVISORY_STATS))
    renderPanel()

    const badge = await screen.findByTestId('routing-mode-badge')
    expect(badge.textContent).toContain('ADVISORY')
    // The distinction the old tile could not make.
    expect(badge.textContent).toMatch(/configured strategy executes/i)
  })

  it('renders a MEASURED zero as 0.0% when the denominator is real', async () => {
    getStatus.mockResolvedValue(payload(ADVISORY_STATS))
    renderPanel()

    await waitFor(() =>
      expect(screen.getByTestId('trend-pct').textContent).toBe('100.0%')
    )
    expect(screen.getByTestId('mean-rev-pct').textContent).toBe('0.0%')
    expect(screen.getByTestId('total-routing-decisions').textContent).toBe('180')
  })

  it('percentages sum to 100 when decisions exist', async () => {
    getStatus.mockResolvedValue(
      payload({
        ...ADVISORY_STATS,
        trend_signals: 120,
        mean_reversion_signals: 60,
        trend_pct: 66.66666,
        mean_reversion_pct: 33.33333,
      })
    )
    renderPanel()

    await waitFor(() =>
      expect(screen.getByTestId('trend-pct').textContent).toBe('66.7%')
    )
    const trend = parseFloat(screen.getByTestId('trend-pct').textContent)
    const mean = parseFloat(screen.getByTestId('mean-rev-pct').textContent)
    expect(trend + mean).toBeCloseTo(100.0, 1)
  })

  it('flags an engine that does not report routing_mode at all', async () => {
    // A build predating 2026-08-21. Its counters cannot be interpreted, and
    // saying so beats rendering them as if they were meaningful.
    const { routing_mode, ...legacy } = ADVISORY_STATS
    getStatus.mockResolvedValue(payload(legacy))
    renderPanel()

    const badge = await screen.findByTestId('routing-mode-badge')
    expect(badge.textContent).toContain('UNREPORTED')
  })

  it('derives liveness from engine activity, not from a hardcoded dot', async () => {
    const stale = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    getStatus.mockResolvedValue(
      payload(ADVISORY_STATS, {
        signal_funnel: { last_event_at: stale, stages: [] },
      })
    )
    renderPanel()

    const liveness = await screen.findByTestId('routing-liveness')
    expect(liveness.textContent).toContain('Stale')
    expect(liveness.textContent).not.toContain('Live ·')
  })
})
