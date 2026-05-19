/**
 * useLiveReadiness.test.jsx — behavioral tests for the live-readiness polling hook.
 *
 * Gap coverage (DASHLIVE-01/03, task 10-02-01):
 *   1. Hook calls api.get('/preflight/live-readiness') and exposes result via data
 *   2. queryKey is ['preflight-live-readiness']
 *   3. Hook configured with refetchInterval 5000, staleTime 5000, retry 2, retryDelay 1000
 *      (cadence parity with useSafetyState per D-10-15)
 *
 * Adversarial stance: hook must call the correct distinct path from useCarryIns.
 * A hook accidentally calling '/preflight/carry-ins' would fail test 1.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock BEFORE import — vitest hoists vi.mock
vi.mock('../../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}))

import api from '../../services/api'
import { useLiveReadiness } from '../useLiveReadiness'

/** Minimal valid live-readiness payload. */
const LIVE_READINESS_PAYLOAD = {
  schema_version: 1,
  overall: 'PASS',
  evaluated_at: '2026-05-18T00:00:00+00:00',
  checks: [
    { check: 'cap', status: 'PASS', detail: 'cap ≤ 2%' },
    { check: 'paper_mode', status: 'PASS', detail: 'paper' },
    { check: 'trading_mode', status: 'PASS', detail: 'paper' },
    { check: 'ack', status: 'PASS', detail: 'ACK present' },
    { check: 'emergency_stop', status: 'PASS', detail: 'not active' },
    { check: 'dsr_evidence', status: 'PASS', detail: 'dsr=0.96' },
  ],
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

describe('useLiveReadiness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('calls api.get("/preflight/live-readiness") and exposes payload via data', async () => {
    api.get.mockResolvedValueOnce(LIVE_READINESS_PAYLOAD)

    const { result } = renderHook(() => useLiveReadiness(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(api.get).toHaveBeenCalledWith('/preflight/live-readiness')
    expect(result.current.data).toEqual(LIVE_READINESS_PAYLOAD)
  })

  it('uses distinct queryKey ["preflight-live-readiness"] (not carry-ins key)', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const hookPath = path.resolve(here, '..', 'useLiveReadiness.js')
    const src = fs.readFileSync(hookPath, 'utf8')

    expect(src).toMatch(/queryKey:\s*\[\s*['"]preflight-live-readiness['"]\s*\]/)
    // Must NOT share the carry-ins queryKey
    expect(src).not.toMatch(/queryKey:\s*\[\s*['"]preflight-carry-ins['"]\s*\]/)
  })

  it('is configured with refetchInterval 5000, staleTime 5000, retry 2, retryDelay 1000 (D-10-15 cadence parity)', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const hookPath = path.resolve(here, '..', 'useLiveReadiness.js')
    const src = fs.readFileSync(hookPath, 'utf8')

    expect(src).toMatch(/refetchInterval:\s*5000/)
    expect(src).toMatch(/staleTime:\s*5000/)
    expect(src).toMatch(/retry:\s*2/)
    expect(src).toMatch(/retryDelay:\s*1000/)
  })
})
