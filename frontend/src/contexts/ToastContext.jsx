import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

/**
 * ToastContext — Editorial Trading Floor toast surface.
 *
 * Emits ephemeral feedback in a corner stack. All toasts share a single
 * `aria-live="polite"` region so screen readers announce updates without
 * trapping focus. Three intents: info (viridian), warn (gold), error
 * (warm rose).
 *
 * Usage:
 *   const { toast } = useToast()
 *   toast('Auto-trader started')
 *   toast.error('Start failed: …')
 *   toast.warn('Daily loss approaching cap')
 *
 * Components without provider access can also dispatch a `toast` event:
 *   window.dispatchEvent(new CustomEvent('toast', { detail: { message: 'x', intent: 'info' } }))
 */

const ToastContext = createContext(null)

const C = {
  bg: '#121215',
  border: '#2a2a32',
  borderInfo: 'rgba(94, 234, 212, 0.45)',
  borderWarn: 'rgba(212, 175, 106, 0.5)',
  borderError: 'rgba(251, 113, 133, 0.5)',
  textInfo: '#5eead4',
  textWarn: '#d4af6a',
  textError: '#fb7185',
  text: '#f5f3ee',
  text2: '#a09e98',
}

const accentFor = (intent) => {
  if (intent === 'error') return { border: C.borderError, accent: C.textError }
  if (intent === 'warn') return { border: C.borderWarn, accent: C.textWarn }
  return { border: C.borderInfo, accent: C.textInfo }
}

let nextId = 1

export function ToastProvider({ children, max = 4, defaultTtlMs = 4500 }) {
  const [toasts, setToasts] = useState([])
  const timeoutsRef = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
    const t = timeoutsRef.current.get(id)
    if (t) {
      clearTimeout(t)
      timeoutsRef.current.delete(id)
    }
  }, [])

  const push = useCallback(
    (message, opts = {}) => {
      if (!message) return
      const id = nextId++
      const intent = opts.intent || 'info'
      const ttl = opts.ttl != null ? opts.ttl : defaultTtlMs
      setToasts((list) => {
        const next = [...list, { id, message, intent }]
        return next.length > max ? next.slice(next.length - max) : next
      })
      if (ttl > 0) {
        const handle = setTimeout(() => dismiss(id), ttl)
        timeoutsRef.current.set(id, handle)
      }
      return id
    },
    [defaultTtlMs, dismiss, max]
  )

  // toast() callable + intent shortcuts
  const toast = useCallback((message, opts) => push(message, opts), [push])
  toast.info = useCallback((m, o = {}) => push(m, { ...o, intent: 'info' }), [push])
  toast.warn = useCallback((m, o = {}) => push(m, { ...o, intent: 'warn' }), [push])
  toast.error = useCallback((m, o = {}) => push(m, { ...o, intent: 'error' }), [push])

  // Window-level event bridge for callers without provider access
  useEffect(() => {
    const handler = (e) => {
      if (!e?.detail) return
      const { message, intent, ttl } = e.detail
      push(message, { intent, ttl })
    }
    window.addEventListener('toast', handler)
    return () => window.removeEventListener('toast', handler)
  }, [push])

  const value = { toast, dismiss }

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* Live region — announces every toast text to assistive tech */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-12 right-4 z-[90] pointer-events-none flex flex-col gap-2 max-w-sm"
        style={{ fontFamily: 'Manrope, system-ui, sans-serif' }}
      >
        {toasts.map((t) => {
          const tone = accentFor(t.intent)
          return (
            <div
              key={t.id}
              className="pointer-events-auto px-4 py-3 rounded-md shadow-2xl backdrop-blur"
              style={{
                background: `${C.bg}f5`,
                border: `1px solid ${tone.border}`,
                color: C.text,
                animation: 'toast-rise 240ms cubic-bezier(0.2, 0.8, 0.2, 1) both',
              }}
            >
              <div className="flex items-start gap-3">
                <span
                  aria-hidden="true"
                  className="flex-shrink-0 inline-block rounded-full mt-1.5"
                  style={{
                    width: 6,
                    height: 6,
                    background: tone.accent,
                    boxShadow: `0 0 8px ${tone.accent}80`,
                  }}
                />
                <div className="flex-1 text-sm leading-snug">{t.message}</div>
                <button
                  type="button"
                  onClick={() => dismiss(t.id)}
                  className="text-[10px] uppercase tracking-widest"
                  style={{ color: C.text2, fontFamily: 'JetBrains Mono, monospace' }}
                  aria-label="Dismiss notification"
                >
                  ✕
                </button>
              </div>
            </div>
          )
        })}
      </div>
      <style>{`
        @keyframes toast-rise {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // Non-provider fallback — fire window event so something still records it
    const fallback = (message, opts = {}) =>
      window.dispatchEvent(new CustomEvent('toast', { detail: { message, ...opts } }))
    fallback.info = (m, o = {}) => fallback(m, { ...o, intent: 'info' })
    fallback.warn = (m, o = {}) => fallback(m, { ...o, intent: 'warn' })
    fallback.error = (m, o = {}) => fallback(m, { ...o, intent: 'error' })
    return { toast: fallback, dismiss: () => {} }
  }
  return ctx
}
