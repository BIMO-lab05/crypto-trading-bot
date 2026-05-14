import React from 'react'
import { useTradingStatus, usePositions } from '../hooks/usePositions'
import { usePortfolio } from '../hooks/usePortfolio'
import { useSafetyState } from '../hooks/useSafetyState'

/**
 * StatusBar — fixed-bottom live state strip.
 *
 * Editorial Trading Floor aesthetic. Live cells:
 *   1. Trading-loop state (running / idle, with breath pulse)
 *   2. Signals checked (lifetime)
 *   3. Trades executed (lifetime)
 *   4. Open positions
 *   5. Cash balance + total P&L
 *   6. MODE pill (PAPER green / LIVE red) — D-05/D-06
 *   7. KILL-SWITCH ARMED / TRIPPED — D-04/D-05
 *   8. ML toggle ON / OFF — D-05
 *   9. EMERGENCY active+mtime / inactive — D-07
 *
 * The breath dot uses a CSS animation so we get pulse without re-render.
 * Refreshes follow the underlying hook polling cadence (5–10s);
 * useSafetyState polls /api/config/safety-state every 5s per D-11.
 */

const fmt = (n, d = 2) => {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
}

const Cell = ({ eyebrow, value, valueStyle, accent, mono = true, testId }) => (
  <div
    className="flex flex-col gap-0.5 px-4 py-1.5 min-w-0"
    style={{ borderRight: '1px solid #2a2a32' }}
    data-testid={testId}
  >
    <span
      className="text-[9px] uppercase tracking-[0.18em] truncate"
      style={{ color: '#65645e', fontWeight: 600 }}
    >
      {eyebrow}
    </span>
    <span
      className="text-xs truncate"
      style={{
        color: accent || '#f5f3ee',
        fontFamily: mono ? 'JetBrains Mono, monospace' : 'Manrope, system-ui, sans-serif',
        fontFeatureSettings: '"tnum" 1',
        ...valueStyle,
      }}
    >
      {value}
    </span>
  </div>
)

// Format an ISO timestamp as "HH:MM:SS" in UTC, or return null if invalid.
const fmtMtime = (iso) => {
  if (!iso) return null
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return null
    return d.toLocaleTimeString('en-GB', { hour12: false, timeZone: 'UTC' })
  } catch {
    return null
  }
}

