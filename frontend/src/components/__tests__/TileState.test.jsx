/**
 * TileState.test.jsx — tests for the shared <TileState/> wrapper.
 *
 * Plan 06-05 Task 1 behaviors. Precedence rule (F-05 — D-13 intent):
 *   error > loading > empty > stale-overlay > children
 * `forceStale` ONLY toggles between branches 4 and 5; it does NOT bypass
 * branches 1-3 (errors are LOUD; a LABELED_STALE tile that hits a real
 * error still shows the Failed UI).
 *
 * Behaviors covered (10 tests):
 *   1. isLoading && !data         → skeleton; children NOT rendered
 *   2. isSuccess && isEmpty(data) → "No data yet"; children NOT rendered
 *   3. isError, response.status=503 → /Failed \(503\)/ + Retry → refetch()
 *   4. isError, no response (network) → /Failed \(network\)/ fallback
 *   5. isSuccess && !isEmpty(data) → children
 *   6a. lastUpdatedAt 90s old, thresholdKey="ticker" → children + "stale" badge
 *   6b. lastUpdatedAt 30s old, thresholdKey="ticker" → children, NO stale badge
 *   7. forceStale + isSuccess + !isEmpty → children + "stale" badge
 *   8. STALE_THRESHOLDS_MS exports keys: ticker, signals, performance,
 *      portfolio, positions, default
 *   9 (F-05). forceStale + isError → Failed UI; NO stale badge; NO children
 *   10 (F-05). forceStale + isLoading → skeleton; NO stale badge
 */

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import TileState, { STALE_THRESHOLDS_MS } from '../TileState'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a React-Query-shaped result object. Defaults to the success-empty
 * baseline; override fields per test.
 */
function makeQuery(overrides = {}) {
  return {
    isLoading: false,
    isFetching: false,
    isError: false,
    isSuccess: true,
    error: null,
    data: null,
    refetch: vi.fn(),
    ...overrides,
  }
}

