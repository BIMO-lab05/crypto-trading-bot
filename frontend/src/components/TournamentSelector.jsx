import React from 'react'

/**
 * TournamentSelector — native <select> dropdown for picking which committed
 * tournament snapshot to view. Sorted by `exported_at` descending so the
 * latest tournament is the first option (and the default auto-selection in
 * TournamentDashboard).
 *
 * Decisions referenced:
 *   - D-10 (Phase 7) — selector sits between sticky header and filter chips
 *
 * Pure presentational; URL-state lives in the parent (TournamentDashboard).
 */

// Editorial Trading Floor palette tokens — inlined per phase convention.
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

function formatExportedAt(iso) {
  if (!iso || typeof iso !== 'string') return ''
  // Slice the ISO datetime at the `T` to render only the date portion.
  const idx = iso.indexOf('T')
  return idx === -1 ? iso : iso.slice(0, idx)
}

export default function TournamentSelector({ tournaments, selectedId, onChange }) {
  const list = Array.isArray(tournaments) ? tournaments : []
  const sorted = [...list].sort((a, b) => {
    const aa = a?.exported_at || ''
    const bb = b?.exported_at || ''
    if (aa === bb) return 0
    return aa < bb ? 1 : -1
  })

  const empty = sorted.length === 0
  const value = selectedId || ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span
        style={{
          color: C.text3,
          fontSize: 10,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          fontWeight: 600,
          fontFamily: 'Manrope, system-ui, sans-serif',
        }}
      >
        TOURNAMENT
      </span>
      <select
        data-testid="tournament-selector"
        value={value}
        onChange={(e) => {
          const next = e.target.value
          if (typeof onChange === 'function') onChange(next)
        }}
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          color: C.text,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 13,
          padding: '8px 12px',
          borderRadius: 4,
          fontFeatureSettings: '"tnum" 1, "zero" 1',
        }}
      >
        {empty && (
          <option value="" disabled>
            {'No tournaments available'}
          </option>
        )}
        {!empty && value === '' && (
          <option value="" disabled>
            {'Select a tournament…'}
          </option>
        )}
        {sorted.map((t) => {
          const tid = t?.tournament_id || ''
          const exported = formatExportedAt(t?.exported_at)
          const n = t?.n_rows ?? 0
          const label = `${tid} · ${exported} · ${n} runs`
          return (
            <option key={tid} value={tid}>
              {label}
            </option>
          )
        })}
      </select>
    </div>
  )
}
