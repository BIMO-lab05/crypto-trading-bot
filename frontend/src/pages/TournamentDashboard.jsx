import React, { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'

import useTournamentList from '../hooks/useTournamentList'
import useTournamentSnapshot from '../hooks/useTournamentSnapshot'
import TileState from '../components/TileState'
import TournamentSelector from '../components/TournamentSelector'
import TournamentLeaderboard from '../components/TournamentLeaderboard'
import TournamentFilterChips from '../components/TournamentFilterChips'
import ContaminatedWindowWarning from '../components/ContaminatedWindowWarning'

import '../pages/performance-theme.css'

/**
 * TournamentDashboard — top-level /tournament page composition.
 *
 * Decisions referenced:
 *   - D-09  new top-level /tournament route
 *   - D-10  layout: sticky header → selector → filter chips → table → footer
 *   - D-11  plain <table>, no TanStack (TournamentLeaderboard handles render)
 *   - D-12  sort default dsr DESC; click-to-sort; sort state in URL
 *   - D-13  filter state in URL via useSearchParams
 *   - D-23  staleTime: Infinity (TileState staleAfterMs={Infinity})
 *
 * URL params:
 *   ?tournament_id=<id>
 *   ?symbol=BTC,SOL          (comma-separated multi-select)
 *   ?arch=GRU,LSTM           (comma-separated multi-select)
 *   ?status=success|failed|all
 *   ?sort=dsr|oos_sharpe|psr|dir_acc_corrected|r2_returns|train_seconds
 *   ?dir=asc|desc
 */

// Editorial Trading Floor palette tokens — inlined per phase convention
// (no shared tokens module — out of scope per Phase 6 06-PATTERNS.md).
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

const SORT_WHITELIST = ['dsr', 'oos_sharpe', 'psr', 'dir_acc_corrected', 'r2_returns', 'train_seconds']
const DIR_WHITELIST = ['asc', 'desc']

function clampSort(raw) {
  return SORT_WHITELIST.includes(raw) ? raw : 'dsr'
}
function clampDir(raw) {
  return DIR_WHITELIST.includes(raw) ? raw : 'desc'
}

function parseList(raw) {
  if (!raw || typeof raw !== 'string') return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
}

// Null/undefined values sort LAST regardless of direction (per plan spec).
function compareRows(a, b, col, dir) {
  const av = a?.[col]
  const bv = b?.[col]
  const aMissing = av == null || !Number.isFinite(av)
  const bMissing = bv == null || !Number.isFinite(bv)
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  if (av === bv) return 0
  if (dir === 'asc') return av < bv ? -1 : 1
  return av < bv ? 1 : -1
}

function truncateSha(s) {
  if (!s || typeof s !== 'string') return ''
  return s.slice(0, 7)
}

export default function TournamentDashboard() {
  const [params, setParams] = useSearchParams()

  const tournamentId = params.get('tournament_id') ?? ''
  const selectedSymbols = parseList(params.get('symbol'))
  const selectedArchs = parseList(params.get('arch'))
  const selectedStatus = params.get('status') ?? 'all'
  const sortCol = clampSort(params.get('sort') ?? 'dsr')
  const sortDir = clampDir(params.get('dir') ?? 'desc')

  const listQuery = useTournamentList()
  const snapshotQuery = useTournamentSnapshot(tournamentId)

  const sortedTournaments = useMemo(() => {
    const list = listQuery.data?.tournaments ?? []
    return [...list].sort((a, b) => {
      const aa = a?.exported_at || ''
      const bb = b?.exported_at || ''
      if (aa === bb) return 0
      return aa < bb ? 1 : -1
    })
  }, [listQuery.data])

  // Auto-select the latest tournament when URL has no tournament_id and the
  // list is non-empty. Use replace=true so we don't litter browser history.
  useEffect(() => {
    if (!tournamentId && sortedTournaments.length > 0) {
      const latest = sortedTournaments[0]?.tournament_id
      if (latest) {
        setParams(
          (prev) => {
            const next = new URLSearchParams(prev)
            next.set('tournament_id', latest)
            return next
          },
          { replace: true },
        )
      }
    }
    // setParams is stable; sortedTournaments captures listQuery.data
  }, [tournamentId, sortedTournaments, setParams])

  const rows = snapshotQuery.data?.snapshot?.rows ?? []
  const exportedAt = snapshotQuery.data?.snapshot?.exported_at

  const ensembleMembersBySymbol = useMemo(() => {
    const out = {}
    const ensembles = snapshotQuery.data?.ensemble?.ensembles ?? []
    if (!Array.isArray(ensembles)) return out
    for (const ent of ensembles) {
      const sym = ent?.symbol
      const members = ent?.members
      if (!sym || !Array.isArray(members)) continue
      const set = new Set()
      for (const m of members) {
        if (m?.run_id != null) set.add(m.run_id)
      }
      out[sym] = set
    }
    return out
  }, [snapshotQuery.data])

  const perSymbolSignificance = snapshotQuery.data?.significance?.per_symbol ?? {}

  const anyContaminated = useMemo(
    () => rows.some((r) => r?.train_window_includes_contaminated === true),
    [rows],
  )

  // Filter pipeline — counts computed against the OTHER axes per
  // standard multi-facet behavior (a SOL chip's count reflects the rows
  // matching arch + status filters, but NOT the symbol filter).
  const counts = useMemo(() => {
    const symbolCounts = {}
    const archCounts = {}
    const statusCounts = {}
    for (const row of rows) {
      const passArch = selectedArchs.length === 0 || selectedArchs.includes(row?.architecture)
      const passStatus = selectedStatus === 'all' || row?.status === selectedStatus
      const passSymbol = selectedSymbols.length === 0 || selectedSymbols.includes(row?.symbol)
      // Symbol counts: ignore symbol filter, apply arch + status filters
      if (passArch && passStatus && row?.symbol) {
        symbolCounts[row.symbol] = (symbolCounts[row.symbol] ?? 0) + 1
      }
      // Arch counts: ignore arch filter, apply symbol + status filters
      if (passSymbol && passStatus && row?.architecture) {
        archCounts[row.architecture] = (archCounts[row.architecture] ?? 0) + 1
      }
      // Status counts: ignore status filter, apply symbol + arch filters
      if (passSymbol && passArch) {
        const s = row?.status
        if (s) statusCounts[s] = (statusCounts[s] ?? 0) + 1
        statusCounts.all = (statusCounts.all ?? 0) + 1
      }
    }
    return { symbol: symbolCounts, arch: archCounts, status: statusCounts }
  }, [rows, selectedSymbols, selectedArchs, selectedStatus])

  const sortedRows = useMemo(() => {
    const filtered = rows.filter((row) => {
      if (selectedSymbols.length > 0 && !selectedSymbols.includes(row?.symbol)) return false
      if (selectedArchs.length > 0 && !selectedArchs.includes(row?.architecture)) return false
      if (selectedStatus !== 'all' && row?.status !== selectedStatus) return false
      return true
    })
    const arr = [...filtered]
    arr.sort((a, b) => compareRows(a, b, sortCol, sortDir))
    return arr
  }, [rows, selectedSymbols, selectedArchs, selectedStatus, sortCol, sortDir])

  const isFetching = listQuery.isFetching || snapshotQuery.isFetching

  const onSelectTournament = (id) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tournament_id', id)
      return next
    })
  }

  const onSort = (col) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      const cur = prev.get('sort')
      const curDir = prev.get('dir') ?? 'desc'
      if (cur === col) {
        next.set('dir', curDir === 'desc' ? 'asc' : 'desc')
      } else {
        next.set('sort', col)
        next.set('dir', 'desc')
      }
      return next
    })
  }

  const onRefresh = () => {
    listQuery.refetch()
    snapshotQuery.refetch()
  }

  // Footer metadata — pull from the first row of the snapshot (all rows in
  // a tournament share tournament_start_ts + git_sha per Phase 3 schema).
  const firstRow = rows[0] ?? null
  const tournamentStartTs = firstRow?.tournament_start_ts ?? ''
  const gitSha = firstRow?.git_sha ?? ''

  return (
    <div
      style={{
        background: C.bg,
        minHeight: '100vh',
        color: C.text,
        fontFamily: 'Manrope, system-ui, sans-serif',
      }}
    >
      {/* Sticky page header */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 40,
          background: 'rgba(10, 10, 11, 0.86)',
          backdropFilter: 'blur(14px)',
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div
          className="px-6 py-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between"
          style={{ maxWidth: '88rem', margin: '0 auto' }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <h1
              style={{
                fontFamily: 'Fraunces, serif',
                fontSize: 28,
                fontWeight: 500,
                color: C.text,
                lineHeight: 1.2,
                letterSpacing: '-0.025em',
                margin: 0,
                fontVariationSettings: '"opsz" 144',
              }}
            >
              Tournament Leaderboard
            </h1>
            <span
              style={{
                fontFamily: 'Manrope, system-ui, sans-serif',
                fontSize: 10,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                fontWeight: 600,
                color: C.text3,
              }}
            >
              ML evaluation runs · DSR + bootstrap significance
            </span>
          </div>
          <button
            type="button"
            data-testid="tournament-refresh"
            onClick={onRefresh}
            disabled={isFetching}
            title="Re-read tournament snapshot from disk"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'transparent',
              border: `1px solid ${C.border}`,
              borderRadius: 4,
              padding: '4px 12px',
              color: isFetching ? C.text3 : C.text2,
              fontFamily: 'Manrope, system-ui, sans-serif',
              fontSize: 11,
              fontWeight: 500,
              cursor: isFetching ? 'wait' : 'pointer',
              opacity: isFetching ? 0.5 : 1,
              transition: 'color 120ms ease',
            }}
          >
            <RefreshCw
              size={11}
              className={isFetching ? 'animate-spin' : ''}
              aria-hidden="true"
            />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      <main
        style={{
          maxWidth: '88rem',
          margin: '0 auto',
          padding: 'clamp(1.5rem, 3vw, 2.75rem) clamp(1rem, 3vw, 2rem) 5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: 'clamp(2rem, 4vw, 3.5rem)',
        }}
      >
        <TournamentSelector
          tournaments={listQuery.data?.tournaments ?? []}
          selectedId={tournamentId}
          onChange={onSelectTournament}
        />

        <TournamentFilterChips counts={counts} />

        <TileState
          query={snapshotQuery}
          title="Tournament Leaderboard"
          isEmpty={(d) => !d?.snapshot?.rows?.length}
          lastUpdatedAt={exportedAt}
          staleAfterMs={Infinity}
        >
          <TournamentLeaderboard
            rows={sortedRows}
            ensembleMembersBySymbol={ensembleMembersBySymbol}
            perSymbolSignificance={perSymbolSignificance}
            sort={sortCol}
            dir={sortDir}
            onSort={onSort}
          />
        </TileState>

        <ContaminatedWindowWarning visible={anyContaminated} />

        <div
          data-testid="tournament-footer"
          style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            color: C.text3,
            textAlign: 'center',
            fontFeatureSettings: '"tnum" 1, "zero" 1',
          }}
        >
          {exportedAt ? `exported ${exportedAt}` : ''}
          {gitSha ? ` · git ${truncateSha(gitSha)}` : ''}
          {tournamentStartTs ? ` · tournament started ${tournamentStartTs}` : ''}
        </div>
      </main>
    </div>
  )
}
