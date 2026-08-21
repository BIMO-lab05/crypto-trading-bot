import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { tradingAPI } from '../services/api'
import TileState from './TileState'

/**
 * Signal Funnel Panel
 *
 * Created 2026-08-21. Renders GET /api/trading/signal-funnel: how many
 * evaluations reached each filter in the live signal path, how many passed,
 * and for every rejection the reason code plus the numeric values that caused
 * it ("confidence 0.2761 < 0.30").
 *
 * This exists because the Hybrid Strategy Routing tile could read
 * "0 signals routed" indefinitely without the system being able to say
 * whether that meant no opportunity or a dead code path. A funnel that
 * reports zeros WITH the stage they died at is not a silent failure.
 *
 * Rules mirrored from the backend module (app/monitoring/signal_funnel.py):
 *   - Every stage renders even at zero. An absent stage is a bug, not a
 *     rendering optimisation.
 *   - pass_rate_pct is null (not 0.0) when nothing was evaluated; rendered
 *     as "—", never "0.0%".
 *   - Stages marked `advisory` are labelled, because they are declared parts
 *     of the cascade that do not actually reject anything.
 */

const STAGE_LABELS = {
  evaluations: 'Evaluations (per symbol per cycle)',
  passed_risk_halt: 'Risk-manager halt',
  raw_signals_generated: 'Raw signals generated',
  passed_price_lookup: 'Current price available',
  passed_indicator_agreement: 'Indicator agreement (vote threshold)',
  passed_gatekeeper: 'Gatekeeper (trend filter)',
  passed_validator: 'Validator (volume)',
  passed_regime_filter: 'Regime filter (ADX hard-block)',
  passed_category_diversity: 'Category diversity',
  passed_consensus_count: 'Consensus count',
  passed_confidence_floor: 'Aggregator confidence floor',
  passed_atr_filter: 'ATR filter',
  routing_decision_made: 'Routing decision made',
  ensemble_signal_emitted: 'Ensemble signal emitted',
  passed_position_dedupe: 'No open position',
  passed_cooldown: 'Re-entry cooldown',
  passed_side_gate: 'Side permitted',
  passed_signal_confidence_gate: 'Entry confidence gate',
  passed_daily_limit: 'Daily trade limit',
  passed_stop_consistency: 'Stop/target consistency',
  passed_portfolio_heat: 'Portfolio heat',
  order_intent_emitted: 'Order intent emitted',
}

