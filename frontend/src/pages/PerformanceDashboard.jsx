/**
 * PerformanceDashboard.jsx — Editorial trading floor redesign.
 *
 * Aesthetic direction: warm off-black with viridian-teal gain / warm
 * rose loss accents (deliberately not the generic emerald/red),
 * Fraunces display + Manrope body + JetBrains Mono numbers. Asymmetric
 * grid: hero P&L is the visual anchor; risk metrics column stacks to
 * the right; the equity curve runs edge-to-edge below as the page's
 * primary visual.
 *
 * Theme is scoped to `.perf-page` via performance-theme.css so the
 * existing slate/cyan look on other pages is untouched.
 *
 * Renders directly with recharts — does not import the legacy
 * `components/performance/*` chart wrappers, which were styled for
 * the old aesthetic and would clash here. The legacy components
 * remain in place for any other consumers; this page just doesn't
 * use them.
 *
 * Replaces the prior dual PerformanceDashboard.jsx /
 * PerformanceDashboardEnhanced.jsx pages — the audit found those were
 * near-duplicates. Enhanced is removed in this commit.
 */

import React, { useState, useMemo, useEffect, useRef } from 'react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { RefreshCw, ArrowUpRight, ArrowDownRight, Activity } from 'lucide-react'
import { format } from 'date-fns'

import {
  usePerformanceMetrics,
  useCorrelationMatrix,
} from '../hooks/usePerformanceMetrics'
import './performance-theme.css'

// ────────────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────────────

const PERIODS = [
  { value: '1d', label: '24H' },
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: 'all', label: 'ALL' },
]

const CORRELATION_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT']

// ────────────────────────────────────────────────────────────────────
// Formatting helpers
// ────────────────────────────────────────────────────────────────────

const fmtUSD = (n, sign = false) => {
  if (n == null || Number.isNaN(n)) return '—'
  const abs = Math.abs(n)
  const formatted = abs.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  if (sign) return `${n >= 0 ? '+' : '−'}$${formatted}`
  return `${n < 0 ? '−' : ''}$${formatted}`
}

const fmtNumber = (n, dp = 2) => {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  })
}

const fmtPct = (n, dp = 2, sign = false) => {
  if (n == null || Number.isNaN(n)) return '—'
  const formatted = Math.abs(n).toFixed(dp)
  if (sign) return `${n >= 0 ? '+' : '−'}${formatted}%`
  return `${n < 0 ? '−' : ''}${formatted}%`
}

// ────────────────────────────────────────────────────────────────────
// AnimatedNumber — tweens to the new value over ~700ms.
// Used only on the hero P&L; lesser metrics update instantly.
// ────────────────────────────────────────────────────────────────────

