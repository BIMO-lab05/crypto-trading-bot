import React from 'react'
import { Check, X, HelpCircle, Circle, CheckCircle2 } from 'lucide-react'
import { useLiveReadiness } from '../hooks/useLiveReadiness'
import { useCarryIns } from '../hooks/useCarryIns'
import TileState from './TileState'

/**
 * PathToLiveTile — Phase 10 DASHLIVE-01 + DASHLIVE-03 operator-visibility surface.
 *
 * Shows the 3-state LIVE-readiness banner (DO NOT FLIP / ALMOST / READY),
 * 6 PREFLIGHT check rows, 5 carry-in close-state rows, and a 24-hour
 * continuous-PASS window progress footer.
 *
 * Authority rule (D-10-16, load-bearing):
 *   carryInsQuery.data is the authoritative source for `overall`, `window`,
 *   and per-check detail rows (via the joined `.live_readiness` block).
 *   useLiveReadiness() serves as a fallback ONLY when
 *   carryInsQuery.data.live_readiness?.checks is absent (degraded payload).
 *   If the two queries disagree (race), useCarryIns wins.
 *
 * Security (T-10-02-02): all text content goes through JSX text interpolation.
 * React escapes by default. No raw-HTML injection props, no eval, no
 * direct DOM innerHTML writes. Description strings are operator-authored in
 * .planning/state/carry_ins.json and reviewed via git diff.
 *
 * Error handling (T-10-02-03): tile is wrapped in TileState; on isError
 * TileState renders Failed/Retry UI and children never render. All nested
 * field accesses use optional-chaining to prevent runtime errors on
 * degraded or partial payloads.
 *
 * Placement: Dashboard.jsx renders this as the FIRST child of the
 * min-h-screen wrapper, above KeyMetricsStrip per D-10-12.
 */

// ── Tailwind token maps (D-10-13, locked) ────────────────────────────────────

/** Banner background token by overall state. */
const BANNER_BG = {
  DO_NOT_FLIP: 'bg-rose-700',
  ALMOST: 'bg-amber-600',
  READY: 'bg-emerald-700',
}

/** Human-readable banner label. "DO_NOT_FLIP" → "DO NOT FLIP". */
const BANNER_LABEL = {
  DO_NOT_FLIP: 'DO NOT FLIP',
  ALMOST: 'ALMOST',
  READY: 'READY',
}

/** Status chip classes by check status. */
const CHIP_CLASSES = {
  PASS: 'bg-emerald-700/30 text-emerald-300',
  FAIL: 'bg-rose-700/30 text-rose-300',
  UNKNOWN: 'bg-slate-600/30 text-slate-300',
}

