/**
 * StatusBar.test.jsx — tests for the three new safety cells + emergency mtime
 * rendering, per Plan 06-04 Task 1 behaviors 3-6.
 *
 * Behaviors covered:
 *   3. PAPER trading_mode → MODE cell shows "PAPER" with gain (#5eead4) color
 *   4. LIVE trading_mode → MODE cell shows "LIVE" with loss (#fb7185) color
 *   5. kill_switch.tripped=true → KILL-SWITCH cell shows "TRIPPED" with loss color
 *   6. ml_predictions_enabled=true → ML cell shows "ON" with gold (#d4af6a) color
 *   7. emergency_stop.{active:true, mtime:ISO} → EMERGENCY cell shows "ACTIVE — since HH:MM:SS"
 *   8. emergency_stop.{active:false, mtime:null} → EMERGENCY cell shows "INACTIVE"
 *
 * NOTE on the "existing emergency_stop cell" plan language: at the time of
 * writing there was no pre-existing EMERGENCY cell in StatusBar.jsx (only the
 * leftmost state pill flipping color on emergency). Per advisor (Wave 2
 * advisor call), the cleanest implementation is a NEW dedicated EMERGENCY
 * cell rendered after the three D-05 cells — keeps the state pill semantics
 * intact and gives D-07 (Active/Inactive + mtime) a dedicated affordance.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock all 4 hooks consumed by StatusBar.
vi.mock('../../hooks/usePositions', () => ({
  useTradingStatus: vi.fn(() => ({ data: { status: { is_running: false } } })),
  usePositions: vi.fn(() => ({ data: { positions: [] } })),
}))
vi.mock('../../hooks/usePortfolio', () => ({
  usePortfolio: vi.fn(() => ({ data: { portfolio: { cash_balance: 0, total_pnl: 0 } } })),
}))
vi.mock('../../hooks/useSafetyState', () => ({
  useSafetyState: vi.fn(() => ({ data: undefined })),
}))

import StatusBar from '../StatusBar'
import { useSafetyState } from '../../hooks/useSafetyState'

function withSafety(payload) {
  useSafetyState.mockReturnValue({ data: payload })
}

const BASE_SAFETY = {
  trading_mode: 'PAPER',
  paper_trading_mode: true,
  auto_trading_enabled: true,
  emergency_stop: { active: false, mtime: null },
  ml_predictions_enabled: false,
  kill_switch: { daily_loss_armed: true, daily_pnl_pct: 0.0, tripped: false },
  last_updated_at: '2026-05-13T21:07:38.440181+00:00',
}

describe('StatusBar — safety cells', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders MODE cell with PAPER value and gain (#5eead4) color when trading_mode=PAPER', () => {
    withSafety({ ...BASE_SAFETY, trading_mode: 'PAPER' })
    render(<StatusBar />)
    const value = screen.getByText('PAPER')
    expect(value).toBeInTheDocument()
    // eyebrow label is present
    expect(screen.getByText('MODE')).toBeInTheDocument()
    // gain color (mint)
    expect(value.getAttribute('style') || '').toMatch(/#5eead4/i)
  })

  it('renders MODE cell with LIVE value and loss (#fb7185) color when trading_mode=LIVE', () => {
    withSafety({ ...BASE_SAFETY, trading_mode: 'LIVE' })
    render(<StatusBar />)
    const value = screen.getByText('LIVE')
    expect(value).toBeInTheDocument()
    expect(value.getAttribute('style') || '').toMatch(/#fb7185/i)
  })

  it('renders KILL-SWITCH cell with TRIPPED + loss color when kill_switch.tripped=true', () => {
    withSafety({
      ...BASE_SAFETY,
      kill_switch: { daily_loss_armed: true, daily_pnl_pct: -5.1, tripped: true },
    })
    render(<StatusBar />)
    expect(screen.getByText('KILL-SWITCH')).toBeInTheDocument()
    const value = screen.getByText('TRIPPED')
    expect(value).toBeInTheDocument()
    expect(value.getAttribute('style') || '').toMatch(/#fb7185/i)
  })

  it('renders KILL-SWITCH cell with ARMED + neutral (#a09e98) color when tripped=false', () => {
    withSafety(BASE_SAFETY)
    render(<StatusBar />)
    const value = screen.getByText('ARMED')
    expect(value).toBeInTheDocument()
    expect(value.getAttribute('style') || '').toMatch(/#a09e98/i)
  })

  it('renders ML cell with ON + gold (#d4af6a) color when ml_predictions_enabled=true', () => {
    withSafety({ ...BASE_SAFETY, ml_predictions_enabled: true })
    render(<StatusBar />)
    expect(screen.getByText('ML')).toBeInTheDocument()
    const value = screen.getByText('ON')
    expect(value).toBeInTheDocument()
    expect(value.getAttribute('style') || '').toMatch(/#d4af6a/i)
  })

  it('renders ML cell with OFF + muted (#65645e) color when ml_predictions_enabled=false', () => {
    withSafety(BASE_SAFETY)
    render(<StatusBar />)
    const value = screen.getByText('OFF')
    expect(value).toBeInTheDocument()
    expect(value.getAttribute('style') || '').toMatch(/#65645e/i)
  })

  it('renders EMERGENCY cell as "ACTIVE — since HH:MM:SS" when emergency_stop.active=true with mtime', () => {
    withSafety({
      ...BASE_SAFETY,
      emergency_stop: { active: true, mtime: '2026-05-13T12:43:01Z' },
    })
    render(<StatusBar />)
    expect(screen.getByText('EMERGENCY')).toBeInTheDocument()
    // The HH:MM:SS portion of 2026-05-13T12:43:01Z — local-time-formatted via
    // toLocaleTimeString('en-GB', {hour12:false, timeZone:'UTC'}) → "12:43:01"
    expect(screen.getByText(/ACTIVE\s+—\s+since\s+12:43:01/)).toBeInTheDocument()
  })

  it('renders EMERGENCY cell as INACTIVE when emergency_stop.active=false', () => {
    withSafety(BASE_SAFETY)
    render(<StatusBar />)
    expect(screen.getByText('INACTIVE')).toBeInTheDocument()
  })

  it('falls back to PAPER defaults when useSafetyState returns no data', () => {
    // hook not configured → data is undefined
    useSafetyState.mockReturnValue({ data: undefined })
    render(<StatusBar />)
    expect(screen.getByText('PAPER')).toBeInTheDocument()
    expect(screen.getByText('ARMED')).toBeInTheDocument()
    expect(screen.getByText('OFF')).toBeInTheDocument()
    expect(screen.getByText('INACTIVE')).toBeInTheDocument()
  })
})
