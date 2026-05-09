import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../contexts/ToastContext'

/**
 * CommandPalette — Cmd/Ctrl+K driven action surface.
 *
 * Editorial Trading Floor aesthetic: Fraunces serif display, JetBrains Mono
 * for symbol tickers, warm off-black backdrop with viridian-teal accent.
 *
 * Sections:
 *   1. Symbols  — switch focused chart symbol (dispatches a CustomEvent
 *      'cp:select-symbol' so the dashboard can react without prop drilling)
 *   2. Actions  — start / stop trader, emergency stop, refresh
 *   3. Routes   — jump between pages
 *
 * Open with Cmd-K (mac) or Ctrl-K (win/linux). Esc to close. Enter to
 * fire selected. Arrow keys to navigate. / focuses the input from any
 * non-input element.
 */

const SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT',
  'AVAXUSDT', 'LINKUSDT', 'DOTUSDT', 'MATICUSDT', 'ARBUSDT', 'OPUSDT',
]

const ROUTES = [
  { path: '/', label: 'Main Dashboard', hint: 'g d' },
  { path: '/portfolio', label: 'Portfolio', hint: 'g o' },
  { path: '/performance', label: 'Performance Analytics', hint: 'g p' },
  { path: '/phase1', label: 'Phase 1 Monitoring', hint: 'g 1' },
  { path: '/phase3', label: 'Phase 3 AI Enhanced', hint: 'g 3' },
  { path: '/settings', label: 'Settings', hint: 'g s' },
]