export default function StatusBar() {
  const { data: tradingStatus } = useTradingStatus()
  const { data: positions } = usePositions()
  const { data: portfolio } = usePortfolio()
  const { data: safety } = useSafetyState()

  // Safety state derivations (D-05 / D-06 / D-07).
  // Defaults match the safe PAPER posture when safety-state is loading or unreachable.
  const tradingMode = safety?.trading_mode || 'PAPER'
  const killSwitchTripped = !!safety?.kill_switch?.tripped
  const mlOn = !!safety?.ml_predictions_enabled
  const emergencyActive = !!safety?.emergency_stop?.active
  const emergencyMtime = fmtMtime(safety?.emergency_stop?.mtime)
  const emergencyValue = emergencyActive
    ? emergencyMtime
      ? `ACTIVE — since ${emergencyMtime}`
      : 'ACTIVE'
    : 'INACTIVE'
  const emergencyAccent = emergencyActive ? '#fb7185' : '#a09e98'
  const modeAccent = tradingMode === 'LIVE' ? '#fb7185' : '#5eead4'
  const killSwitchAccent = killSwitchTripped ? '#fb7185' : '#a09e98'
  const mlAccent = mlOn ? '#d4af6a' : '#65645e'

  const status = tradingStatus?.status
  const isRunning = !!status?.is_running
  const emergency = emergencyActive || !!status?.emergency_stop?.active
  const signalsChecked = status?.total_signals_checked ?? 0
  const tradesExec = status?.total_trades_executed ?? 0

  const openCount = Array.isArray(positions?.positions) ? positions.positions.length : 0
  // /api/portfolio wraps payload in `portfolio: {}` ; /api/portfolio/balance returns flat.
  // Accept both shapes so the bar reads correctly regardless of which hook ran first.
  const portfolioInner = portfolio?.portfolio || portfolio
  const cash = portfolioInner?.cash_balance ?? portfolioInner?.total_value ?? 0
  const totalPnl = Number(portfolioInner?.total_pnl ?? 0)
  const pnlAccent = totalPnl > 0 ? '#5eead4' : totalPnl < 0 ? '#fb7185' : '#a09e98'
  const pnlSign = totalPnl > 0 ? '+' : totalPnl < 0 ? '−' : '·'
  const pnlAbs = Math.abs(totalPnl)

  let runState = 'idle'
  let runColor = '#a09e98'
  if (emergency) { runState = 'halted'; runColor = '#fb7185' }
  else if (isRunning) { runState = 'live'; runColor = '#5eead4' }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Trading bot live status"
      data-testid="statusbar"
      className="fixed bottom-0 left-0 right-0 z-30"
      style={{
        background: '#0a0a0b',
        borderTop: '1px solid #2a2a32',
        fontFamily: 'Manrope, system-ui, sans-serif',
        height: 38,
      }}
    >
      <div className="max-w-[1600px] mx-auto h-full flex items-stretch overflow-x-auto">
        {/* State pill — leftmost, prominent */}
        <div
          className="flex items-center gap-2 px-4 flex-shrink-0"
          style={{ borderRight: '1px solid #2a2a32' }}
          data-testid="statusbar-trading-state"
        >
          <span
            className="inline-block rounded-full"
            style={{
              width: 8,
              height: 8,
              background: runColor,
              boxShadow: `0 0 8px ${runColor}80`,
              animation: isRunning && !emergency ? 'sb-breath 1.6s ease-in-out infinite' : 'none',
            }}
            aria-hidden="true"
          />
          <span
            className="text-[10px] uppercase tracking-[0.2em] font-semibold"
            style={{ color: runColor }}
          >
            {runState}
          </span>
          <span
            className="text-[9px] uppercase tracking-[0.18em] hidden sm:inline"
            style={{ color: '#65645e' }}
          >
            {status?.strategy_mode || 'ensemble'}
          </span>
        </div>

        <Cell eyebrow="Signals" value={fmt(signalsChecked, 0)} />
        <Cell eyebrow="Trades" value={fmt(tradesExec, 0)} />
        <Cell eyebrow="Open" value={fmt(openCount, 0)} accent={openCount > 0 ? '#d4af6a' : undefined} />
        <Cell
          eyebrow="Cash"
          value={`$${fmt(cash, 2)}`}
        />
        <Cell
          eyebrow="P&L"
          value={`${pnlSign} $${fmt(pnlAbs, 2)}`}
          accent={pnlAccent}
        />

        {/* D-05/D-06: trading mode pill (PAPER green / LIVE red) */}
        <Cell
          eyebrow="MODE"
          value={tradingMode}
          accent={modeAccent}
          mono={false}
          testId="statusbar-mode"
        />

        {/* D-04/D-05: 5%-daily-loss kill-switch state */}
        <Cell
          eyebrow="KILL-SWITCH"
          value={killSwitchTripped ? 'TRIPPED' : 'ARMED'}
          accent={killSwitchAccent}
          testId="statusbar-kill-switch"
        />

        {/* D-05: ML predictions feature flag */}
        <Cell
          eyebrow="ML"
          value={mlOn ? 'ON' : 'OFF'}
          accent={mlAccent}
          testId="statusbar-ml"
        />

        {/* D-07: EMERGENCY_STOP file Active/Inactive + mtime (HH:MM:SS UTC) */}
        <Cell
          eyebrow="EMERGENCY"
          value={emergencyValue}
          accent={emergencyAccent}
          mono={false}
          testId="statusbar-emergency-stop"
        />

        <div className="flex-1" />

        {/* Right anchor: keyboard hint */}
        <div className="hidden md:flex items-center gap-3 px-4" style={{ borderLeft: '1px solid #2a2a32' }}>
          <span className="text-[9px] uppercase tracking-[0.18em]" style={{ color: '#65645e' }}>
            Press
          </span>
          <kbd
            className="px-1.5 py-0.5 rounded text-[10px]"
            style={{ background: '#1f1f24', color: '#a09e98', fontFamily: 'JetBrains Mono, monospace' }}
          >
            ⌘K
          </kbd>
        </div>
      </div>

      <style>{`
        @keyframes sb-breath {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.55; transform: scale(0.9); }
        }
      `}</style>
    </div>
  )
}
