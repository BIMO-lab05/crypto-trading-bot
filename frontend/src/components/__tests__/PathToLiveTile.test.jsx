/**
 * PathToLiveTile.test.jsx — behavioral tests for the Phase 10 path-to-live tile.
 *
 * Gap coverage (DASHLIVE-01/03, task 10-02-02):
 *   1. Banner reads overall from useCarryIns.data.overall — NOT client-recomputed
 *      (D-10-16: carryInsQuery is authoritative; useLiveReadiness used only as fallback)
 *   2. data-testid="path-to-live-tile" present always (outside TileState)
 *   3. data-testid="path-to-live-banner" present when data loaded
 *   4. Per-check rows use data-testid="path-to-live-check-{name}"
 *   5. Carry-in rows use data-testid="path-to-live-carry-in-{id}"
 *   6. Check rows source from carryInsQuery.data.live_readiness.checks (primary)
 *   7. Check rows fall back to useLiveReadiness.data.checks when carryIns lacks them
 *   8. ALMOST banner shows subtitle with elapsed/required timing
 *   9. open carry-in chip has amber classes; closed carry-in chip has emerald classes
 *  10. isError state: tile root renders but TileState shows error UI (not banner/checks)
 *
 * Adversarial key test (test 1):
 *   Mock useCarryIns returning overall="READY" but useLiveReadiness returning
 *   a live_readiness with overall="FAIL". If tile recomputes overall client-side
 *   from the checks it would show DO_NOT_FLIP. If it correctly reads the server
 *   value it shows READY (bg-emerald-700). This PROVES the D-10-16 authority rule.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock hooks BEFORE component import — vitest hoists vi.mock
vi.mock('../../hooks/useCarryIns', () => ({
  useCarryIns: vi.fn(),
  default: vi.fn(),
}))

vi.mock('../../hooks/useLiveReadiness', () => ({
  useLiveReadiness: vi.fn(),
  default: vi.fn(),
}))

import { useCarryIns } from '../../hooks/useCarryIns'
import { useLiveReadiness } from '../../hooks/useLiveReadiness'
import PathToLiveTile from '../PathToLiveTile'

// ---------------------------------------------------------------------------
// Query mock helpers (mirrors TileState.test.jsx makeQuery pattern)
// ---------------------------------------------------------------------------

function makeCarryInsQuery(overrides = {}) {
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

function makeLiveReadinessQuery(overrides = {}) {
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

const SIX_PASS_CHECKS = [
  { check: 'cap', status: 'PASS', detail: 'cap ≤ 2%' },
  { check: 'paper_mode', status: 'PASS', detail: 'paper' },
  { check: 'trading_mode', status: 'PASS', detail: 'paper' },
  { check: 'ack', status: 'PASS', detail: 'ACK present' },
  { check: 'emergency_stop', status: 'PASS', detail: 'not active' },
  { check: 'dsr_evidence', status: 'PASS', detail: 'dsr=0.96' },
]

const SIX_FAIL_CHECKS = [
  { check: 'cap', status: 'FAIL', detail: 'cap too high' },
  { check: 'paper_mode', status: 'FAIL', detail: 'live' },
  { check: 'trading_mode', status: 'FAIL', detail: 'live' },
  { check: 'ack', status: 'FAIL', detail: 'missing' },
  { check: 'emergency_stop', status: 'FAIL', detail: 'active' },
  { check: 'dsr_evidence', status: 'FAIL', detail: 'missing' },
]

const CARRY_INS_LIST = [
  { id: 'OP-01', state: 'open', description: 'Risk cap restored to ≤2%' },
  { id: 'OP-02', state: 'closed', description: 'Paper-trading confirmed', closed_at: '2026-05-18T00:00:00Z' },
]

/** Full valid carryIns payload with all required keys. */
function makeCarryInsData(overrides = {}) {
  return {
    schema_version: 1,
    evaluated_at: '2026-05-18T00:00:00+00:00',
    overall: 'DO_NOT_FLIP',
    carry_ins: CARRY_INS_LIST,
    window: {
      first_all_pass_at: null,
      elapsed_seconds: 0,
      required_seconds: 86400,
      remaining_seconds: 86400,
    },
    preflight_summary: { pass: 0, fail: 6, unknown: 0 },
    live_readiness: {
      schema_version: 1,
      overall: 'FAIL',
      evaluated_at: '2026-05-18T00:00:00+00:00',
      checks: SIX_FAIL_CHECKS,
    },
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  // Safe default: both hooks return empty success
  useLiveReadiness.mockReturnValue(makeLiveReadinessQuery({ data: null }))
  useCarryIns.mockReturnValue(makeCarryInsQuery({ data: null }))
})

