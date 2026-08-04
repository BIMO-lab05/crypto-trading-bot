import React from 'react'
import SignificanceBadge from './SignificanceBadge'

/**
 * TournamentLeaderboard — semantic <table> rendering one tournament's
 * leaderboard rows with click-to-sort headers, mint/rose value coloring,
 * and a significance column powered by SignificanceBadge.
 *
 * Decisions referenced:
 *   - D-07  failed runs render row marker + rose failure_reason cell (not empty)
 *   - D-11  plain <table>, no TanStack
 *   - D-12  sort default dsr DESC; click-to-sort; sort state lives in URL
 *
 * Props:
 *   rows                          Array of snapshot rows (snapshot.rows[])
 *   ensembleMembersBySymbol       Record<symbol, Set<run_id>>
 *   perSymbolSignificance         Record<symbol, SignificanceObj|null>
 *   sort                          current sort column (already whitelisted by parent)
 *   dir                           'asc' | 'desc'
 *   onSort                        (column: string) => void
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

const MINUS = '−' // U+2212 minus sign for signed R² display
const EMDASH = '—'

const SORTABLE = new Set([
  'dsr',
  'oos_sharpe',
  'psr',
  'dir_acc_corrected',
  'r2_returns',
  'train_seconds',
])

// Column definitions — order is the rendering order; width is in px; align
// is the text-align for the <th> and the <td>; key is the row property.
const COLUMNS = [
  { key: '__marker', label: '', width: 8, align: 'left', sortable: false, numeric: false },
  { key: 'architecture', label: 'ARCHITECTURE', width: 96, align: 'left', sortable: false, numeric: false },
  { key: 'symbol', label: 'SYMBOL', width: 64, align: 'left', sortable: false, numeric: false },
  { key: 'horizon', label: 'HORIZON', width: 64, align: 'right', sortable: false, numeric: true },
  { key: 'target_mode', label: 'TARGET MODE', width: 96, align: 'left', sortable: false, numeric: false },
  { key: 'dsr', label: 'DSR', width: 80, align: 'right', sortable: true, numeric: true },
  { key: 'oos_sharpe', label: 'OOS SHARPE', width: 80, align: 'right', sortable: true, numeric: true },
  { key: 'psr', label: 'PSR', width: 80, align: 'right', sortable: true, numeric: true },
  { key: 'dir_acc_corrected', label: 'DIR.ACC.', width: 80, align: 'right', sortable: true, numeric: true },
  { key: 'r2_returns', label: 'R² RETURNS', width: 88, align: 'right', sortable: true, numeric: true },
  { key: '__significance', label: 'SIGNIFICANCE', width: 128, align: 'center', sortable: false, numeric: false },
  { key: 'train_seconds', label: 'TRAIN SECONDS', width: 80, align: 'right', sortable: true, numeric: true },
  { key: 'status', label: 'STATUS', width: 80, align: 'left', sortable: false, numeric: false },
  { key: 'failure_reason', label: 'FAILURE REASON', width: 160, align: 'left', sortable: false, numeric: false, flex: true },
]

function isFiniteNum(v) {
  return typeof v === 'number' && Number.isFinite(v)
}

function fmtFixed(v, dp) {
  if (!isFiniteNum(v)) return EMDASH
  return v.toFixed(dp)
}

function fmtPercent(v, dp) {
  if (!isFiniteNum(v)) return EMDASH
  return `${(v * 100).toFixed(dp)}%`
}

function fmtSignedFixed(v, dp) {
  if (!isFiniteNum(v)) return EMDASH
  const sign = v >= 0 ? '+' : MINUS
  return `${sign}${Math.abs(v).toFixed(dp)}`
}

function fmtInt(v) {
  if (!isFiniteNum(v)) return EMDASH
  return String(Math.round(v))
}

function colorForValue(key, value) {
  if (!isFiniteNum(value)) return C.text
  if (key === 'dsr') {
    if (value < 0) return C.loss
    if (value >= 1.0) return C.gain
    return C.text
  }
  if (key === 'oos_sharpe') {
    if (value < 0) return C.loss
    if (value >= 1.0) return C.gain
    return C.text
  }
  if (key === 'dir_acc_corrected') {
    if (value > 0.05) return C.gain
    return C.text
  }
  if (key === 'r2_returns') {
    if (value < 0) return C.loss
    if (value > 0) return C.gain
    return C.text
  }
  return C.text
}

function renderNumeric(key, row) {
  const value = row?.[key]
  const color = colorForValue(key, value)
  let text
  switch (key) {
    case 'dsr':
    case 'psr':
      text = fmtFixed(value, 3)
      break
    case 'oos_sharpe':
      text = fmtFixed(value, 2)
      break
    case 'dir_acc_corrected':
      text = fmtPercent(value, 2)
      break
    case 'r2_returns':
      text = fmtSignedFixed(value, 4)
      break
    case 'train_seconds':
      text = fmtInt(value)
      break
    case 'horizon':
      text = fmtInt(value)
      break
    default:
      text = isFiniteNum(value) ? String(value) : EMDASH
  }
  return (
    <span
      style={{
        color,
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 500,
        fontSize: 13,
        letterSpacing: '0.01em',
        fontFeatureSettings: '"tnum" 1, "zero" 1',
      }}
    >
      {text}
    </span>
  )
}

function thStyle(col, isActive) {
  return {
    width: col.flex ? 'auto' : col.width,
    minWidth: col.flex ? col.width : undefined,
    textAlign: col.align,
    padding: '8px 8px',
    color: isActive ? C.text : '#65645e',
    fontFamily: 'Manrope, system-ui, sans-serif',
    fontSize: 10,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    fontWeight: 600,
    borderBottom: `1px solid ${C.borderStrong}`,
    background: C.bg,
    whiteSpace: 'nowrap',
  }
}

function tdStyle(col, status) {
  const isFailed = status === 'failed'
  return {
    width: col.flex ? 'auto' : col.width,
    minWidth: col.flex ? col.width : undefined,
    textAlign: col.align,
    padding: '12px 8px',
    borderBottom: `1px solid ${C.border}`,
    color: C.text,
    verticalAlign: 'middle',
    // Failed-row left border applied to the marker column (first cell) only.
    borderLeft: col.key === '__marker' && isFailed ? `2px solid ${C.loss}` : undefined,
    whiteSpace: col.key === 'failure_reason' ? 'normal' : 'nowrap',
  }
}

function renderHeaderCell(col, sort, dir, onSort) {
  const isActive = sort === col.key
  const caret = isActive ? (dir === 'asc' ? '▲' : '▼') : ''
  if (col.sortable && SORTABLE.has(col.key)) {
    return (
      <th key={col.key} scope="col" style={thStyle(col, isActive)}>
        <button
          type="button"
          onClick={() => {
            if (typeof onSort === 'function') onSort(col.key)
          }}
          style={{
            background: 'transparent',
            border: 'none',
            padding: 0,
            color: 'inherit',
            font: 'inherit',
            letterSpacing: 'inherit',
            textTransform: 'inherit',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <span>{col.label}</span>
          {caret && (
            <span
              aria-hidden="true"
              style={{
                color: C.text,
                fontSize: 10,
              }}
            >
              {caret}
            </span>
          )}
        </button>
      </th>
    )
  }
  return (
    <th key={col.key} scope="col" style={thStyle(col, false)}>
      {col.label}
    </th>
  )
}

function renderMarkerCell(row) {
  const isFailed = row?.status === 'failed'
  const isContaminated = row?.train_window_includes_contaminated === true
  let dotColor = null
  if (isFailed) dotColor = C.loss
  else if (isContaminated) dotColor = C.gold
  if (!dotColor) return null
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: 4,
        height: 4,
        borderRadius: '50%',
        background: dotColor,
      }}
    />
  )
}

function renderCell(col, row, ensembleMembersBySymbol, perSymbolSignificance) {
  if (col.key === '__marker') {
    return renderMarkerCell(row)
  }
  if (col.key === '__significance') {
    const isFailed = row?.status === 'failed'
    if (isFailed) {
      return (
        <span
          data-testid="significance-badge-none"
          style={{ color: C.text3, fontFamily: 'JetBrains Mono, monospace', fontSize: 13 }}
        >
          {EMDASH}
        </span>
      )
    }
    const memberSet = ensembleMembersBySymbol?.[row?.symbol]
    const inEnsemble = memberSet && memberSet.has ? memberSet.has(row?.run_id) : false
    const sig = perSymbolSignificance?.[row?.symbol] ?? null
    const winGatePassed = Boolean(sig?.win_gate_passed)
    return (
      <SignificanceBadge
        inEnsemble={inEnsemble}
        winGatePassed={winGatePassed}
        significance={sig}
      />
    )
  }
  if (col.key === 'failure_reason') {
    if (row?.status !== 'failed') return null
    const reason = row?.failure_reason
    return (
      <span
        style={{
          color: C.loss,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 13,
          fontFeatureSettings: '"tnum" 1, "zero" 1',
        }}
      >
        {reason || EMDASH}
      </span>
    )
  }
  if (col.key === 'status') {
    const status = row?.status || ''
    const color = status === 'failed' ? C.loss : C.text
    return (
      <span
        style={{
          color,
          fontFamily: 'Manrope, system-ui, sans-serif',
          fontSize: 13,
          fontWeight: 500,
        }}
      >
        {status}
      </span>
    )
  }
  if (col.numeric) {
    return renderNumeric(col.key, row)
  }
  const text = row?.[col.key] ?? EMDASH
  return (
    <span style={{ color: C.text, fontFamily: 'Manrope, system-ui, sans-serif', fontSize: 13 }}>
      {text}
    </span>
  )
}

export default function TournamentLeaderboard({
  rows,
  ensembleMembersBySymbol,
  perSymbolSignificance,
  sort,
  dir,
  onSort,
}) {
  const list = Array.isArray(rows) ? rows : []
  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <table
        data-testid="tournament-leaderboard"
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          background: C.bg,
          color: C.text,
          tableLayout: 'auto',
        }}
      >
        <thead>
          <tr>{COLUMNS.map((col) => renderHeaderCell(col, sort, dir, onSort))}</tr>
        </thead>
        <tbody>
          {list.map((row, idx) => {
            // Phase 14 CR-03 fix: previously coalesced to literal `'unknown'`,
            // which produced duplicate React keys + duplicate
            // `data-testid="tournament-row-unknown"` when multiple rows had
            // null run_id. Index suffix disambiguates while preserving the
            // mirrored testid contract with TournamentDashboard.jsx
            // (`tournament-row-*` prefix).
            const runId = row?.run_id ?? `unknown-${idx}`
            const status = row?.status
            return (
              <tr
                key={runId}
                data-testid={`tournament-row-${runId}`}
              >
                {COLUMNS.map((col) => (
                  <td key={col.key} style={tdStyle(col, status)}>
                    {renderCell(col, row, ensembleMembersBySymbol, perSymbolSignificance)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
