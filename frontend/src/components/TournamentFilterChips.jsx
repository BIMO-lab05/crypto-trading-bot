import React from 'react'
import { useSearchParams } from 'react-router-dom'
import { X } from 'lucide-react'

/**
 * TournamentFilterChips — three filter groups + clear button.
 *
 * Groups:
 *   - SYMBOLS (multi-select, stable order: BTC, ETH, SOL, BNB, ADA)
 *   - ARCHITECTURE (multi-select: GRU, LSTM, Transformer, TCN)
 *   - STATUS (segmented single-select: success / failed / all)
 *
 * Decisions referenced:
 *   - D-13  filter state in URL params via useSearchParams
 *   - D-14  filter pills show counts + Clear filters when any chip active
 *
 * URL serialization:
 *   ?symbol=SOL,ADA    comma-separated multi-select
 *   ?arch=GRU,LSTM     comma-separated multi-select
 *   ?status=success    single-select; default = 'all' (param stripped)
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

const SYMBOLS = ['BTC', 'ETH', 'SOL', 'BNB', 'ADA']
const ARCHS = ['GRU', 'LSTM', 'Transformer', 'TCN']
const STATUSES = ['success', 'failed', 'all']

function parseList(raw) {
  if (!raw || typeof raw !== 'string') return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
}

function eyebrowStyle() {
  return {
    color: C.text3,
    fontSize: 10,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    fontWeight: 600,
    fontFamily: 'Manrope, system-ui, sans-serif',
    minWidth: 96,
  }
}

function chipStyle(selected) {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '4px 10px',
    borderRadius: 4,
    border: selected ? `1px solid ${C.borderStrong}` : `1px solid ${C.border}`,
    background: selected ? C.surface2 : C.surface,
    color: selected ? C.text : C.text2,
    fontFamily: 'Manrope, system-ui, sans-serif',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background-color 120ms ease, color 120ms ease, border-color 120ms ease',
  }
}

function segmentStyle(active, isFirst, isLast) {
  return {
    padding: '4px 12px',
    background: active ? C.surface2 : C.surface,
    color: active ? C.text : C.text2,
    border: 'none',
    borderRight: isLast ? 'none' : `1px solid ${C.border}`,
    borderLeft: isFirst ? 'none' : 'none',
    fontFamily: 'Manrope, system-ui, sans-serif',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    textTransform: 'lowercase',
    transition: 'background-color 120ms ease, color 120ms ease',
  }
}

export default function TournamentFilterChips({ counts }) {
  const [params, setParams] = useSearchParams()

  const selectedSymbols = parseList(params.get('symbol'))
  const selectedArchs = parseList(params.get('arch'))
  const selectedStatus = params.get('status') || 'all'

  const symbolCounts = counts?.symbol || {}
  const archCounts = counts?.arch || {}
  const statusCounts = counts?.status || {}

  const writeMulti = (key, nextList) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (nextList.length === 0) {
        next.delete(key)
      } else {
        next.set(key, nextList.join(','))
      }
      return next
    })
  }

  const toggleSymbol = (sym) => {
    const has = selectedSymbols.includes(sym)
    const nextList = has ? selectedSymbols.filter((s) => s !== sym) : [...selectedSymbols, sym]
    writeMulti('symbol', nextList)
  }

  const toggleArch = (arch) => {
    const has = selectedArchs.includes(arch)
    const nextList = has ? selectedArchs.filter((a) => a !== arch) : [...selectedArchs, arch]
    writeMulti('arch', nextList)
  }

  const setStatus = (s) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (s === 'all') {
        next.delete('status')
      } else {
        next.set('status', s)
      }
      return next
    })
  }

  const hasNonDefault =
    selectedSymbols.length > 0 || selectedArchs.length > 0 || selectedStatus !== 'all'

  const clearAll = () => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('symbol')
      next.delete('arch')
      next.delete('status')
      next.delete('sort')
      next.delete('dir')
      return next
    })
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      {/* SYMBOLS row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={eyebrowStyle()}>SYMBOLS</span>
        {SYMBOLS.map((sym) => {
          const selected = selectedSymbols.includes(sym)
          const count = symbolCounts[sym] ?? 0
          return (
            <button
              key={sym}
              type="button"
              data-testid={`tournament-filter-chip-symbol-${sym}`}
              aria-pressed={selected}
              onClick={() => toggleSymbol(sym)}
              style={chipStyle(selected)}
            >
              <span>{sym}</span>
              <span
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11,
                  color: C.text3,
                  fontFeatureSettings: '"tnum" 1, "zero" 1',
                }}
              >
                {`(${count})`}
              </span>
            </button>
          )
        })}
      </div>

      {/* ARCHITECTURE row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={eyebrowStyle()}>ARCHITECTURE</span>
        {ARCHS.map((arch) => {
          const selected = selectedArchs.includes(arch)
          const count = archCounts[arch] ?? 0
          return (
            <button
              key={arch}
              type="button"
              data-testid={`tournament-filter-chip-arch-${arch}`}
              aria-pressed={selected}
              onClick={() => toggleArch(arch)}
              style={chipStyle(selected)}
            >
              <span>{arch}</span>
              <span
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11,
                  color: C.text3,
                  fontFeatureSettings: '"tnum" 1, "zero" 1',
                }}
              >
                {`(${count})`}
              </span>
            </button>
          )
        })}
      </div>

      {/* STATUS row + Clear filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={eyebrowStyle()}>STATUS</span>
        <div
          role="group"
          aria-label="Status filter"
          data-testid="tournament-filter-status"
          style={{
            display: 'inline-flex',
            border: `1px solid ${C.borderStrong}`,
            borderRadius: 4,
            overflow: 'hidden',
          }}
        >
          {STATUSES.map((s, idx) => {
            const active = selectedStatus === s
            const count = statusCounts[s] ?? 0
            return (
              <button
                key={s}
                type="button"
                aria-pressed={active}
                onClick={() => setStatus(s)}
                style={segmentStyle(active, idx === 0, idx === STATUSES.length - 1)}
              >
                <span>{s}</span>
                <span
                  style={{
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 11,
                    marginLeft: 4,
                    color: C.text3,
                    fontFeatureSettings: '"tnum" 1, "zero" 1',
                  }}
                >
                  {`(${count})`}
                </span>
              </button>
            )
          })}
        </div>
        {hasNonDefault && (
          <button
            type="button"
            onClick={clearAll}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 8px',
              border: 'none',
              background: 'transparent',
              color: C.text3,
              fontFamily: 'Manrope, system-ui, sans-serif',
              fontSize: 11,
              cursor: 'pointer',
              marginLeft: 'auto',
            }}
          >
            <X size={11} />
            <span>Clear filters</span>
          </button>
        )}
      </div>
    </div>
  )
}