// ---------------------------------------------------------------------------
// Test 1: D-10-16 authority — banner reads server overall, no client recompute
// ---------------------------------------------------------------------------

describe('PathToLiveTile — D-10-16 authority (critical adversarial)', () => {
  it('shows READY banner when carryIns.overall="READY" even if liveReadiness checks are FAIL', () => {
    // Adversarial: server says READY but the per-check data would compute to DO_NOT_FLIP
    // if the tile recomputed client-side. This discriminates the authority rule.
    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: makeCarryInsData({
        overall: 'READY',
        live_readiness: {
          schema_version: 1,
          overall: 'FAIL',
          evaluated_at: '2026-05-18T00:00:00+00:00',
          checks: SIX_FAIL_CHECKS,
        },
      }),
    }))
    useLiveReadiness.mockReturnValue(makeLiveReadinessQuery({
      data: {
        schema_version: 1,
        overall: 'FAIL',
        evaluated_at: '2026-05-18T00:00:00+00:00',
        checks: SIX_FAIL_CHECKS,
      },
    }))

    render(<PathToLiveTile />)

    const banner = screen.getByTestId('path-to-live-banner')
    // READY must use bg-emerald-700, not bg-rose-700 (DO_NOT_FLIP)
    expect(banner.className).toContain('bg-emerald-700')
    expect(banner.className).not.toContain('bg-rose-700')
    expect(banner.textContent).toContain('READY')
  })

  it('shows DO_NOT_FLIP banner when carryIns.overall="DO_NOT_FLIP" even if checks are all PASS', () => {
    // Server says DO_NOT_FLIP (e.g. still building window) even though checks pass
    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: makeCarryInsData({
        overall: 'DO_NOT_FLIP',
        live_readiness: {
          schema_version: 1,
          overall: 'PASS',
          evaluated_at: '2026-05-18T00:00:00+00:00',
          checks: SIX_PASS_CHECKS,
        },
      }),
    }))

    render(<PathToLiveTile />)

    const banner = screen.getByTestId('path-to-live-banner')
    expect(banner.className).toContain('bg-rose-700')
    expect(banner.textContent).toContain('DO NOT FLIP')
  })
})

// ---------------------------------------------------------------------------
// Test 2+3: testid contracts
// ---------------------------------------------------------------------------

describe('PathToLiveTile — testid contracts', () => {
  it('root data-testid="path-to-live-tile" always renders (outside TileState)', () => {
    // Even with no data (loading state), the tile root must be present
    useCarryIns.mockReturnValue(makeCarryInsQuery({ isLoading: true, isSuccess: false, data: undefined }))

    render(<PathToLiveTile />)

    expect(screen.getByTestId('path-to-live-tile')).toBeTruthy()
  })

  it('data-testid="path-to-live-banner" renders inside successful tile', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({ data: makeCarryInsData() }))

    render(<PathToLiveTile />)

    expect(screen.getByTestId('path-to-live-banner')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Test 4: per-check row testids
// ---------------------------------------------------------------------------

describe('PathToLiveTile — per-check row testids', () => {
  it('renders data-testid="path-to-live-check-{name}" for each check in carryIns.live_readiness.checks', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: makeCarryInsData({ overall: 'DO_NOT_FLIP' }),
    }))

    render(<PathToLiveTile />)

    for (const chk of SIX_FAIL_CHECKS) {
      expect(screen.getByTestId(`path-to-live-check-${chk.check}`)).toBeTruthy()
    }
  })
})

// ---------------------------------------------------------------------------
// Test 5: carry-in row testids
// ---------------------------------------------------------------------------

