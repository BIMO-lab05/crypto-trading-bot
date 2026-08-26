import React, { useMemo } from 'react'
import { useKlines } from '../hooks/useTicker'
import TileState from './TileState'

/**
 * Sparkline — tiny SVG-rendered close-price line for a ticker.
 *
 * Pulls 24h of 60m candles (24 points) via useKlines (already cached per
 * symbol), normalises to a unit box, draws a single polyline with an
 * area-fill underlay. No axes, no labels, no tooltips. ~36px tall.
 *
 * Direction colour is derived from first→last close so it matches the
 * 24h-change badge above it.
 *
 * UPDATED 2026-05-14 (Plan 06-05, DASH-05): wrapped in <TileState/>
 * (shares /api/market/klines/* endpoint with PriceChart). 2026-08-20:
 * forceStale flag removed — the endpoint is healthy again. The stale
 * badge is driven by the query's `dataUpdatedAt` (epoch ms of the last
 * successful fetch) passed as `lastUpdatedAt` to TileState. F-05
 * precedence preserves real errors.
 */

const W = 120
const H = 32

export default function Sparkline({ symbol, intent }) {
  const q = useKlines(symbol, '60', { limit: 24 })
  const klines = q.data

  const { path, area, colour } = useMemo(() => {
    const closes = (klines || [])
      .map((k) => Number(k.close ?? k.c ?? k.close_price))
      .filter((v) => Number.isFinite(v) && v > 0)

    if (closes.length < 2) return { path: '', area: '', colour: '#8a8982' }

    const min = Math.min(...closes)
    const max = Math.max(...closes)
    const span = max - min || 1
    const stepX = W / (closes.length - 1)

    const points = closes.map((c, i) => {
      const x = i * stepX
      const y = H - ((c - min) / span) * H
      return [x, y]
    })

    const directionUp = closes[closes.length - 1] >= closes[0]
    const c = intent
      ? intent === 'positive'
        ? '#5eead4'
        : '#fb7185'
      : directionUp
      ? '#5eead4'
      : '#fb7185'

    const pathStr = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
    const areaStr = `${pathStr} L${W},${H} L0,${H} Z`

    return { path: pathStr, area: areaStr, colour: c }
  }, [klines, intent])

  // TileState handles loading/error/empty/stale; the existing skeleton path
  // is retained as a defensive in-success-with-thin-data fallback (path is
  // computed inside useMemo, may yield '' if closes.length < 2).
  const gradId = `spark-${symbol}`
  return (
    <div data-testid="sparkline" style={{ display: 'contents' }}>
    <TileState
      query={q}
      title="Sparkline"
      thresholdKey="ticker"
      lastUpdatedAt={q.dataUpdatedAt || undefined}
      isEmpty={(d) => !d || !Array.isArray(d) || d.length === 0}
    >
      {!path ? (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height={H}
          className="block opacity-30"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="#3d3c38" strokeDasharray="2 4" strokeWidth="1" />
        </svg>
      ) : (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height={H}
          className="block"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={colour} stopOpacity="0.28" />
              <stop offset="100%" stopColor={colour} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#${gradId})`} stroke="none" />
          <path d={path} fill="none" stroke={colour} strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </TileState>
    </div>
  )
}