function AnimatedNumber({ value, render }) {
  const [displayed, setDisplayed] = useState(value ?? 0)
  const fromRef = useRef(value ?? 0)
  const startRef = useRef(null)

  useEffect(() => {
    if (value == null || Number.isNaN(value)) {
      setDisplayed(value ?? 0)
      return
    }
    const from = fromRef.current
    const to = value
    if (from === to) return
    const duration = 700
    let raf
    const step = (ts) => {
      if (startRef.current == null) startRef.current = ts
      const t = Math.min(1, (ts - startRef.current) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      const v = from + (to - from) * eased
      setDisplayed(v)
      if (t < 1) raf = requestAnimationFrame(step)
      else {
        fromRef.current = to
        startRef.current = null
      }
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value])

  return render(displayed)
}

// ────────────────────────────────────────────────────────────────────
// Header — sticky bar with date, refresh, period pills.
// ────────────────────────────────────────────────────────────────────

function PerfHeader({ period, onPeriodChange, onRefresh, isLoading, lastUpdated }) {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 40,
        background: 'rgba(10, 10, 11, 0.86)',
        backdropFilter: 'blur(14px)',
        borderBottom: '1px solid var(--perf-border)',
      }}
    >
      <div className="px-6 py-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="flex items-baseline gap-4">
          <span className="perf-eyebrow">Performance</span>
          <span
            className="perf-mono"
            style={{ color: 'var(--perf-text-3)', fontSize: '0.6875rem', letterSpacing: '0.08em' }}
          >
            {format(new Date(), "yyyy-MM-dd · HH:mm 'UTC'")}
          </span>
        </div>

        <div className="flex items-center gap-4">
          <div
            className="flex"
            style={{
              border: '1px solid var(--perf-border)',
              borderRadius: 4,
              overflow: 'hidden',
            }}
          >
            {PERIODS.map((p) => (
              <button
                key={p.value}
                className="perf-pill"
                data-active={period === p.value}
                onClick={() => onPeriodChange(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            title="Refresh"
            className="perf-mono"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.4375rem 0.75rem',
              background: 'transparent',
              color: 'var(--perf-text-2)',
              border: '1px solid var(--perf-border)',
              borderRadius: 4,
              fontSize: '0.6875rem',
              letterSpacing: '0.06em',
              cursor: isLoading ? 'wait' : 'pointer',
              opacity: isLoading ? 0.5 : 1,
            }}
          >
            <RefreshCw size={11} className={isLoading ? 'animate-spin' : ''} />
            REFRESH
          </button>
        </div>
      </div>
    </header>
  )
}

// ────────────────────────────────────────────────────────────────────
// HeroPnL — the visual anchor. Big serif number; period meta below.
// ────────────────────────────────────────────────────────────────────

function HeroPnL({ totalPnL, equityCurve, period, tradeCount }) {
  const isGain = (totalPnL ?? 0) >= 0
  const colorVar = isGain ? 'var(--perf-gain)' : 'var(--perf-loss)'

  // Compute % change vs starting equity if we have curve data.
  const pctChange = useMemo(() => {
    if (!equityCurve || equityCurve.length < 2) return null
    const start = equityCurve[0]?.equity
    const end = equityCurve[equityCurve.length - 1]?.equity
    if (!start || !end || start === 0) return null
    return ((end - start) / start) * 100
  }, [equityCurve])

  const PERIOD_LABEL = useMemo(() => {
    const found = PERIODS.find((p) => p.value === period)
    return found?.label ?? period
  }, [period])

  return (
    <div className="perf-reveal perf-reveal-1" style={{ position: 'relative' }}>
      <div className="perf-eyebrow" style={{ marginBottom: '1.25rem' }}>
        Net P&amp;L · {PERIOD_LABEL}
      </div>

      <div className="flex items-baseline gap-4 flex-wrap">
        <span
          className="perf-display perf-mono"
          style={{
            color: colorVar,
            fontSize: 'clamp(3.5rem, 9vw, 7.5rem)',
            fontFamily: 'var(--perf-font-display)',
            fontVariationSettings: "'opsz' 144",
            fontWeight: 600,
          }}
        >
          {totalPnL == null ? (
            <span className="perf-skeleton" style={{ display: 'inline-block', width: '8em', height: '0.85em' }} />
          ) : (
            <AnimatedNumber
              value={totalPnL}
              render={(v) => (
                <>
                  {v < 0 ? '−' : ''}
                  <span style={{ fontWeight: 400, opacity: 0.55 }}>$</span>
                  {Math.abs(v).toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </>
              )}
            />
          )}
        </span>

        {pctChange != null && (
          <span
            className="perf-mono"
            style={{
              color: pctChange >= 0 ? 'var(--perf-gain)' : 'var(--perf-loss)',
              fontSize: '0.875rem',
              fontWeight: 600,
              letterSpacing: '0.04em',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.3rem',
              padding: '0.25rem 0.625rem',
              background: pctChange >= 0 ? 'var(--perf-gain-soft)' : 'var(--perf-loss-soft)',
              borderRadius: 999,
            }}
          >
            {pctChange >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
            {fmtPct(pctChange, 2, true)}
          </span>
        )}
      </div>

      <div
        className="perf-text-soft"
        style={{
          marginTop: '1rem',
          fontSize: '0.875rem',
          maxWidth: '36rem',
          lineHeight: 1.55,
        }}
      >
        Realized profit and loss over the past{' '}
        <span style={{ color: 'var(--perf-text)' }}>{PERIOD_LABEL.toLowerCase()}</span>
        {tradeCount > 0 ? (
          <>
            {' '}across{' '}
            <span className="perf-mono" style={{ color: 'var(--perf-text)' }}>
              {tradeCount}
            </span>{' '}
            closed trades.
          </>
        ) : (
          <> — no closed trades in this window yet.</>
        )}
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// MetricRow — single row in the right-hand risk metrics stack.
// ────────────────────────────────────────────────────────────────────

function MetricRow({ label, value, accent, sub }) {
  return (
    <div
      className="flex items-baseline justify-between"
      style={{
        padding: '0.875rem 0',
        borderBottom: '1px solid var(--perf-border)',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
        <span className="perf-eyebrow" style={{ letterSpacing: '0.14em' }}>
          {label}
        </span>
        {sub && (
          <span style={{ fontSize: '0.6875rem', color: 'var(--perf-text-3)' }}>{sub}</span>
        )}
      </div>
      <span
        className="perf-mono"
        style={{
          fontSize: '1.0625rem',
          fontWeight: 500,
          color: accent ?? 'var(--perf-text)',
          letterSpacing: '-0.01em',
        }}
      >
        {value}
      </span>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// RiskMetricsColumn — stack of secondary metrics next to the hero.
// ────────────────────────────────────────────────────────────────────

function RiskMetricsColumn({ metrics, isLoading }) {
  const m = metrics ?? {}
  const sharpeColor =
    m.sharpeRatio == null ? 'var(--perf-text)'
    : m.sharpeRatio >= 1 ? 'var(--perf-gain)'
    : m.sharpeRatio >= 0 ? 'var(--perf-text)'
    : 'var(--perf-loss)'
  const ddColor =
    m.maxDrawdownPercent == null ? 'var(--perf-text)'
    : m.maxDrawdownPercent <= 5 ? 'var(--perf-gain)'
    : m.maxDrawdownPercent <= 15 ? 'var(--perf-text)'
    : 'var(--perf-loss)'
  const winColor =
    m.winRate == null ? 'var(--perf-text)'
    : m.winRate >= 55 ? 'var(--perf-gain)'
    : m.winRate >= 45 ? 'var(--perf-text)'
    : 'var(--perf-loss)'

  return (
    <div className="perf-card perf-corner-ticks perf-reveal perf-reveal-2" style={{ padding: '0.75rem 1.25rem' }}>
      <MetricRow
        label="Sharpe Ratio"
        sub="excess return ÷ vol"
        value={isLoading ? '…' : fmtNumber(m.sharpeRatio, 2)}
        accent={sharpeColor}
      />
      <MetricRow
        label="Sortino Ratio"
        sub="downside-only Sharpe"
        value={isLoading ? '…' : fmtNumber(m.sortinoRatio, 2)}
      />
      <MetricRow
        label="Max Drawdown"
        sub="peak → trough"
        value={isLoading ? '…' : fmtPct(m.maxDrawdownPercent, 2)}
        accent={ddColor}
      />
      <MetricRow
        label="Win Rate"
        sub={`${m.winningTrades ?? 0}W / ${m.losingTrades ?? 0}L`}
        value={isLoading ? '…' : fmtPct(m.winRate, 1)}
        accent={winColor}
      />
      <MetricRow
        label="Profit Factor"
        sub="gross win ÷ gross loss"
        value={isLoading ? '…' : fmtNumber(m.profitFactor, 2)}
      />
      <MetricRow
        label="VaR (95%)"
        sub="value at risk"
        value={isLoading ? '…' : fmtUSD(m.var95)}
      />
      <MetricRow
        label="CVaR (95%)"
        sub="expected shortfall"
        value={isLoading ? '…' : fmtUSD(m.cvar95)}
      />
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// SectionHeader — editorial frame for each lower section.
// ────────────────────────────────────────────────────────────────────

function SectionHeader({ index, title, sub }) {
  return (
    <div className="flex items-end justify-between" style={{ marginBottom: '1.25rem' }}>
      <div>
        <div className="perf-eyebrow">No. {String(index).padStart(2, '0')}</div>
        <h2 className="perf-section-title" style={{ marginTop: '0.35rem' }}>
          {title}
        </h2>
        {sub && (
          <p
            className="perf-text-soft"
            style={{ marginTop: '0.5rem', fontSize: '0.875rem', maxWidth: '34rem' }}
          >
            {sub}
          </p>
        )}
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// EquityCurvePanel — full-width recharts area chart.
// ────────────────────────────────────────────────────────────────────

function EquityTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  const equity = d?.equity ?? 0
  const pnl = d?.pnl ?? 0
  return (
    <div
      style={{
        background: 'var(--perf-bg-elev)',
        border: '1px solid var(--perf-border-strong)',
        borderRadius: 4,
        padding: '0.625rem 0.875rem',
        fontFamily: 'var(--perf-font-mono)',
        fontSize: 11,
        color: 'var(--perf-text)',
        minWidth: 180,
      }}
    >
      <div style={{ color: 'var(--perf-text-3)', marginBottom: 4, letterSpacing: '0.04em' }}>
        {d?.timestamp ? format(new Date(d.timestamp), 'yyyy-MM-dd HH:mm') : '—'}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ color: 'var(--perf-text-2)' }}>EQUITY</span>
        <span>{fmtUSD(equity)}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
        <span style={{ color: 'var(--perf-text-2)' }}>TRADE P&amp;L</span>
        <span style={{ color: pnl >= 0 ? 'var(--perf-gain)' : 'var(--perf-loss)' }}>
          {fmtUSD(pnl, true)}
        </span>
      </div>
    </div>
  )
}

function EquityCurvePanel({ data, isLoading }) {
  const empty = !data || data.length < 2
  const start = data?.[0]?.equity ?? 0
  return (
    <div
      className="perf-card perf-corner-ticks perf-reveal perf-reveal-3"
      style={{ padding: '1.25rem 1.25rem 0.5rem 1.25rem' }}
    >
      <div className="flex items-baseline justify-between" style={{ marginBottom: '0.75rem' }}>
        <span className="perf-eyebrow">Equity Trajectory</span>
        {!empty && (
          <span className="perf-mono" style={{ color: 'var(--perf-text-3)', fontSize: 11 }}>
            {data.length} points
          </span>
        )}
      </div>

      {empty ? (
        <EmptyChart
          height={340}
          message={
            isLoading
              ? 'Pulling equity points…'
              : 'Equity trajectory appears once at least two trades have closed.'
          }
        />
      ) : (
        <div style={{ height: 340 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 8, left: 8, bottom: 6 }}>
              <defs>
                <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--perf-gain)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--perf-gain)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--perf-grid)" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(t) => format(new Date(t), 'MMM d')}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
                axisLine={false}
                tickLine={false}
                width={60}
              />
              <Tooltip content={<EquityTooltip />} cursor={{ stroke: 'var(--perf-border-strong)', strokeDasharray: '3 3' }} />
              <ReferenceLine y={start} stroke="var(--perf-text-4)" strokeDasharray="4 4" />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="var(--perf-gain)"
                strokeWidth={1.75}
                fill="url(#eq-fill)"
                isAnimationActive
                animationDuration={620}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// DrawdownPanel — recharts area inverted, rose fill.
// ────────────────────────────────────────────────────────────────────

function DrawdownTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  return (
    <div
      style={{
        background: 'var(--perf-bg-elev)',
        border: '1px solid var(--perf-border-strong)',
        borderRadius: 4,
        padding: '0.625rem 0.875rem',
        fontFamily: 'var(--perf-font-mono)',
        fontSize: 11,
      }}
    >
      <div style={{ color: 'var(--perf-text-3)', marginBottom: 4 }}>
        {d?.timestamp ? format(new Date(d.timestamp), 'MMM d HH:mm') : '—'}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <span style={{ color: 'var(--perf-text-2)' }}>DRAWDOWN</span>
        <span style={{ color: 'var(--perf-loss)' }}>−{fmtNumber(d.drawdownPercent, 2)}%</span>
      </div>
    </div>
  )
}

function DrawdownPanel({ data, isLoading, currentDD, maxDD }) {
  const empty = !data || data.length < 2
  return (
    <div className="perf-card perf-corner-ticks perf-reveal perf-reveal-3" style={{ padding: '1.25rem' }}>
      <div className="flex items-baseline justify-between" style={{ marginBottom: '0.75rem' }}>
        <span className="perf-eyebrow">Drawdown</span>
        <div className="perf-mono" style={{ fontSize: 11, color: 'var(--perf-text-3)' }}>
          curr {fmtNumber(currentDD, 1)}% · max{' '}
          <span style={{ color: 'var(--perf-loss)' }}>−{fmtNumber(maxDD, 1)}%</span>
        </div>
      </div>

      {empty ? (
        <EmptyChart
          height={220}
          message={
            isLoading
              ? 'Computing drawdown series…'
              : 'Drawdown shows after the equity curve has its first new high then dips.'
          }
        />
      ) : (
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data.map((d) => ({ ...d, ddNeg: -Math.abs(d.drawdownPercent || 0) }))}
              margin={{ top: 8, right: 4, left: 4, bottom: 0 }}
            >
              <defs>
                <linearGradient id="dd-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--perf-loss)" stopOpacity={0} />
                  <stop offset="100%" stopColor="var(--perf-loss)" stopOpacity={0.32} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--perf-grid)" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(t) => format(new Date(t), 'MMM d')}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v) => `${v}%`}
                axisLine={false}
                tickLine={false}
                width={42}
              />
              <Tooltip content={<DrawdownTooltip />} cursor={{ stroke: 'var(--perf-border-strong)', strokeDasharray: '3 3' }} />
              <Area
                type="monotone"
                dataKey="ddNeg"
                stroke="var(--perf-loss)"
                strokeWidth={1.5}
                fill="url(#dd-fill)"
                isAnimationActive
                animationDuration={620}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// ReturnsHistogram — bar chart, teal positive / rose negative.
// ────────────────────────────────────────────────────────────────────

function ReturnsHistogram({ bins, stats, isLoading }) {
  const empty = !bins || bins.length === 0
  return (
    <div className="perf-card perf-corner-ticks perf-reveal perf-reveal-4" style={{ padding: '1.25rem' }}>
      <div className="flex items-baseline justify-between" style={{ marginBottom: '0.75rem' }}>
        <span className="perf-eyebrow">Returns Distribution</span>
        {stats && (
          <div className="perf-mono" style={{ fontSize: 11, color: 'var(--perf-text-3)' }}>
            μ {fmtNumber(stats.mean, 2)} · σ {fmtNumber(stats.stdDev, 2)} · skew{' '}
            {fmtNumber(stats.skewness, 2)}
          </div>
        )}
      </div>

      {empty ? (
        <EmptyChart
          height={220}
          message={
            isLoading
              ? 'Bucketing trade P&L…'
              : 'Distribution chart appears once you have at least a handful of closed trades.'
          }
        />
      ) : (
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bins} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
              <CartesianGrid stroke="var(--perf-grid)" vertical={false} />
              <XAxis
                dataKey="binMid"
                tickFormatter={(v) => v.toFixed(0)}
                axisLine={false}
                tickLine={false}
              />
              <YAxis axisLine={false} tickLine={false} width={32} />
              <Tooltip
                contentStyle={{
                  background: 'var(--perf-bg-elev)',
                  border: '1px solid var(--perf-border-strong)',
                  borderRadius: 4,
                  fontFamily: 'var(--perf-font-mono)',
                  fontSize: 11,
                }}
                labelFormatter={(v) => `bucket mid: ${Number(v).toFixed(2)}`}
              />
              <ReferenceLine x={0} stroke="var(--perf-text-4)" strokeDasharray="3 3" />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {bins.map((b, i) => (
                  <Cell
                    key={i}
                    fill={b.binMid >= 0 ? 'var(--perf-gain)' : 'var(--perf-loss)'}
                    fillOpacity={0.78}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// CorrelationGrid — hand-rolled CSS-grid heatmap.
// Replaces the legacy CorrelationHeatmap component (which had
// useMockData hardcoded). This always uses real data from the
// useCorrelationMatrix hook backed by /api/trading/correlations.
// ────────────────────────────────────────────────────────────────────

function corrColor(v) {
  // -1 (rose) → 0 (neutral) → +1 (teal)
  if (v == null || Number.isNaN(v)) return 'transparent'
  const t = Math.max(-1, Math.min(1, v))
  if (t >= 0) {
    const a = 0.08 + t * 0.62
    return `rgba(94, 234, 212, ${a.toFixed(3)})`
  }
  const a = 0.08 + Math.abs(t) * 0.55
  return `rgba(251, 113, 133, ${a.toFixed(3)})`
}

function CorrelationGrid({ symbols, matrix, isLoading }) {
  const sym = symbols && symbols.length > 0 ? symbols : CORRELATION_SYMBOLS
  const has = matrix && matrix.length > 0
  return (
    <div className="perf-card perf-corner-ticks perf-reveal perf-reveal-5" style={{ padding: '1.25rem' }}>
      <div className="flex items-baseline justify-between" style={{ marginBottom: '0.75rem' }}>
        <span className="perf-eyebrow">Asset Correlations</span>
        <span className="perf-mono" style={{ fontSize: 11, color: 'var(--perf-text-3)' }}>
          {has ? `${sym.length} × ${sym.length}` : '—'}
        </span>
      </div>

      {!has ? (
        <EmptyChart
          height={260}
          message={
            isLoading
              ? 'Computing pairwise correlations…'
              : 'Correlation matrix appears after enough overlapping price history accumulates per symbol.'
          }
        />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: `auto repeat(${sym.length}, minmax(60px, 1fr))`,
              gap: 2,
            }}
          >
            <div />
            {sym.map((s) => (
              <div
                key={`col-${s}`}
                className="perf-mono"
                style={{
                  fontSize: 10,
                  letterSpacing: '0.06em',
                  color: 'var(--perf-text-3)',
                  textAlign: 'center',
                  padding: '0.25rem 0',
                }}
              >
                {s.replace('USDT', '')}
              </div>
            ))}
            {sym.map((rs, ri) => (
              <React.Fragment key={`row-${rs}`}>
                <div
                  className="perf-mono"
                  style={{
                    fontSize: 10,
                    letterSpacing: '0.06em',
                    color: 'var(--perf-text-3)',
                    paddingRight: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                  }}
                >
                  {rs.replace('USDT', '')}
                </div>
                {sym.map((cs, ci) => {
                  const v = matrix?.[ri]?.[ci]
                  return (
                    <div
                      key={`cell-${rs}-${cs}`}
                      className="perf-mono"
                      title={`${rs} ⇄ ${cs}: ${v == null ? '—' : v.toFixed(3)}`}
                      style={{
                        background: corrColor(v),
                        color: 'var(--perf-text)',
                        fontSize: 11,
                        fontWeight: 500,
                        textAlign: 'center',
                        padding: '0.625rem 0.25rem',
                        border: '1px solid var(--perf-border)',
                        transition: 'transform 120ms ease',
                      }}
                    >
                      {v == null || Number.isNaN(v) ? '—' : v.toFixed(2)}
                    </div>
                  )
                })}
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// TradeStatsTable — editorial monospace data sheet.
// ────────────────────────────────────────────────────────────────────

function StatRow({ label, value, accent }) {
  return (
    <div
      className="flex items-baseline justify-between"
      style={{
        padding: '0.625rem 0',
        borderBottom: '1px dashed var(--perf-border)',
      }}
    >
      <span className="perf-eyebrow" style={{ letterSpacing: '0.12em' }}>
        {label}
      </span>
      <span
        className="perf-mono"
        style={{ fontSize: '0.9375rem', color: accent ?? 'var(--perf-text)' }}
      >
        {value}
      </span>
    </div>
  )
}

function TradeStatsTable({ metrics, isLoading }) {
  const m = metrics ?? {}
  return (
    <div
      className="perf-card-flat perf-corner-ticks perf-reveal perf-reveal-5"
      style={{ padding: '1.25rem 1.5rem' }}
    >
      <div
        className="grid grid-cols-1 md:grid-cols-3 gap-x-10"
      >
        <div>
          <StatRow
            label="Total Trades"
            value={isLoading ? '…' : (m.totalTrades ?? 0).toLocaleString()}
          />
          <StatRow
            label="Winning"
            value={isLoading ? '…' : (m.winningTrades ?? 0).toLocaleString()}
            accent="var(--perf-gain)"
          />
          <StatRow
            label="Losing"
            value={isLoading ? '…' : (m.losingTrades ?? 0).toLocaleString()}
            accent="var(--perf-loss)"
          />
        </div>
        <div>
          <StatRow
            label="Average Win"
            value={isLoading ? '…' : fmtUSD(m.avgWin)}
            accent="var(--perf-gain)"
          />
          <StatRow
            label="Average Loss"
            value={isLoading ? '…' : fmtUSD(m.avgLoss != null ? -Math.abs(m.avgLoss) : null)}
            accent="var(--perf-loss)"
          />
          <StatRow
            label="Expectancy"
            value={isLoading ? '…' : fmtUSD(m.expectancy)}
            accent={
              m.expectancy == null
                ? 'var(--perf-text)'
                : m.expectancy >= 0
                ? 'var(--perf-gain)'
                : 'var(--perf-loss)'
            }
          />
        </div>
        <div>
          <StatRow
            label="Gross Profit"
            value={isLoading ? '…' : fmtUSD(m.grossProfit)}
          />
          <StatRow
            label="Gross Loss"
            value={isLoading ? '…' : fmtUSD(m.grossLoss != null ? -Math.abs(m.grossLoss) : null)}
          />
          <StatRow
            label="Recovery Factor"
            value={isLoading ? '…' : fmtNumber(m.recoveryFactor, 2)}
          />
        </div>
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// EmptyChart — informative empty state used by every chart panel.
// ────────────────────────────────────────────────────────────────────

function EmptyChart({ height = 240, message }) {
  return (
    <div
      style={{
        height,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.75rem',
        color: 'var(--perf-text-3)',
        textAlign: 'center',
        padding: '1rem',
      }}
    >
      <Activity size={20} />
      <div style={{ maxWidth: 360, fontSize: 13, lineHeight: 1.55 }}>{message}</div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// Page error / no-data states.
// ────────────────────────────────────────────────────────────────────

function PageErrorState({ error, onRetry }) {
  return (
    <div
      className="perf-card perf-corner-ticks"
      style={{ padding: '2rem', textAlign: 'center' }}
    >
      <div className="perf-eyebrow" style={{ color: 'var(--perf-loss)' }}>
        Error
      </div>
      <h2 className="perf-section-title" style={{ marginTop: '0.5rem' }}>
        Couldn&apos;t load performance data
      </h2>
      <p
        className="perf-text-soft"
        style={{ marginTop: '0.75rem', maxWidth: '32rem', marginInline: 'auto', fontSize: 14 }}
      >
        {error?.message || 'Try again in a moment, or check that the api-gateway and trading-engine services are healthy.'}
      </p>
      <button
        onClick={onRetry}
        className="perf-mono"
        style={{
          marginTop: '1.25rem',
          padding: '0.5rem 1.125rem',
          background: 'var(--perf-text)',
          color: 'var(--perf-bg)',
          border: 'none',
          borderRadius: 4,
          fontSize: 12,
          letterSpacing: '0.06em',
          cursor: 'pointer',
        }}
      >
        RETRY
      </button>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// Main page
// ────────────────────────────────────────────────────────────────────

export default function PerformanceDashboard() {
  const [period, setPeriod] = useState('30d')

  const {
    isLoading,
    isError,
    error,
    metrics,
    equityCurve,
    drawdownSeries,
    returnsDistribution,
    tradeCount,
    refresh,
  } = usePerformanceMetrics({ period, pollingInterval: 30000 })

  const correlation = useCorrelationMatrix({ period, symbols: CORRELATION_SYMBOLS })

  const currentDD = drawdownSeries?.[drawdownSeries.length - 1]?.drawdownPercent ?? 0
  const maxDD = drawdownSeries?.length
    ? Math.max(...drawdownSeries.map((d) => d.drawdownPercent || 0))
    : 0

  return (
    <div className="perf-page">
      <PerfHeader
        period={period}
        onPeriodChange={setPeriod}
        onRefresh={refresh}
        isLoading={isLoading}
        lastUpdated={metrics?.lastUpdated}
      />

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
        {isError ? (
          <PageErrorState error={error} onRetry={refresh} />
        ) : (
          <>
            {/* ── HERO ROW: P&L + risk metrics column (asymmetric) ── */}
            <section
              className="grid"
              style={{
                gridTemplateColumns: 'minmax(0, 1.6fr) minmax(0, 1fr)',
                gap: 'clamp(1.5rem, 3vw, 3rem)',
                alignItems: 'start',
              }}
            >
              <HeroPnL
                totalPnL={metrics?.totalPnL}
                equityCurve={equityCurve}
                period={period}
                tradeCount={tradeCount}
              />
              <RiskMetricsColumn metrics={metrics} isLoading={isLoading} />
            </section>

            <div className="perf-rule" />

            {/* ── EQUITY CURVE: full-width hero chart ── */}
            <section>
              <SectionHeader
                index={1}
                title="Equity Curve"
                sub="Cumulative portfolio value over time. The dashed line marks starting equity."
              />
              <EquityCurvePanel data={equityCurve} isLoading={isLoading} />
            </section>

            {/* ── TWO-UP: drawdown + returns histogram ── */}
            <section
              className="grid"
              style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 28rem), 1fr))', gap: '1.5rem' }}
            >
              <div>
                <SectionHeader
                  index={2}
                  title="Drawdown"
                  sub="Peak-to-trough decline as a percentage of the running high."
                />
                <DrawdownPanel
                  data={drawdownSeries}
                  isLoading={isLoading}
                  currentDD={currentDD}
                  maxDD={maxDD}
                />
              </div>
              <div>
                <SectionHeader
                  index={3}
                  title="Returns Distribution"
                  sub="Histogram of per-trade P&L. Skew and kurtosis reveal the trading edge's shape."
                />
                <ReturnsHistogram
                  bins={returnsDistribution?.bins}
                  stats={returnsDistribution?.stats}
                  isLoading={isLoading}
                />
              </div>
            </section>

            {/* ── TRADE STATISTICS: editorial table ── */}
            <section>
              <SectionHeader
                index={4}
                title="Trade Statistics"
                sub="Per-trade economics and risk-of-ruin signals."
              />
              <TradeStatsTable metrics={metrics} isLoading={isLoading} />
            </section>

            {/* ── ASSET CORRELATIONS: real data via the new endpoint ── */}
            <section>
              <SectionHeader
                index={5}
                title="Asset Correlations"
                sub="Pairwise return correlation across tracked symbols. Highly-correlated assets diversify less than they appear."
              />
              <CorrelationGrid
                symbols={correlation.data?.symbols}
                matrix={correlation.data?.matrix}
                isLoading={correlation.isLoading}
              />
            </section>
          </>
        )}
      </main>
    </div>
  )
}