describe('PathToLiveTile — carry-in row testids', () => {
  it('renders data-testid="path-to-live-carry-in-{id}" for each carry-in', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({ data: makeCarryInsData() }))

    render(<PathToLiveTile />)

    expect(screen.getByTestId('path-to-live-carry-in-OP-01')).toBeTruthy()
    expect(screen.getByTestId('path-to-live-carry-in-OP-02')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Test 6+7: check fallback chain (D-10-16)
// ---------------------------------------------------------------------------

describe('PathToLiveTile — check source fallback chain (D-10-16)', () => {
  it('uses carryIns.live_readiness.checks as primary source', () => {
    // carryIns has checks, liveReadiness has different checks — carryIns wins
    const carryInChecks = [{ check: 'cap', status: 'FAIL', detail: 'from-carry-ins' }]
    const liveChecks = [{ check: 'cap', status: 'PASS', detail: 'from-live-readiness' }]

    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: makeCarryInsData({
        live_readiness: { schema_version: 1, overall: 'FAIL', evaluated_at: '', checks: carryInChecks },
      }),
    }))
    useLiveReadiness.mockReturnValue(makeLiveReadinessQuery({ data: { checks: liveChecks } }))

    render(<PathToLiveTile />)

    const row = screen.getByTestId('path-to-live-check-cap')
    // Should show detail from carryIns source, not liveReadiness
    expect(row.textContent).toContain('from-carry-ins')
    expect(row.textContent).not.toContain('from-live-readiness')
  })

  it('falls back to useLiveReadiness.data.checks when carryIns lacks live_readiness.checks', () => {
    // carryIns has no live_readiness block, fallback to liveReadiness
    const fallbackChecks = [{ check: 'cap', status: 'UNKNOWN', detail: 'fallback-source' }]

    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: {
        schema_version: 1,
        evaluated_at: '2026-05-18T00:00:00+00:00',
        overall: 'DO_NOT_FLIP',
        carry_ins: CARRY_INS_LIST,
        window: { first_all_pass_at: null, elapsed_seconds: 0, required_seconds: 86400, remaining_seconds: 86400 },
        preflight_summary: { pass: 0, fail: 0, unknown: 6 },
        // live_readiness absent — should trigger fallback
      },
    }))
    useLiveReadiness.mockReturnValue(makeLiveReadinessQuery({
      data: { checks: fallbackChecks },
    }))

    render(<PathToLiveTile />)

    const row = screen.getByTestId('path-to-live-check-cap')
    expect(row.textContent).toContain('fallback-source')
  })
})

// ---------------------------------------------------------------------------
// Test 8: ALMOST banner subtitle
// ---------------------------------------------------------------------------

describe('PathToLiveTile — ALMOST subtitle', () => {
  it('shows elapsed/required timing subtitle only when overall=ALMOST', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: makeCarryInsData({
        overall: 'ALMOST',
        window: {
          first_all_pass_at: '2026-05-18T00:00:00+00:00',
          elapsed_seconds: 3661,  // 1h 1m 1s
          required_seconds: 86400,
          remaining_seconds: 82739,
        },
      }),
    }))

    render(<PathToLiveTile />)

    const banner = screen.getByTestId('path-to-live-banner')
    // ALMOST uses bg-amber-600
    expect(banner.className).toContain('bg-amber-600')
    // Subtitle must contain formatted time
    expect(banner.textContent).toContain('01:01:01')
    expect(banner.textContent).toContain('All checks PASS')
  })

  it('does NOT show ALMOST subtitle when overall=DO_NOT_FLIP', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({
      data: makeCarryInsData({ overall: 'DO_NOT_FLIP' }),
    }))

    render(<PathToLiveTile />)

    const banner = screen.getByTestId('path-to-live-banner')
    expect(banner.textContent).not.toContain('All checks PASS')
  })
})

// ---------------------------------------------------------------------------
// Test 9: carry-in chip colors
// ---------------------------------------------------------------------------

describe('PathToLiveTile — carry-in chip colors', () => {
  it('open carry-in chip has amber classes', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({ data: makeCarryInsData() }))

    render(<PathToLiveTile />)

    const openRow = screen.getByTestId('path-to-live-carry-in-OP-01')
    // OP-01 is state=open → amber chip
    const chip = openRow.querySelector('span span, span')
    // Find the chip span (has bg-amber-600/30)
    const html = openRow.innerHTML
    expect(html).toContain('bg-amber-600/30')
    expect(html).toContain('text-amber-300')
  })

  it('closed carry-in chip has emerald classes', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({ data: makeCarryInsData() }))

    render(<PathToLiveTile />)

    const closedRow = screen.getByTestId('path-to-live-carry-in-OP-02')
    // OP-02 is state=closed → emerald chip
    const html = closedRow.innerHTML
    expect(html).toContain('bg-emerald-700/30')
    expect(html).toContain('text-emerald-300')
  })
})

// ---------------------------------------------------------------------------
// Test 10: error path via TileState
// ---------------------------------------------------------------------------

describe('PathToLiveTile — error path via TileState', () => {
  it('tile root renders but banner absent when carryIns query isError', () => {
    useCarryIns.mockReturnValue(makeCarryInsQuery({
      isError: true,
      isSuccess: false,
      error: { response: { status: 503, data: { detail: 'Service Unavailable' } } },
    }))

    render(<PathToLiveTile />)

    // Tile root always present (outside TileState)
    expect(screen.getByTestId('path-to-live-tile')).toBeTruthy()
    // Banner must NOT render (TileState renders error UI instead of children)
    expect(screen.queryByTestId('path-to-live-banner')).toBeNull()
  })
})
