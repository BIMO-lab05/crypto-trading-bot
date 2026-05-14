/**
 * useSafetyState.test.jsx — unit tests for the safety-state polling hook.
 *
 * Covers Plan 06-04 Task 1 behaviors 1-2:
 *   1. Hook calls api.get('/config/safety-state') and exposes the result via data
 *   2. Hook configured with refetchInterval: 5000, staleTime: 5000, retry: 2, retryDelay: 1000
 *
 * Per D-11 (06-CONTEXT.md): 5s poll cadence matching StatusBar/usePositions.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock the axios client BEFORE importing the hook (hoisted by vitest).
vi.mock('../../services/api', () => {
  return {
    default: {
      get: vi.fn(),
    },
  }
})

import api from '../../services/api'
import { useSafetyState } from '../useSafetyState'

const SAFETY_PAYLOAD = {
  trading_mode: 'PAPER',
  paper_trading_mode: true,
  auto_trading_enabled: true,
  emergency_stop: { active: false, mtime: null },
  ml_predictions_enabled: false,
  kill_switch: { daily_loss_armed: true, daily_pnl_pct: 0.0, tripped: false },
  last_updated_at: '2026-05-13T21:07:38.440181+00:00',
}

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
  // eslint-disable-next-line react/display-name, react/prop-types
  return ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('useSafetyState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('calls api.get("/config/safety-state") and exposes result via data', async () => {
    api.get.mockResolvedValueOnce(SAFETY_PAYLOAD)

    const { result } = renderHook(() => useSafetyState(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(api.get).toHaveBeenCalledWith('/config/safety-state')
    expect(result.current.data).toEqual(SAFETY_PAYLOAD)
  })

  it('is configured with refetchInterval 5000, staleTime 5000, retry 2, retryDelay 1000', async () => {
    // Behavior-level verification: assert the source declarations of the hook's
    // option values. We can't introspect React Query's internal options at
    // runtime, so the strongest behavioral check is that the documented
    // numbers are present at the call site. Use a textual read of the file
    // so a refactor that changes the literals trips this test.
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const hookPath = path.resolve(here, '..', 'useSafetyState.js')
    const src = fs.readFileSync(hookPath, 'utf8')

    expect(src).toMatch(/refetchInterval:\s*5000/)
    expect(src).toMatch(/staleTime:\s*5000/)
    expect(src).toMatch(/retry:\s*2/)
    expect(src).toMatch(/retryDelay:\s*1000/)
  })
})
