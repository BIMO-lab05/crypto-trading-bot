import React from 'react'

/**
 * TileState — shared wrapper for every audited dashboard tile (Plan 06-05,
 * DASH-05). Consumes a React-Query result object + optional `lastUpdatedAt`
 * and routes the render between five branches.
 *
 * State machine precedence (F-05 — D-13 intent: "errors are LOUD"):
 *   1. query.isError                                  → Failed (...) + Retry
 *   2. query.isLoading && !query.data                 → skeleton
 *   3. query.isSuccess && isEmpty(query.data)         → "No data yet"
 *   4. (forceStale || isStale(...)) && success-non-empty → children + stale badge
 *   5. otherwise                                       → children
 *
 * `forceStale` ONLY toggles between branches 4 and 5; it does NOT bypass
 * branches 1-3. A LABELED_STALE tile that hits a real error still shows the
 * Failed (...) UI — a stale-overlay can NEVER silence a real error.
 *
 * Editorial palette tokens are inlined here (no shared tokens module — out
 * of scope per 06-PATTERNS.md line 612).
 *
 * Decisions referenced:
 *   - D-12  shared wrapper for every audited tile body
 *   - D-13  empty + error UX text + precedence
 *   - D-14  error rendering shape: "Failed (<code>): <msg>. [Retry]"
 *           NEVER renders the raw axios message field (security: may contain
 *           stack-trace fragments); fallback is detail → statusText → "request failed"
 *   - D-15  per-tile staleness thresholds (STALE_THRESHOLDS_MS)
 *   - F-05  precedence clarification — errors are loud, never silenced
 */

// Editorial palette tokens lifted from performance-theme.css. Inlined for
// components outside .perf-page where the CSS variables aren't in scope.
const C = {
  bg: '#0a0a0b',
  surface: '#18181c',
  surface2: '#1f1f24',
  border: '#2a2a32',
  borderStrong: '#3a3a44',
  text: '#f5f3ee',
  text2: '#a09e98',
  text3: '#8a8982',
  gain: '#5eead4',
  loss: '#fb7185',
  gold: '#d4af6a',
}

// Per-tile staleness thresholds (D-15). Callers pass `thresholdKey` OR an
// explicit `staleAfterMs`. If neither, defaults to 60s.
export const STALE_THRESHOLDS_MS = {
  ticker: 60_000,
  signals: 30_000,
  performance: 5 * 60_000,
  portfolio: 30_000,
  positions: 30_000,
  default: 60_000,
}

// Default isEmpty predicate: null/undefined or empty array.
const defaultIsEmpty = (d) => d == null || (Array.isArray(d) && d.length === 0)

/**
 * Determine whether `lastUpdatedAt` is older than `staleAfterMs`. Returns
 * false on missing/invalid timestamps (caller controls forced-stale via
 * `forceStale` prop).
 */
function isStaleByTimestamp(lastUpdatedAt, staleAfterMs) {
  if (lastUpdatedAt == null || !Number.isFinite(staleAfterMs)) return false
  const t = typeof lastUpdatedAt === 'number'
    ? lastUpdatedAt
    : Date.parse(lastUpdatedAt)
  if (!Number.isFinite(t)) return false
  return Date.now() - t > staleAfterMs
}

// Stale corner badge — small text-only marker positioned absolute top-right
// of the parent container (caller container must have position: relative).
function StaleBadge() {
  return (
    <span
      aria-label="stale"
      style={{
        position: 'absolute',
        top: 6,
        right: 8,
        zIndex: 1,
        fontFamily: 'Manrope, system-ui, sans-serif',
        fontSize: 9,
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color: C.text3,
        background: C.surface2,
        border: `1px solid ${C.border}`,
        borderRadius: 2,
        padding: '1px 5px',
      }}
    >
      stale
    </span>
  )
}

// Skeleton (loading) — two muted bars on surface2. Pattern lifted from
// KeyMetricsStrip.jsx:105-110.
function Skeleton() {
  return (
    <div className="space-y-1.5 animate-pulse" style={{ padding: 12 }}>
      <div className="h-7 rounded" style={{ background: C.surface2, width: '60%' }} />
      <div className="h-3 rounded" style={{ background: C.surface2, width: '40%' }} />
    </div>
  )
}

