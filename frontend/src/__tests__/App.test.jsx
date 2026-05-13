/**
 * App.test.jsx — viewport safety-border wrapper tests (Plan 06-04 Task 2).
 *
 * Behaviors covered:
 *   1. PAPER mode → root container has class `safety-border safety-border--paper`
 *   2. LIVE mode  → root container has class `safety-border safety-border--live`
 *   3. App still renders existing children (Header, main, footer) — no regression
 *
 * CSS rule shape (D-06; PATTERNS.md lines 224-228) — use `outline` not `border`
 * — is verified via a textual grep over the safety-border.css source file. No
 * layout shift introduced.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock useSafetyState before importing App.
vi.mock('../hooks/useSafetyState', () => ({
  useSafetyState: vi.fn(() => ({ data: undefined })),
}))

// The dashboard/page components touch many hooks that hit api endpoints.
// We stub the high-leaf pages so App renders without ferrying every
// downstream hook into the test sandbox. We only care about App's root
// container className.
vi.mock('../components/Dashboard', () => ({ default: () => <div data-testid="dashboard" /> }))
vi.mock('../pages/Phase1Dashboard', () => ({ default: () => <div /> }))
vi.mock('../pages/Phase3Dashboard', () => ({ default: () => <div /> }))
vi.mock('../pages/PerformanceDashboard', () => ({ default: () => <div /> }))
vi.mock('../pages/Portfolio', () => ({ default: () => <div /> }))
vi.mock('../pages/Settings', () => ({ default: () => <div /> }))
vi.mock('../components/CommandPalette', () => ({ default: () => <div /> }))
vi.mock('../components/KeyboardShortcuts', () => ({ default: () => <div /> }))
vi.mock('../components/StatusBar', () => ({ default: () => <div data-testid="status-bar" /> }))
vi.mock('../components/ThemeToggle', () => ({ default: () => <div /> }))
vi.mock('../contexts/ToastContext', () => ({
  ToastProvider: ({ children }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn(), removeToast: vi.fn() }),
}))

import App from '../App'
import { useSafetyState } from '../hooks/useSafetyState'

function withSafety(payload) {
  useSafetyState.mockReturnValue({ data: payload })
}

describe('App — viewport safety-border', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('applies safety-border--paper class when trading_mode=PAPER', () => {
    withSafety({ trading_mode: 'PAPER' })
    const { container } = render(<App />)
    const root = container.querySelector('.safety-border')
    expect(root).not.toBeNull()
    expect(root.className).toContain('safety-border--paper')
    expect(root.className).not.toContain('safety-border--live')
  })

  it('applies safety-border--live class when trading_mode=LIVE', () => {
    withSafety({ trading_mode: 'LIVE' })
    const { container } = render(<App />)
    const root = container.querySelector('.safety-border')
    expect(root).not.toBeNull()
    expect(root.className).toContain('safety-border--live')
    expect(root.className).not.toContain('safety-border--paper')
  })

  it('falls back to safety-border--paper when safety-state is undefined', () => {
    withSafety(undefined)
    const { container } = render(<App />)
    const root = container.querySelector('.safety-border')
    expect(root).not.toBeNull()
    expect(root.className).toContain('safety-border--paper')
  })

  it('still renders existing Dashboard + StatusBar children (no regression)', () => {
    withSafety({ trading_mode: 'PAPER' })
    render(<App />)
    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('status-bar')).toBeInTheDocument()
  })

  it('uses CSS `outline` not `border` in safety-border.css (no layout shift)', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const cssPath = path.resolve(here, '..', 'styles', 'safety-border.css')
    const src = fs.readFileSync(cssPath, 'utf8')

    expect(src).toMatch(/\.safety-border\s*\{/)
    expect(src).toMatch(/\.safety-border--paper/)
    expect(src).toMatch(/\.safety-border--live/)
    expect(src).toMatch(/outline:\s*1px/)
    // Active `border:` declarations are forbidden — only `outline` should
    // appear in declaration position. Strip comments first, then assert.
    const noComments = src.replace(/\/\*[\s\S]*?\*\//g, '')
    expect(noComments).not.toMatch(/^\s*border:/m)
  })
})