function renderTile(props = {}, children = <div data-testid="body">BODY</div>) {
  return render(
    <TileState title="Test Tile" query={makeQuery()} {...props}>
      {children}
    </TileState>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TileState — loading branch', () => {
  it('renders skeleton when isLoading && !data and does NOT render children', () => {
    const q = makeQuery({ isLoading: true, isSuccess: false, data: undefined })
    const { container } = render(
      <TileState title="Loading Tile" query={q}>
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    // children must NOT render
    expect(screen.queryByTestId('body')).toBeNull()
    // skeleton: at least one element with the surface2 background token
    const html = container.innerHTML
    expect(html.includes('#1f1f24') || html.includes('rgb(31, 31, 36)')).toBe(true)
  })
})

describe('TileState — empty branch', () => {
  it('renders "No data yet" when isSuccess && isEmpty(data) and does NOT render children', () => {
    const q = makeQuery({ data: null })
    render(
      <TileState title="Empty Tile" query={q}>
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByText(/no data yet/i)).toBeInTheDocument()
    expect(screen.queryByTestId('body')).toBeNull()
  })

  it('honors a custom isEmpty predicate', () => {
    const q = makeQuery({ data: { positions: [] } })
    render(
      <TileState
        title="Active Trades"
        query={q}
        isEmpty={(d) => !d || (d.positions ?? []).length === 0}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByText(/no data yet/i)).toBeInTheDocument()
    expect(screen.queryByTestId('body')).toBeNull()
  })
})

describe('TileState — error branch (D-14)', () => {
  it('renders "Failed (503)" + Retry; clicking Retry calls refetch()', () => {
    const refetch = vi.fn()
    const q = makeQuery({
      isError: true,
      isSuccess: false,
      error: { response: { status: 503, data: { detail: 'service unavailable' } } },
      refetch,
    })
    render(
      <TileState title="Tile X" query={q}>
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByText(/Failed \(503\)/i)).toBeInTheDocument()
    expect(screen.queryByTestId('body')).toBeNull()
    const btn = screen.getByRole('button', { name: /retry/i })
    fireEvent.click(btn)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('renders "Failed (network)" fallback when error has no response.status', () => {
    const q = makeQuery({
      isError: true,
      isSuccess: false,
      error: { message: 'Network Error' },
    })
    render(
      <TileState title="Tile Y" query={q}>
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByText(/Failed \(network\)/i)).toBeInTheDocument()
    // ensure raw error.message is NOT rendered (D-14: forbid error.message)
    expect(screen.queryByText(/Network Error/)).toBeNull()
  })
})

describe('TileState — success non-empty branch', () => {
  it('renders children when isSuccess && !isEmpty(data)', () => {
    const q = makeQuery({ data: { positions: [{ id: 1 }] } })
    render(
      <TileState
        title="Active Trades"
        query={q}
        isEmpty={(d) => !d || (d.positions ?? []).length === 0}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByTestId('body')).toBeInTheDocument()
  })
})

describe('TileState — stale-overlay branch (D-15)', () => {
  it('renders children + stale badge when lastUpdatedAt is 90s old and thresholdKey="ticker"', () => {
    const q = makeQuery({ data: { positions: [{ id: 1 }] } })
    const lastUpdated = new Date(Date.now() - 90_000).toISOString()
    render(
      <TileState
        title="Ticker"
        query={q}
        thresholdKey="ticker"
        lastUpdatedAt={lastUpdated}
        isEmpty={() => false}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByTestId('body')).toBeInTheDocument()
    expect(screen.getByText(/stale/i)).toBeInTheDocument()
  })

  it('renders children WITHOUT stale badge when lastUpdatedAt is 30s old and thresholdKey="ticker"', () => {
    const q = makeQuery({ data: { positions: [{ id: 1 }] } })
    const lastUpdated = new Date(Date.now() - 30_000).toISOString()
    render(
      <TileState
        title="Ticker"
        query={q}
        thresholdKey="ticker"
        lastUpdatedAt={lastUpdated}
        isEmpty={() => false}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByTestId('body')).toBeInTheDocument()
    expect(screen.queryByText(/^stale$/i)).toBeNull()
  })

  it('forceStale + isSuccess + non-empty → children + stale badge', () => {
    const q = makeQuery({ data: { positions: [{ id: 1 }] } })
    render(
      <TileState
        title="Phase3"
        query={q}
        forceStale
        isEmpty={() => false}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    expect(screen.getByTestId('body')).toBeInTheDocument()
    expect(screen.getByText(/stale/i)).toBeInTheDocument()
  })
})

describe('TileState — STALE_THRESHOLDS_MS export', () => {
  it('exports the documented threshold keys', () => {
    expect(STALE_THRESHOLDS_MS).toBeDefined()
    expect(STALE_THRESHOLDS_MS.ticker).toBe(60_000)
    expect(STALE_THRESHOLDS_MS.signals).toBe(30_000)
    expect(STALE_THRESHOLDS_MS.performance).toBe(5 * 60_000)
    expect(STALE_THRESHOLDS_MS.portfolio).toBe(30_000)
    expect(STALE_THRESHOLDS_MS.positions).toBe(30_000)
    expect(STALE_THRESHOLDS_MS.default).toBe(60_000)
  })
})

describe('TileState — F-05 precedence (errors are LOUD)', () => {
  // Test 9: forceStale + isError → error UI wins; stale badge MUST NOT appear; children MUST NOT render.
  it('forceStale=true AND isError=true → Failed UI + Retry; NO stale badge; NO children', () => {
    const refetch = vi.fn()
    const q = makeQuery({
      isError: true,
      isSuccess: false,
      error: { response: { status: 500, data: { detail: 'kaboom' } } },
      refetch,
    })
    render(
      <TileState
        title="Forced-stale tile with real error"
        query={q}
        forceStale
        isEmpty={() => false}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    // Failed UI present
    expect(screen.getByText(/Failed \(500\)/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    // children NOT rendered
    expect(screen.queryByTestId('body')).toBeNull()
    // stale badge NOT present (precedence: error wins)
    expect(screen.queryByText(/^stale$/i)).toBeNull()
  })

  // Test 10: forceStale + isLoading → skeleton wins; stale badge MUST NOT appear.
  it('forceStale=true AND isLoading=true → skeleton; NO stale badge', () => {
    const q = makeQuery({
      isLoading: true,
      isSuccess: false,
      data: undefined,
    })
    const { container } = render(
      <TileState
        title="Forced-stale tile while loading"
        query={q}
        forceStale
        isEmpty={() => false}
      >
        <div data-testid="body">BODY</div>
      </TileState>,
    )
    // children NOT rendered
    expect(screen.queryByTestId('body')).toBeNull()
    // skeleton: surface2 background must be present
    const html = container.innerHTML
    expect(html.includes('#1f1f24') || html.includes('rgb(31, 31, 36)')).toBe(true)
    // stale badge NOT present
    expect(screen.queryByText(/^stale$/i)).toBeNull()
  })
})
