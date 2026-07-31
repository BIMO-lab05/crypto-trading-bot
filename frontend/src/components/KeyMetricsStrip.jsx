import React from 'react'
import { usePositions, useTradingStatus, usePerformance } from '../hooks/usePositions'
import TileState from './TileState'
import { toFiniteNumber, PAPER_DEFAULT_BALANCE } from '../utils/balance'

/**
 * KeyMetricsStrip — Editorial Trading Floor metric strip.
 *
 * UPDATED 2026-05-14 (Plan 06-05, DASH-05): wrapped in <TileState/> per
 * audit verdict FIXED. The load-bearing query is `usePerformance` (per
 * 06-TILE-AUDIT.md). Loading/error/empty states surface through the
 * shared wrapper; the existing per-cell `isLoading` skeleton is kept as
 * a fallback for the partial-data path (positions hydrate before
 * performance metrics on a cold cache).
 *
 * Replaces the prior cyan-slate gradient with the warm off-black /
 * viridian-teal / warm-rose palette already used by the Performance
 * dashboard (see pages/performance-theme.css). Same data source, same
 * hooks; only typography + colour are reworked.
 *
 * Layout: asymmetric. The hero balance cell spans two columns and is
 * set in Fraunces display weight; supporting cells use JetBrains Mono
 * with tabular figures so digits don't dance on refresh.
 */

const formatCurrency = (value, showSign = false) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '$0.00'
  const v = Number(value)
  const formatted = Math.abs(v).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  if (showSign && v !== 0) return v >= 0 ? `+${formatted}` : `−${formatted}`
  return formatted
}

const formatPercent = (value, showSign = false) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '0.00%'
  const v = Number(value)
  const formatted = `${Math.abs(v).toFixed(2)}%`
  if (showSign && v !== 0) return v >= 0 ? `+${formatted}` : `−${formatted}`
  return formatted
}

// Color tokens lifted from performance-theme.css. Inlined for components
// outside .perf-page where the CSS variables aren't in scope.
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

const tone = (trend) => {
  if (trend === 'positive') return C.gain
  if (trend === 'negative') return C.loss
  if (trend === 'gold') return C.gold
  return C.text
}

// Phase 14 CR-02 fix: derive a stable per-cell testid from the eyebrow
// label so test_key_metrics_2col can probe the real metric cells via
// `[data-testid^="metric-"]` instead of falling back to opaque children
// of a `display:contents` wrapper (which yielded one vacuously-passing
// row). Lowercase + non-alphanum -> hyphen + strip leading/trailing
// hyphens. Same shape Tailwind's `kebab-case` utility uses.
const slugifyEyebrow = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

/**
 * Cell — single metric tile. Hero variant gets larger display type
 * and corner-tick decoration.
 */
const Cell = ({ eyebrow, value, sub, trend, hero = false, isLoading = false }) => {
  const valueColor = tone(trend)
  return (
    <div
      data-testid={`metric-${slugifyEyebrow(eyebrow)}`}
      className="relative px-5 py-4"
      style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 4,
        gridColumn: hero ? 'span 2' : undefined,
      }}
    >
      {/* Editorial corner ticks */}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute', top: -1, left: -1, width: 8, height: 8,
          borderTop: `1px solid ${C.text3}`, borderLeft: `1px solid ${C.text3}`,
        }}
      />
      <span
        aria-hidden="true"
        style={{
          position: 'absolute', bottom: -1, right: -1, width: 8, height: 8,
          borderBottom: `1px solid ${C.text3}`, borderRight: `1px solid ${C.text3}`,
        }}
      />

      <div
        className="text-[10px] uppercase mb-2"
        style={{
          color: C.text3,
          letterSpacing: '0.18em',
          fontWeight: 600,
          fontFamily: 'Manrope, system-ui, sans-serif',
        }}
      >
        {eyebrow}
      </div>

      {isLoading ? (
        <div className="space-y-1.5">
          <div className="h-7 rounded" style={{ background: C.surface2, width: hero ? '70%' : '60%' }} />
          <div className="h-3 rounded" style={{ background: C.surface2, width: '40%' }} />
        </div>
      ) : (
        <>
          <div
            style={{
              color: valueColor,
              fontFamily: hero ? 'Fraunces, "Iowan Old Style", Georgia, serif' : 'JetBrains Mono, monospace',
              fontVariationSettings: hero ? '"opsz" 144' : undefined,
              fontWeight: hero ? 500 : 600,
              fontSize: hero ? 36 : 22,
              lineHeight: 1,
              letterSpacing: hero ? '-0.025em' : '0.01em',
              fontFeatureSettings: '"tnum" 1, "zero" 1',
            }}
          >
            {value}
          </div>
          {sub && (
            <div
              className="mt-1.5"
              style={{
                color: C.text3,
                fontSize: 11,
                fontFamily: 'JetBrains Mono, monospace',
                letterSpacing: '0.02em',
              }}
            >
              {sub}
            </div>
          )}
        </>
      )}
    </div>
  )
}

