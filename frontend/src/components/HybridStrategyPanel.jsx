import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { tradingAPI } from '../services/api'
import TileState from './TileState'

/**
 * Hybrid Strategy Panel Component
 *
 * Displays strategy routing information:
 * - Current market regime (TRENDING/RANGING), from the engine's regime detector
 * - Routing branch distribution (Trend-Following vs Mean Reversion)
 * - Whether the router is EXECUTING, ADVISORY, or has made no decisions
 *
 * Created: 2026-01-06
 *
 * UPDATED 2026-05-13 (Plan 06-05, DASH-05): wrapped in <TileState/>.
 *
 * REWRITTEN 2026-08-21 — the tile was structurally incapable of telling the
 * truth. `hybrid_strategy_stats` was only emitted by the backend in RESEARCH
 * or HYBRID mode; the deployed mode is `ensemble`, so the key was ABSENT from
 * every payload, and `hybrid.trend_pct || 0` rendered that absence as
 * "0.0% — 0 signals routed" for seven months while a hardcoded green "Live"
 * dot pulsed next to it. See docs/PIPELINE_MAP.md §0.
 *
 * Three rules now hold and are covered by tests:
 *   1. A null percentage renders as "n/a", never "0.0%". Missing data and a
 *      measured zero must not look the same.
 *   2. `routing_mode` from the backend is rendered verbatim as a badge, so a
 *      router that is only observing can never be presented as one that is
 *      steering.
 *   3. The "Live" indicator is derived from query state and the funnel's
 *      last_event_at, not hardcoded.
 */

const REGIME_STYLE = {
  TRENDING: { color: 'text-blue-400', icon: '📈' },
  RANGING: { color: 'text-emerald-400', icon: '↔️' },
  VOLATILE: { color: 'text-amber-400', icon: '⚡' },
  MIXED: { color: 'text-slate-400', icon: '⚖️' },
  UNKNOWN: { color: 'text-slate-500', icon: '❔' },
}

// Backend enum: app/aggregation/market_regime.py MarketRegime.
// The previous version bucketed on MEAN_REVERTING / RANGE_BOUND, which the
// backend has never emitted, so the mean-reversion side of the ratio was
// permanently under-counted and the tile skewed TRENDING.
const TRENDING_KEYS = ['STRONG_TREND', 'TRENDING', 'WEAK_TREND']
const RANGING_KEYS = ['RANGING']
const OTHER_REGIME_KEYS = ['VOLATILE', 'UNKNOWN']

const ROUTING_MODE_BADGE = {
  executing: {
    label: 'EXECUTING',
    detail: 'The router selects the strategy that trades.',
    className: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  },
  mixed: {
    label: 'MIXED',
    detail: 'Some decisions executed, some advisory only.',
    className: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  },
  advisory: {
    label: 'ADVISORY',
    detail:
      'The router classifies the regime on every evaluation, but the ' +
      'configured strategy executes. These counts are observations.',
    className: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  },
  inactive: {
    label: 'NO DECISIONS',
    detail:
      'The router has not classified a single evaluation. Either the engine ' +
      'has not evaluated yet, or STRATEGY_ROUTING_MODE is off.',
    className: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  },
}

const MODE_LABELS = {
  ensemble: 'Ensemble (RSI + Multi-Indicator + Mean-Rev)',
  research: 'Research',
  hybrid: 'Hybrid',
  grid_trading: 'Grid Trading',
  standard: 'Standard',
}

/** Percentage formatter that refuses to turn absent data into a zero. */
function pct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a'
  return `${Number(value).toFixed(1)}%`
}

function count(value) {
  if (value === null || value === undefined) return 'n/a'
  return Number(value).toLocaleString()
}