/** Carry-in chip classes by state. */
const CARRY_IN_CHIP_CLASSES = {
  open: 'bg-amber-600/30 text-amber-300',
  closed: 'bg-emerald-700/30 text-emerald-300',
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Format a duration in seconds as "HH:MM:SS".
 * Uses plain Math.floor — no moment/dayjs (CONTEXT.md "Specific Ideas").
 */
function fmtSeconds(s) {
  const sec = Math.max(0, Math.floor(s || 0))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const ss = sec % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** Status chip icon + label for a single PREFLIGHT check. */
function StatusChip({ status }) {
  const classes = CHIP_CLASSES[status] || CHIP_CLASSES.UNKNOWN
  const Icon =
    status === 'PASS' ? Check :
    status === 'FAIL' ? X :
    HelpCircle

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${classes}`}>
      <Icon size={10} />
      {status || 'UNKNOWN'}
    </span>
  )
}

/** Carry-in state chip. */
function CarryInChip({ state }) {
  const classes = CARRY_IN_CHIP_CLASSES[state] || CARRY_IN_CHIP_CLASSES.open
  const Icon = state === 'closed' ? CheckCircle2 : Circle

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${classes}`}>
      <Icon size={10} />
      {state || 'open'}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

function PathToLiveTile() {
  const liveReadinessQuery = useLiveReadiness()
  const carryInsQuery = useCarryIns()

  // Resolve per-check rows: prefer the joined block (carryInsQuery authoritative
  // per D-10-16), fall back to liveReadinessQuery for degraded payloads only.
  const checks =
    carryInsQuery.data?.live_readiness?.checks ||
    liveReadinessQuery.data?.checks ||
    []

  const carryIns = carryInsQuery.data?.carry_ins || []
  const overall = carryInsQuery.data?.overall || 'DO_NOT_FLIP'
  const window_ = carryInsQuery.data?.window || {}

  const bannerBg = BANNER_BG[overall] || BANNER_BG.DO_NOT_FLIP
  const bannerLabel = BANNER_LABEL[overall] || 'DO NOT FLIP'

  const elapsedSec = window_.elapsed_seconds || 0
  const requiredSec = window_.required_seconds || 86400

  return (
    <div data-testid="path-to-live-tile" className="w-full">
      <TileState
        query={carryInsQuery}
        thresholdKey="default"
        title="Path to LIVE"
        lastUpdatedAt={carryInsQuery.data?.evaluated_at}
        isEmpty={(data) => !data || !data.carry_ins}
      >
        {/* ── Banner ────────────────────────────────────────────────────────── */}
        <div
          data-testid="path-to-live-banner"
          className={`${bannerBg} px-5 py-3 rounded-t-lg`}
        >
          <div className="flex items-center justify-between">
            <div>
              <span
                className="text-white text-lg tracking-widest"
                style={{ fontWeight: overall === 'ALMOST' ? 600 : 700 }}
              >
                {bannerLabel}
              </span>
              {overall === 'ALMOST' && (
                <p className="text-white/80 text-xs mt-0.5">
                  All checks PASS — {fmtSeconds(elapsedSec)} of {fmtSeconds(requiredSec)} elapsed
                </p>
              )}
            </div>
            <span
              className="text-white/70 text-xs"
              style={{ fontFamily: 'Manrope, system-ui, sans-serif' }}
            >
              Path to LIVE
            </span>
          </div>
        </div>

        {/* ── Body ──────────────────────────────────────────────────────────── */}
        <div
          className="rounded-b-lg border border-slate-700/50 divide-y divide-slate-700/30"
          style={{ background: '#18181c' }}
        >
          {/* PREFLIGHT Checks section */}
          <div className="px-5 pt-3 pb-1">
            <p
              className="text-[9px] uppercase tracking-[0.18em] mb-2"
              style={{ color: '#65645e', fontWeight: 600 }}
            >
              PREFLIGHT checks
            </p>
            <div className="space-y-1.5">
              {checks.map((chk) => (
                <div
                  key={chk.check}
                  data-testid={`path-to-live-check-${chk.check}`}
                  className="flex flex-col md:flex-row md:flex-wrap md:items-center gap-1 md:gap-3 py-0.5"
                >
                  <span
                    className="w-full md:w-28 md:shrink-0 text-xs"
                    style={{
                      color: '#a09e98',
                      fontFamily: 'JetBrains Mono, monospace',
                    }}
                  >
                    {chk.check}
                  </span>
                  <StatusChip status={chk.status} />
                  <span
                    className="text-xs truncate"
                    style={{ color: '#65645e', fontFamily: 'JetBrains Mono, monospace' }}
                  >
                    {chk.detail}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Carry-ins section */}
          <div className="px-5 pt-3 pb-1">
            <p
              className="text-[9px] uppercase tracking-[0.18em] mb-2"
              style={{ color: '#65645e', fontWeight: 600 }}
            >
              Carry-ins
            </p>
            <div className="space-y-1.5">
              {carryIns.map((ci) => (
                <div
                  key={ci.id}
                  data-testid={`path-to-live-carry-in-${ci.id}`}
                  className="flex flex-col md:flex-row md:flex-wrap md:items-center gap-1 md:gap-3 py-0.5"
                >
                  <span
                    className="w-full md:w-20 md:shrink-0 text-xs font-semibold"
                    style={{
                      color: '#a09e98',
                      fontFamily: 'JetBrains Mono, monospace',
                    }}
                  >
                    {ci.id}
                  </span>
                  <CarryInChip state={ci.state} />
                  <span
                    className="text-xs truncate"
                    style={{ color: '#65645e', fontFamily: 'Manrope, system-ui, sans-serif' }}
                  >
                    {ci.description}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* 24h continuous-PASS window footer */}
          <div className="px-5 py-2.5 flex items-center gap-3">
            <span
              className="text-[9px] uppercase tracking-[0.18em]"
              style={{ color: '#65645e', fontWeight: 600 }}
            >
              24h continuous-PASS window
            </span>
            <span
              className="text-xs tabular-nums"
              style={{
                color: '#a09e98',
                fontFamily: 'JetBrains Mono, monospace',
              }}
            >
              {fmtSeconds(elapsedSec)} / {fmtSeconds(requiredSec)}
            </span>
          </div>
        </div>
      </TileState>
    </div>
  )
}

export default PathToLiveTile