const StatusDot = ({ tone: t }) => (
  <span
    aria-hidden="true"
    className="inline-block rounded-full"
    style={{
      width: 8, height: 8, background: t,
      boxShadow: `0 0 8px ${t}80`,
      animation: 'kms-breath 1.6s ease-in-out infinite',
    }}
  />
)

export default function KeyMetricsStrip() {
  // Performance is the load-bearing tile-shape gate per 06-TILE-AUDIT.md
  // (DASH-01). Treat it as the TileState `query`; the secondary hooks
  // (positions/status) carry their own caches and partial-data UX.
  const perfQuery = usePerformance()
  const { data: positionsData, isLoading: positionsLoading, isError: positionsError } = usePositions()
  const { data: statusData } = useTradingStatus()
  const { data: performanceData, isLoading: performanceLoading, isError: performanceError } = perfQuery

  const isApiDegraded = positionsError || performanceError
  const positions = positionsData?.positions || []
  const metrics = performanceData?.metrics || {}
  const status = statusData?.status || {}

  const unrealizedPnL = positions.reduce((t, p) => t + parseFloat(p.unrealized_pnl || 0), 0)
  const portfolioLoading = positionsLoading || performanceLoading

  // Shared with PortfolioCard so the two tiles cannot disagree on the same field.
  const totalBalance = toFiniteNumber(
    metrics.current_balance,
    toFiniteNumber(metrics.initial_balance, PAPER_DEFAULT_BALANCE),
  )
  const realizedPnL = parseFloat(metrics.realized_pnl) || 0
  const currentDrawdown = parseFloat(metrics.max_drawdown) || 0
  const winRate = parseFloat(metrics.win_rate) || 0
  const openPositions = positions.length
  const totalTrades = parseInt(metrics.total_trades) || 0
  const roi = parseFloat(metrics.roi) || 0
  const strategyMode = status.strategy_mode || 'ensemble'
  const isRunning = !!status.is_running
  const emergency = !!status.emergency_stop?.active

  const pnlPercent = totalBalance > 0 ? (unrealizedPnL / totalBalance) * 100 : 0

  let stateLabel = 'idle'
  let stateColor = C.text3
  if (emergency) { stateLabel = 'halted'; stateColor = C.loss }
  else if (isApiDegraded) { stateLabel = 'degraded'; stateColor = C.gold }
  else if (isRunning) { stateLabel = 'live'; stateColor = C.gain }

  return (
    // Phase 14 CR-02 fix: previously the outer wrapper carried both the
    // `data-testid="key-metrics-strip"` attribute AND `display:contents`,
    // which made `getBoundingClientRect()` return 0x0 and silently
    // defeated test_dashboard_single_column_mobile + test_key_metrics_2col.
    // The testid now lives on the real layout box (the inner div that IS
    // the visual strip), so width-vs-viewport assertions resolve against
    // a real bbox.
    <TileState
      query={perfQuery}
      title="Key Metrics"
      thresholdKey="performance"
      lastUpdatedAt={undefined}
      isEmpty={(d) => !d || !d.metrics || Object.keys(d.metrics).length === 0}
    >
    <div
      data-testid="key-metrics-strip"
      style={{
        background: C.bg,
        borderBottom: `1px solid ${C.border}`,
        fontFamily: 'Manrope, system-ui, sans-serif',
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
        {/* Editorial header strip — eyebrow + hairline + state */}
        <div className="flex items-end justify-between mb-4 gap-4">
          <div className="flex items-baseline gap-3 min-w-0">
            <span
              className="uppercase"
              style={{
                color: C.text3,
                fontSize: 10,
                letterSpacing: '0.22em',
                fontWeight: 600,
              }}
            >
              At a Glance
            </span>
            <span
              className="hidden sm:inline italic truncate"
              style={{
                color: C.text2,
                fontFamily: 'Fraunces, serif',
                fontVariationSettings: '"opsz" 36',
                fontSize: 14,
                letterSpacing: 0,
              }}
            >
              Paper trading · {strategyMode}
            </span>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <StatusDot tone={stateColor} />
            <span
              className="uppercase"
              style={{
                color: stateColor,
                fontSize: 10,
                letterSpacing: '0.22em',
                fontWeight: 700,
              }}
            >
              {stateLabel}
            </span>
            <span
              className="hidden md:inline"
              style={{
                color: C.text3,
                fontSize: 10,
                letterSpacing: '0.18em',
                fontFamily: 'JetBrains Mono, monospace',
              }}
            >
              {new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>
        </div>

        {/* Hairline rule */}
        <div
          aria-hidden="true"
          style={{
            height: 1,
            marginBottom: 16,
            background: `linear-gradient(90deg, transparent, ${C.borderStrong} 20%, ${C.borderStrong} 80%, transparent)`,
          }}
        />

        {/* Asymmetric metric grid: hero balance spans 2 cols on lg+ */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3">
          <Cell
            eyebrow="Total Balance"
            value={formatCurrency(totalBalance)}
            sub={`ROI ${roi >= 0 ? '+' : '−'}${Math.abs(roi).toFixed(2)}%`}
            trend={roi >= 0 ? 'positive' : 'negative'}
            hero
            isLoading={portfolioLoading}
          />
          <Cell
            eyebrow="Unrealized P&L"
            value={formatCurrency(unrealizedPnL, true)}
            sub={formatPercent(pnlPercent, true)}
            trend={unrealizedPnL >= 0 ? 'positive' : 'negative'}
            isLoading={portfolioLoading}
          />
          <Cell
            eyebrow="Realized P&L"
            value={formatCurrency(realizedPnL, true)}
            sub="Closed positions"
            trend={realizedPnL >= 0 ? 'positive' : 'negative'}
            isLoading={portfolioLoading}
          />
          <Cell
            eyebrow="Drawdown"
            value={formatPercent(Math.abs(currentDrawdown))}
            sub="From peak equity"
            trend={Math.abs(currentDrawdown) <= 5 ? 'positive' : 'negative'}
            isLoading={portfolioLoading}
          />
          <Cell
            eyebrow="Win Rate"
            value={formatPercent(winRate)}
            sub={`${totalTrades} total trades`}
            trend={winRate >= 50 ? 'positive' : winRate > 0 ? undefined : 'negative'}
            isLoading={portfolioLoading}
          />
          <Cell
            eyebrow="Open Positions"
            value={openPositions.toString().padStart(2, '0')}
            sub="Active exposure"
            trend={openPositions > 0 ? 'gold' : undefined}
            isLoading={portfolioLoading}
          />
        </div>
      </div>

      <style>{`
        @keyframes kms-breath {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%      { opacity: 0.55; transform: scale(0.9); }
        }
      `}</style>
    </div>
    </TileState>
  )
}
