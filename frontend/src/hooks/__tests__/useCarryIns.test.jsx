/**
 * useCarryIns.test.jsx — behavioral tests for the carry-ins polling hook.
 *
 * Gap coverage (DASHLIVE-01/03, task 10-02-01):
 *   1. Hook calls api.get('/preflight/carry-ins') and exposes result via data
 *   2. queryKey is ['preflight-carry-ins']
 *   3. Hook configured with refetchInterval 5000, staleTime 5000, retry 2, retryDelay 1000
 *      (cadence parity with useSafetyState per D-10-15)
 *   4. JSDoc documents D-10-16 authority: useCarryIns is authoritative for overall + window
 *
 * Adversarial stance: hook must actually call the right path and surface data.
 * A hook that calls the wrong path will fail test 1. A hook that silently
 * drops cadence config will fail test 3.
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
import { useCarryIns } from '../useCarryIns'

/** Minimal valid carry-ins payload (D-10-04 shape). */
const CARRY_INS_PAYLOAD = {
  schema_version: 1,
  evaluated_at: '2026-05-18T00:00:00+00:00',
  overall: 'DO_NOT_FLIP',
  carry_ins: [
    { id: 'OP-01', state: 'open', description: 'Risk cap restored to ≤2%' },
    { id: 'OP-02', state: 'closed', description: 'Paper-trading confirmed' },
  ],
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
    checks: [],
  },
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

describe('useCarryIns', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('calls api.get("/preflight/carry-ins") and exposes the full payload via data', async () => {
    api.get.mockResolvedValueOnce(CARRY_INS_PAYLOAD)

    const { result } = renderHook(() => useCarryIns(), {
      wrapper: makeWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(api.get).toHaveBeenCalledWith('/preflight/carry-ins')
    expect(result.current.data).toEqual(CARRY_INS_PAYLOAD)
  })

  it('uses queryKey ["preflight-carry-ins"]', async () => {
    // Source-text check: queryKey literal must match exactly so cache invalidation works.
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const hookPath = path.resolve(here, '..', 'useCarryIns.js')
    const src = fs.readFileSync(hookPath, 'utf8')

    expect(src).toMatch(/queryKey:\s*\[\s*['"]preflight-carry-ins['"]\s*\]/)
  })

  it('is configured with refetchInterval 5000, staleTime 5000, retry 2, retryDelay 1000 (D-10-15 cadence parity)', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const hookPath = path.resolve(here, '..', 'useCarryIns.js')
    const src = fs.readFileSync(hookPath, 'utf8')

    expect(src).toMatch(/refetchInterval:\s*5000/)
    expect(src).toMatch(/staleTime:\s*5000/)
    expect(src).toMatch(/retry:\s*2/)
    expect(src).toMatch(/retryDelay:\s*1000/)
  })

  it('documents D-10-16 authority — useCarryIns is AUTHORITATIVE for overall + window', async () => {
    // D-10-16 is load-bearing: JSDoc must state the authority rule.
    // A future refactor that silently changes authority without updating docs
    // would indicate a violation or an undocumented behavioral change.
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const hookPath = path.resolve(here, '..', 'useCarryIns.js')
    const src = fs.readFileSync(hookPath, 'utf8')

    expect(src).toMatch(/D-10-16/)
    expect(src).toMatch(/AUTHORITATIVE/i)
  })
})