// "No data yet" — empty-success affordance per D-13.
function EmptyState({ title }) {
  return (
    <div
      style={{
        padding: 16,
        color: C.text3,
        fontFamily: 'Manrope, system-ui, sans-serif',
        fontSize: 12,
        letterSpacing: '0.04em',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          color: C.text3,
          fontSize: 10,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          fontWeight: 600,
          marginBottom: 6,
        }}
      >
        {title}
      </div>
      <div>No data yet</div>
    </div>
  )
}

// Failed (...) — error affordance per D-14. The fallback chain for the
// human-readable message is: response.data.detail → response.statusText →
// "request failed". NEVER the raw axios `.message` field (security: may
// contain stack-trace fragments depending on axios config).
function ErrorState({ title, error, onRetry }) {
  const status = error?.response?.status
  const code = status != null ? String(status) : 'network'
  const detail = error?.response?.data?.detail
  const statusText = error?.response?.statusText
  const message =
    (typeof detail === 'string' && detail) ||
    (typeof statusText === 'string' && statusText) ||
    'request failed'
  return (
    <div
      style={{
        padding: 16,
        fontFamily: 'Manrope, system-ui, sans-serif',
        fontSize: 12,
      }}
    >
      <div
        style={{
          color: C.text3,
          fontSize: 10,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          fontWeight: 600,
          marginBottom: 6,
        }}
      >
        {title}
      </div>
      <div style={{ color: C.loss, marginBottom: 8 }}>
        Failed ({code}): {message}
      </div>
      <button
        type="button"
        onClick={() => {
          if (typeof onRetry === 'function') onRetry()
        }}
        style={{
          fontFamily: 'Manrope, system-ui, sans-serif',
          fontSize: 11,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: C.text,
          background: C.surface,
          border: `1px solid ${C.borderStrong}`,
          borderRadius: 2,
          padding: '4px 12px',
          cursor: 'pointer',
        }}
      >
        Retry
      </button>
    </div>
  )
}

/**
 * TileState — props:
 *   query          React Query result {isLoading,isError,isSuccess,error,data,refetch}
 *   isEmpty        (data) => boolean (default: null/undefined or empty array)
 *   lastUpdatedAt  ISO string | epoch ms — drives stale badge
 *   staleAfterMs   number — explicit threshold (preferred over thresholdKey)
 *   thresholdKey   keyof STALE_THRESHOLDS_MS — falls back to STALE_THRESHOLDS_MS.default
 *   title          string — shown above error/empty affordances
 *   forceStale     boolean — LABELED_STALE-verdict tiles set true; toggles only between branches 4 and 5
 *   children       React.ReactNode — rendered when not loading/empty/error
 */
export default function TileState({
  query,
  isEmpty,
  lastUpdatedAt,
  staleAfterMs,
  thresholdKey,
  title,
  forceStale = false,
  children,
}) {
  const isEmptyFn = typeof isEmpty === 'function' ? isEmpty : defaultIsEmpty
  const effectiveStaleAfterMs =
    typeof staleAfterMs === 'number'
      ? staleAfterMs
      : STALE_THRESHOLDS_MS[thresholdKey] ?? STALE_THRESHOLDS_MS.default

  // ---- Branch 1: ERROR (highest precedence; errors are LOUD) -------------
  if (query?.isError) {
    return (
      <div style={{ position: 'relative' }}>
        <ErrorState title={title} error={query.error} onRetry={query.refetch} />
      </div>
    )
  }

  // ---- Branch 2: LOADING --------------------------------------------------
  if (query?.isLoading && !query?.data) {
    return (
      <div style={{ position: 'relative' }}>
        <Skeleton />
      </div>
    )
  }

  // ---- Branch 3: EMPTY ----------------------------------------------------
  if (query?.isSuccess && isEmptyFn(query.data)) {
    return (
      <div style={{ position: 'relative' }}>
        <EmptyState title={title} />
      </div>
    )
  }

  // ---- Branches 4 + 5: success non-empty (stale-overlay vs steady) -------
  const showStale =
    Boolean(forceStale) ||
    isStaleByTimestamp(lastUpdatedAt, effectiveStaleAfterMs)

  if (showStale && query?.isSuccess && !isEmptyFn(query.data)) {
    return (
      <div style={{ position: 'relative' }}>
        <StaleBadge />
        {children}
      </div>
    )
  }

  // Steady state (success non-empty, not stale).
  return <>{children}</>
}