export default function HybridStrategyPanel() {
  const q = useQuery({
    queryKey: ['trading-status'],
    queryFn: () => tradingAPI.getStatus(),
    refetchInterval: 5000,
    staleTime: 4000,
  })

  const status = q.data?.status
  const hybrid = status?.hybrid_strategy_stats
  const funnel = status?.signal_funnel

  // routing_mode is authoritative. `undefined` means the backend predates this
  // field — surfaced as its own state rather than silently treated as zero.
  const routingMode = hybrid?.routing_mode
  const badge = ROUTING_MODE_BADGE[routingMode] || {
    label: 'UNREPORTED',
    detail:
      'The engine did not report routing_mode. It is running a build from ' +
      'before 2026-08-21; these counters cannot be interpreted.',
    className: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  }

  const trendPct = hybrid?.trend_pct ?? null
  const meanRevPct = hybrid?.mean_reversion_pct ?? null
  const totalSignals = hybrid?.total_signals ?? null
  const adxThreshold = hybrid?.adx_threshold ?? null

  // Current regime comes from the engine's regime detector distribution — a
  // different measurement from the routing counters, and labelled as such.
  const dist = status?.regime_detector_stats?.regime_distribution || status?.regime_distribution
  let currentRegime = 'UNKNOWN'
  let regimeSource = 'no regime data reported'
  if (dist && Object.keys(dist).length > 0) {
    const sum = (keys) => keys.reduce((s, k) => s + (dist[k] || 0), 0)
    const trendCount = sum(TRENDING_KEYS)
    const rangeCount = sum(RANGING_KEYS)
    const otherCount = sum(OTHER_REGIME_KEYS)
    const total = trendCount + rangeCount + otherCount
    regimeSource = `${total.toLocaleString()} detections`
    if (total === 0) {
      currentRegime = 'UNKNOWN'
    } else if (trendCount > rangeCount * 1.5) {
      currentRegime = 'TRENDING'
    } else if (rangeCount > trendCount * 1.5) {
      currentRegime = 'RANGING'
    } else {
      currentRegime = 'MIXED'
    }
  }
  const regimeStyle = REGIME_STYLE[currentRegime] || REGIME_STYLE.UNKNOWN

  const strategyMode = status?.strategy_mode
  const activeStrategy = strategyMode
    ? MODE_LABELS[strategyMode] || strategyMode
    : 'not reported'

  // Liveness derived from data, not asserted by a literal.
  const lastEventAt = funnel?.last_event_at ? new Date(funnel.last_event_at) : null
  const secondsSinceEvent = lastEventAt ? (Date.now() - lastEventAt.getTime()) / 1000 : null
  const isLive = q.isSuccess && secondsSinceEvent !== null && secondsSinceEvent < 180

  return (
    <div data-testid="hybrid-strategy-panel" style={{ display: 'contents' }}>
      <TileState
        query={q}
        title="Hybrid Strategy Routing"
        thresholdKey="signals"
        lastUpdatedAt={undefined}
        isEmpty={(d) => !d || !d.status || !d.status.hybrid_strategy_stats}
      >
        <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700/50 backdrop-blur-sm">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center shadow-lg" style={{ background: 'linear-gradient(135deg, #5eead4 0%, #d4af6a 100%)', boxShadow: '0 4px 14px rgba(94, 234, 212, 0.18)' }}>
                <svg className="w-4 h-4" style={{ color: '#0a0a0b' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-slate-200">Hybrid Strategy Routing</h2>
            </div>
            <div className="flex items-center gap-1.5" data-testid="routing-liveness">
              <div
                className={`w-2 h-2 rounded-full ${
                  isLive ? 'bg-emerald-500 animate-pulse shadow-sm shadow-emerald-500/50' : 'bg-slate-600'
                }`}
              />
              <span className="text-xs text-slate-500">
                {isLive
                  ? `Live · ${Math.round(secondsSinceEvent)}s ago`
                  : secondsSinceEvent === null
                    ? 'No engine activity reported'
                    : `Stale · ${Math.round(secondsSinceEvent)}s ago`}
              </span>
            </div>
          </div>

          {/* Routing mode — the field that stops this tile lying */}
          <div
            data-testid="routing-mode-badge"
            className={`mb-4 rounded-lg border px-3 py-2 ${badge.className}`}
          >
            <div className="text-xs font-bold tracking-wider">ROUTER: {badge.label}</div>
            <div className="text-xs mt-1 opacity-80 leading-relaxed">{badge.detail}</div>
          </div>

          {/* Current Regime Card */}
          <div className="bg-slate-900/50 rounded-lg p-4 mb-6 border border-slate-700/30">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Current Market</span>
              <span className="text-2xl">{regimeStyle.icon}</span>
            </div>
            <div className={`text-2xl font-bold ${regimeStyle.color} mb-1`}>
              {currentRegime}
            </div>
            <div className="text-xs text-slate-500 mb-2">
              from regime detector · {regimeSource}
            </div>
            <div className="text-sm text-slate-400">
              Executing Strategy: <span className="font-medium text-cyan-400">{activeStrategy}</span>
            </div>
          </div>

          {/* Routing branch distribution */}
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-300">Trend-Following</span>
                <span className="text-sm font-bold text-blue-400" data-testid="trend-pct">{pct(trendPct)}</span>
              </div>
              <div className="w-full bg-slate-700/30 rounded-full h-3 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all duration-500 shadow-lg shadow-blue-500/30"
                  style={{ width: `${trendPct ?? 0}%` }}
                />
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {count(hybrid?.trend_signals)} decisions
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-300">Mean Reversion</span>
                <span className="text-sm font-bold text-emerald-400" data-testid="mean-rev-pct">{pct(meanRevPct)}</span>
              </div>
              <div className="w-full bg-slate-700/30 rounded-full h-3 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-emerald-600 rounded-full transition-all duration-500 shadow-lg shadow-emerald-500/30"
                  style={{ width: `${meanRevPct ?? 0}%` }}
                />
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {count(hybrid?.mean_reversion_signals)} decisions
              </div>
            </div>
          </div>

          {/* Statistics Footer */}
          <div className="mt-6 pt-4 border-t border-slate-700/30 space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">Total Routing Decisions</span>
              <span className="font-mono font-medium text-slate-300" data-testid="total-routing-decisions">
                {count(totalSignals)}
              </span>
            </div>
            {hybrid?.observed_signals !== undefined && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">of which advisory / executed</span>
                <span className="font-mono text-slate-400">
                  {count(hybrid.observed_signals)} / {count(hybrid.executed_signals)}
                </span>
              </div>
            )}
          </div>

          {/* Info */}
          <div className="mt-4 p-3 bg-slate-900/30 rounded-lg border border-slate-700/20">
            <div className="flex gap-2">
              <svg className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-xs text-slate-400 leading-relaxed">
                <span className="font-medium text-slate-300">Routing rule:</span>{' '}
                trend-following when ADX &ge;{' '}
                {adxThreshold === null ? 'n/a' : adxThreshold}, mean reversion below it.
                {adxThreshold === null && ' (threshold not reported by the engine)'}
              </div>
            </div>
          </div>
        </div>
      </TileState>
    </div>
  )
}