function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${Number(v).toFixed(1)}%`
}

function fmtNum(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString()
}

function fmtVal(v) {
  if (v === null || v === undefined) return null
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return Number.isInteger(n) ? String(n) : n.toFixed(4)
}

/** "confidence_below_min_signal_confidence — 84x, observed 0.2761 vs 0.30" */
function reasonLine(code, stat) {
  const parts = [`${stat.count}x`]
  const obsMin = fmtVal(stat.observed_min)
  const obsMax = fmtVal(stat.observed_max)
  const thr = fmtVal(stat.threshold)
  if (obsMin !== null) {
    parts.push(obsMin === obsMax ? `observed ${obsMin}` : `observed ${obsMin}–${obsMax}`)
  }
  if (thr !== null) parts.push(`threshold ${thr}`)
  return `${code} — ${parts.join(', ')}`
}

export default function SignalFunnelPanel() {
  const q = useQuery({
    queryKey: ['signal-funnel'],
    queryFn: () => tradingAPI.getSignalFunnel(),
    refetchInterval: 10000,
    staleTime: 8000,
  })

  const funnel = q.data?.funnel
  const stages = funnel?.stages || []
  const routing = funnel?.routing

  // Widest stage is the denominator for the bar widths. Using the first stage
  // would understate later stages if an earlier one was never instrumented.
  const maxEvaluated = stages.reduce((m, s) => Math.max(m, s.evaluated || 0), 0)

  return (
    <div data-testid="signal-funnel-panel" style={{ display: 'contents' }}>
      <TileState
        query={q}
        title="Signal Funnel"
        thresholdKey="signals"
        lastUpdatedAt={undefined}
        isEmpty={(d) => !d || !d.funnel}
      >
        <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700/50 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-200">Signal Funnel</h2>
            <span className="text-xs text-slate-500">
              since {funnel?.started_at ? new Date(funnel.started_at).toLocaleString() : '—'}
            </span>
          </div>

          <p className="text-xs text-slate-500 mb-4 leading-relaxed">
            Every stage in the live signal path, with the reason and the numbers
            behind each rejection. Counters are process-local and reset when the
            trading engine restarts.
          </p>
          <p className="text-xs text-amber-400/70 mb-4 leading-relaxed">
            This is <span className="font-medium">not</span> a single-denominator
            funnel. Aggregator stages are counted <em>per timeframe</em>
            {' '}(15m/60m/240m run separately, so ~3&times; the evaluations);
            everything else is per evaluation or per emitted signal. Each row
            shows its basis — compare a rate only against rows with the same one.
          </p>

          <div className="space-y-2">
            {stages.map((s) => {
              const width = maxEvaluated > 0 ? ((s.passed || 0) / maxEvaluated) * 100 : 0
              const reasons = Object.entries(s.rejection_reasons || {})
              const notes = Object.entries(s.notes || {})
              const dead = s.evaluated === 0
              return (
                <div
                  key={s.stage}
                  data-testid={`funnel-stage-${s.stage}`}
                  className={`rounded-md border px-3 py-2 ${
                    dead
                      ? 'border-slate-700/30 bg-slate-900/20'
                      : 'border-slate-700/50 bg-slate-900/40'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-xs font-medium ${dead ? 'text-slate-500' : 'text-slate-300'}`}>
                      {STAGE_LABELS[s.stage] || s.stage}
                      {s.advisory && (
                        <span className="ml-2 text-[10px] uppercase tracking-wider text-amber-400/80">
                          advisory · not a gate
                        </span>
                      )}
                      {s.basis && s.basis !== 'unknown' && (
                        <span className="ml-2 text-[10px] tracking-wide text-slate-600">
                          {s.basis.replace(/_/g, ' ')}
                        </span>
                      )}
                    </span>
                    <span className="text-xs font-mono text-slate-400 whitespace-nowrap">
                      {fmtNum(s.passed)} / {fmtNum(s.evaluated)} · {fmtPct(s.pass_rate_pct)}
                    </span>
                  </div>
                  <div className="w-full bg-slate-700/20 rounded-full h-1.5 overflow-hidden mt-1.5">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-teal-500 rounded-full transition-all duration-500"
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  {dead && (
                    <div className="text-[11px] text-slate-600 mt-1">
                      never reached — no evaluation got this far
                    </div>
                  )}
                  {reasons.length > 0 && (
                    <ul className="mt-1.5 space-y-0.5">
                      {reasons.map(([code, stat]) => (
                        <li key={code} className="text-[11px] text-rose-300/80 font-mono">
                          {reasonLine(code, stat)}
                        </li>
                      ))}
                    </ul>
                  )}
                  {notes.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {notes.map(([code, stat]) => (
                        <li key={code} className="text-[11px] text-amber-300/70 font-mono">
                          {reasonLine(code, stat)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>

          {routing && (
            <div className="mt-4 pt-3 border-t border-slate-700/30 text-xs text-slate-400 space-y-1">
              <div className="flex justify-between">
                <span>Routing branches</span>
                <span className="font-mono">
                  trend {fmtNum(routing.trend_following)} · mean-rev{' '}
                  {fmtNum(routing.mean_reversion)}
                  {routing.unknown > 0 && ` · unknown ${fmtNum(routing.unknown)}`}
                </span>
              </div>
              {routing.adx_distribution?.n > 0 && (
                <div className="flex justify-between">
                  <span>
                    ADX min / median / max
                    <span className="text-slate-600">
                      {' '}(recent {routing.adx_distribution.n.toLocaleString()} decisions)
                    </span>
                  </span>
                  <span className="font-mono">
                    {fmtVal(routing.adx_distribution.min)} /{' '}
                    {fmtVal(routing.adx_distribution.median)} /{' '}
                    {fmtVal(routing.adx_distribution.max)}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </TileState>
    </div>
  )
}