const fuzzy = (item, query) => {
  if (!query) return true
  const q = query.toLowerCase()
  const haystack = (item.symbol || item.label || '').toLowerCase()
  let qi = 0
  for (const c of haystack) if (c === q[qi]) qi++
  return qi === q.length
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const [busy, setBusy] = useState(null)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const { toast } = useToast()

  // Build flat command list with section headers
  const items = useMemo(() => {
    const symMatches = SYMBOLS
      .filter((s) => fuzzy({ symbol: s }, query))
      .map((s) => ({
        kind: 'symbol',
        id: `sym-${s}`,
        symbol: s,
        label: s,
        group: 'Symbols',
        run: () => {
          window.dispatchEvent(new CustomEvent('cp:select-symbol', { detail: s }))
          toast(`Focused ${s}`, { ttl: 1800 })
        },
      }))

    const actions = [
      {
        kind: 'action',
        id: 'act-start',
        label: 'Start auto-trader',
        group: 'Actions',
        async run() {
          setBusy('start')
          try {
            await api.post('/api/trading/start')
            toast('Auto-trader started')
          } catch (e) {
            toast.error(`Start failed: ${e?.response?.data?.detail || e.message}`)
          } finally {
            setBusy(null)
          }
        },
      },
      {
        kind: 'action',
        id: 'act-stop',
        label: 'Stop auto-trader',
        group: 'Actions',
        async run() {
          setBusy('stop')
          try {
            await api.post('/api/trading/stop')
            toast('Auto-trader stopped')
          } catch (e) {
            toast.error(`Stop failed: ${e?.response?.data?.detail || e.message}`)
          } finally {
            setBusy(null)
          }
        },
      },
      {
        kind: 'action',
        id: 'act-emergency',
        label: 'Emergency stop (halt all trading)',
        group: 'Actions',
        destructive: true,
        async run() {
          if (!confirm('Activate emergency stop? Halts auto-trader; positions remain open for review.')) return
          setBusy('emergency')
          try {
            await api.post('/api/portfolio/emergency-stop', { reason: 'command-palette' })
            toast.warn('Emergency stop activated')
          } catch (e) {
            toast.error(`Emergency stop failed: ${e?.response?.data?.detail || e.message}`)
          } finally {
            setBusy(null)
          }
        },
      },
      {
        kind: 'action',
        id: 'act-reload',
        label: 'Reload dashboard data',
        group: 'Actions',
        run: () => window.dispatchEvent(new CustomEvent('cp:reload')),
      },
    ].filter((a) => fuzzy(a, query))

    const routeMatches = ROUTES
      .filter((r) => fuzzy(r, query))
      .map((r) => ({
        kind: 'route',
        id: `route-${r.path}`,
        label: r.label,
        hint: r.hint,
        group: 'Go to',
        run: () => navigate(r.path),
      }))

    return [...symMatches, ...actions, ...routeMatches]
  }, [query, navigate])

  // Reset active when items change
  useEffect(() => { setActiveIdx(0) }, [query, open])

  // Keyboard: open / close / focus
  useEffect(() => {
    const onKey = (e) => {
      const isMod = e.metaKey || e.ctrlKey
      if (isMod && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
        return
      }
      if (e.key === 'Escape' && open) {
        e.preventDefault()
        setOpen(false)
      }
      // `/` opens the palette from anywhere outside an input
      if (
        e.key === '/' &&
        !open &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        e.preventDefault()
        setOpen(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  // Auto-focus input when opening
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 10)
      return () => clearTimeout(t)
    } else {
      setQuery('')
    }
  }, [open])

  const fire = useCallback(
    async (item) => {
      if (!item) return
      try { await item.run() } finally { setOpen(false) }
    },
    []
  )

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      fire(items[activeIdx])
    }
  }

  if (!open) {
    return (
      <>
        {/* Tiny launcher hint, only after first session */}
        <button
          type="button"
          aria-label="Open command palette"
          onClick={() => setOpen(true)}
          className="fixed bottom-12 right-4 z-40 hidden sm:flex items-center gap-2 px-3 py-2 rounded-full bg-slate-900/80 border border-slate-700/80 text-slate-300 text-xs backdrop-blur hover:border-teal-500/60 hover:text-teal-300 transition-colors shadow-lg"
        >
          <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>⌘K</span>
          <span className="text-[10px] uppercase tracking-widest">Command</span>
        </button>
      </>
    )
  }

  // Group items by section for rendering
  const grouped = items.reduce((acc, it, idx) => {
    const g = it.group
    if (!acc[g]) acc[g] = []
    acc[g].push({ ...it, _flatIdx: idx })
    return acc
  }, {})

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh] px-4"
      onClick={(e) => e.target === e.currentTarget && setOpen(false)}
    >
      {/* Backdrop with grain */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        style={{
          backgroundImage:
            'radial-gradient(circle at 20% 30%, rgba(94,234,212,0.05) 0%, transparent 40%), radial-gradient(circle at 80% 70%, rgba(212,175,106,0.04) 0%, transparent 38%)',
        }}
      />

      <div
        className="relative w-full max-w-2xl rounded-md overflow-hidden shadow-2xl"
        style={{
          background: '#121215',
          border: '1px solid #2a2a32',
          fontFamily: 'Manrope, system-ui, sans-serif',
        }}
      >
        {/* Header / search */}
        <div className="flex items-center gap-3 px-5 py-4 border-b" style={{ borderColor: '#2a2a32' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5eead4" strokeWidth="1.5" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3-3" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search symbols, actions, pages…"
            className="flex-1 bg-transparent outline-none text-base"
            style={{ color: '#f5f3ee', caretColor: '#5eead4' }}
            aria-label="Command palette query"
          />
          <kbd
            className="hidden sm:inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium"
            style={{ background: '#1f1f24', color: '#a09e98', fontFamily: 'JetBrains Mono, monospace' }}
          >
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[60vh] overflow-y-auto py-2">
          {items.length === 0 ? (
            <div className="px-5 py-8 text-center" style={{ color: '#a09e98' }}>
              <div
                className="text-xl mb-1"
                style={{ fontFamily: 'Fraunces, serif', fontVariationSettings: '"opsz" 144', fontStyle: 'italic' }}
              >
                Nothing matches.
              </div>
              <div className="text-xs uppercase tracking-widest" style={{ color: '#65645e' }}>
                Try a symbol like <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>btc</span>
              </div>
            </div>
          ) : (
            Object.entries(grouped).map(([group, gitems]) => (
              <div key={group} className="mb-1 last:mb-0">
                <div
                  className="px-5 pt-3 pb-1 text-[10px] uppercase tracking-[0.2em]"
                  style={{ color: '#65645e', fontWeight: 600 }}
                >
                  {group}
                </div>
                {gitems.map((it) => {
                  const active = it._flatIdx === activeIdx
                  return (
                    <button
                      key={it.id}
                      type="button"
                      onMouseEnter={() => setActiveIdx(it._flatIdx)}
                      onClick={() => fire(it)}
                      disabled={busy !== null}
                      className="w-full flex items-center justify-between px-5 py-2.5 text-left transition-colors"
                      style={{
                        background: active ? 'rgba(94, 234, 212, 0.08)' : 'transparent',
                        color: active ? '#f5f3ee' : '#a09e98',
                        borderLeft: active ? '2px solid #5eead4' : '2px solid transparent',
                      }}
                    >
                      <span className="flex items-center gap-3">
                        {it.kind === 'symbol' ? (
                          <span style={{ fontFamily: 'JetBrains Mono, monospace', color: active ? '#5eead4' : '#a09e98', fontSize: 13 }}>
                            {it.symbol}
                          </span>
                        ) : (
                          <span className="text-sm" style={{ color: it.destructive ? '#fb7185' : 'inherit' }}>
                            {it.label}
                          </span>
                        )}
                        {busy && it.id.startsWith(`act-${busy}`) && (
                          <span className="text-[10px] uppercase tracking-widest" style={{ color: '#5eead4' }}>
                            …running
                          </span>
                        )}
                      </span>
                      {it.hint && (
                        <span
                          className="text-[10px] uppercase tracking-widest"
                          style={{ color: '#65645e', fontFamily: 'JetBrains Mono, monospace' }}
                        >
                          {it.hint}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between px-5 py-2 text-[10px] uppercase tracking-widest border-t"
          style={{ background: '#0a0a0b', borderColor: '#2a2a32', color: '#65645e' }}
        >
          <span style={{ fontFamily: 'Fraunces, serif', fontStyle: 'italic', textTransform: 'none', fontSize: 12, letterSpacing: 0 }}>
            Editorial Command — open with ⌘K
          </span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>↑↓ navigate · ↵ run</span>
        </div>
      </div>
    </div>
  )
}
