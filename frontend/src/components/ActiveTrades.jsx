import React from 'react'
import { usePositions } from '../hooks/usePositions'
import TileState from './TileState'

/**
 * ActiveTrades - Displays all executed trades and their real-time status
 *
 * UPDATED 2025-11-30: Fixed duplicate API calls
 * - Now uses shared usePositions hook instead of direct axios call
 * - Eliminates duplicate /api/trading/positions requests
 * - Shares cache with KeyMetricsStrip for better performance
 *
 * UPDATED 2026-05-14 (Plan 06-05, DASH-05): wrapped in <TileState/> per
 * audit verdict FIXED. Replaces inline isLoading/error early-returns.
 *
 * Shows:
 * - Open positions with entry price, current price, P&L
 * - Stop loss and take profit levels
 * - Position size and remaining quantity
 * - Trade timing and strategy used
 *
 * Author: Frontend Developer
 * Date: 2025-11-29
 */

// Format currency
const formatPrice = (value, decimals = 2) => {
  const num = parseFloat(value) || 0
  if (num >= 1000) return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  if (num >= 1) return `$${num.toFixed(decimals)}`
  return `$${num.toFixed(6)}`
}

// Format P&L with color
const formatPnL = (value) => {
  const num = parseFloat(value) || 0
  const formatted = num >= 0 ? `+$${num.toFixed(2)}` : `-$${Math.abs(num).toFixed(2)}`
  return { value: formatted, isPositive: num >= 0 }
}

// Format percentage
const formatPercent = (entry, current) => {
  const e = parseFloat(entry) || 0
  const c = parseFloat(current) || 0
  if (e === 0) return '0.00%'
  const pct = ((c - e) / e) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
}

// Format time ago
const formatTimeAgo = (dateStr) => {
  if (!dateStr) return 'Unknown'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ${diffMins % 60}m ago`
  return date.toLocaleDateString()
}

export default function ActiveTrades() {
  // Use shared positions hook - eliminates duplicate API calls.
  // Inline isLoading/error early-returns removed in favor of <TileState/>
  // (Plan 06-05, DASH-05).
  const q = usePositions()

  // Extract positions array from the response
  const positions = q.data?.positions || []
  const openPositions = positions?.filter(p => p.status === 'OPEN') || []
  const totalUnrealizedPnL = openPositions.reduce((sum, p) => sum + parseFloat(p.unrealized_pnl || 0), 0)

  return (
    <div data-testid="active-trades" style={{ display: 'contents' }}>
    <TileState
      query={q}
      title="Active Trades"
      thresholdKey="positions"
      lastUpdatedAt={undefined}
      isEmpty={(d) => !d || ((d.positions ?? []).filter(p => p.status === 'OPEN')).length === 0}
    >
    <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 backdrop-blur-sm">
      {/* Header */}
      <div className="p-4 border-b border-slate-700/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-slate-100">Active Trades</h3>
            <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-400 text-xs font-medium rounded-full">
              {openPositions.length} Open
            </span>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-500">Total Unrealized P&L</p>
            <p className={`text-lg font-bold ${totalUnrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {totalUnrealizedPnL >= 0 ? '+' : ''}${totalUnrealizedPnL.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Trades List */}
      <div className="divide-y divide-slate-700/50">
        {openPositions.length === 0 ? (
          <div className="p-8 text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-slate-700/50 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M20 12H4M8 8l-4 4 4 4M16 16l4-4-4-4" />
              </svg>
            </div>
            <p className="text-slate-400 text-sm">No active trades</p>
            <p className="text-slate-500 text-xs mt-1">Waiting for trading signals...</p>
          </div>
        ) : (
          openPositions.map((position) => {
            const pnl = formatPnL(position.unrealized_pnl)
            const pctChange = formatPercent(position.entry_price, position.current_price)
            const entryPrice = parseFloat(position.entry_price) || 0
            const currentPrice = parseFloat(position.current_price) || 0
            const stopLoss = parseFloat(position.stop_loss) || 0
            const takeProfit = parseFloat(position.take_profit) || 0

            // Calculate distance to SL and TP.
            // Guard division by zero: render '—' when currentPrice is 0/undefined.
            const distToSL = currentPrice > 0
              ? (position.side === 'LONG'
                  ? ((currentPrice - stopLoss) / currentPrice * 100).toFixed(1)
                  : ((stopLoss - currentPrice) / currentPrice * 100).toFixed(1))
              : '—'
            const distToTP = currentPrice > 0
              ? (position.side === 'LONG'
                  ? ((takeProfit - currentPrice) / currentPrice * 100).toFixed(1)
                  : ((currentPrice - takeProfit) / currentPrice * 100).toFixed(1))
              : '—'

            // Guard NaN quantity (missing/garbage field) — render '—' instead of "NaN"
            const quantityNum = Number.parseFloat(position.quantity)
            const quantityDisplay = Number.isNaN(quantityNum) ? '—' : quantityNum.toFixed(6)

            return (
              <div key={position.id} className="p-4 hover:bg-slate-700/20 transition-colors">
                {/* Top Row: Symbol, Side, P&L */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`
                      px-2 py-1 rounded text-xs font-bold
                      ${position.side === 'LONG'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      }
                    `}>
                      {position.side}
                    </div>
                    <div>
                      <span className="text-lg font-bold text-slate-100">
                        {position.symbol?.replace('USDT', '') ?? '—'}
                      </span>
                      <span className="text-slate-500 text-sm">/USDT</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-lg font-bold ${pnl.isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pnl.value}
                    </p>
                    <p className={`text-xs ${pnl.isPositive ? 'text-emerald-400/70' : 'text-rose-400/70'}`}>
                      {pctChange}
                    </p>
                  </div>
                </div>

                {/* Price Row */}
                <div className="grid grid-cols-3 gap-4 mb-3">
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Entry Price</p>
                    <p className="text-sm font-medium text-slate-200">{formatPrice(entryPrice)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Current Price</p>
                    <p className={`text-sm font-medium ${pnl.isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatPrice(currentPrice)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Position Size</p>
                    <p className="text-sm font-medium text-slate-200">
                      {quantityDisplay}
                    </p>
                  </div>
                </div>

                {/* SL/TP Row */}
                <div className="grid grid-cols-2 gap-4 mb-3">
                  <div className="bg-rose-500/10 rounded px-3 py-2 border border-rose-500/20">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-rose-400">Stop Loss</span>
                      <span className="text-xs text-slate-500">{distToSL === '—' ? '—' : `${distToSL}% away`}</span>
                    </div>
                    <p className="text-sm font-medium text-rose-300">{formatPrice(stopLoss)}</p>
                  </div>
                  <div className="bg-emerald-500/10 rounded px-3 py-2 border border-emerald-500/20">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-emerald-400">Take Profit (Final)</span>
                      <span className="text-xs text-slate-500">{distToTP === '—' ? '—' : `${distToTP}% away`}</span>
                    </div>
                    <p className="text-sm font-medium text-emerald-300">{formatPrice(takeProfit)}</p>
                  </div>
                </div>

                {/* Partial Take Profit Levels (TP1, TP2, TP3) */}
                {(position.take_profit_1 || position.take_profit_2 || position.take_profit_3) && (
                  <div className="grid grid-cols-3 gap-2 mb-3">
                    {/* TP1 */}
                    <div className={`rounded px-2 py-1.5 border ${
                      position.tp1_hit
                        ? 'bg-emerald-500/30 border-emerald-500/50'
                        : 'bg-cyan-500/10 border-cyan-500/20'
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className={`text-[10px] font-medium ${position.tp1_hit ? 'text-emerald-400' : 'text-cyan-400'}`}>
                          TP1 {position.tp1_hit && '✓'}
                        </span>
                        <span className="text-[10px] text-slate-500">33%</span>
                      </div>
                      <p className={`text-xs font-medium ${position.tp1_hit ? 'text-emerald-300' : 'text-cyan-300'}`}>
                        {position.take_profit_1 ? formatPrice(position.take_profit_1) : '-'}
                      </p>
                    </div>

                    {/* TP2 */}
                    <div className={`rounded px-2 py-1.5 border ${
                      position.tp2_hit
                        ? 'bg-emerald-500/30 border-emerald-500/50'
                        : 'bg-cyan-500/10 border-cyan-500/20'
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className={`text-[10px] font-medium ${position.tp2_hit ? 'text-emerald-400' : 'text-cyan-400'}`}>
                          TP2 {position.tp2_hit && '✓'}
                        </span>
                        <span className="text-[10px] text-slate-500">33%</span>
                      </div>
                      <p className={`text-xs font-medium ${position.tp2_hit ? 'text-emerald-300' : 'text-cyan-300'}`}>
                        {position.take_profit_2 ? formatPrice(position.take_profit_2) : '-'}
                      </p>
                    </div>

                    {/* TP3 */}
                    <div className={`rounded px-2 py-1.5 border ${
                      position.tp3_hit
                        ? 'bg-emerald-500/30 border-emerald-500/50'
                        : 'bg-cyan-500/10 border-cyan-500/20'
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className={`text-[10px] font-medium ${position.tp3_hit ? 'text-emerald-400' : 'text-cyan-400'}`}>
                          TP3 {position.tp3_hit && '✓'}
                        </span>
                        <span className="text-[10px] text-slate-500">34%</span>
                      </div>
                      <p className={`text-xs font-medium ${position.tp3_hit ? 'text-emerald-300' : 'text-cyan-300'}`}>
                        {position.take_profit_3 ? formatPrice(position.take_profit_3) : '-'}
                      </p>
                    </div>
                  </div>
                )}

                {/* Bottom Row: Strategy, Time, Status */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <span className="px-2 py-0.5 bg-slate-700 rounded text-slate-400">
                      {position.strategy || 'unknown'}
                    </span>
                    <span className="text-slate-500">
                      Opened {formatTimeAgo(position.opened_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {position.trailing_stop_enabled && (
                      <span className="px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded text-[10px]">
                        TRAILING
                      </span>
                    )}
                    {position.tp1_hit && (
                      <span className="px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 rounded text-[10px]">
                        TP1 HIT
                      </span>
                    )}
                    {position.tp2_hit && (
                      <span className="px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 rounded text-[10px]">
                        TP2 HIT
                      </span>
                    )}
                    <span className="flex items-center gap-1 text-emerald-400">
                      <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                      LIVE
                    </span>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Footer with refresh info */}
      <div className="p-3 border-t border-slate-700/50 text-center">
        <p className="text-xs text-slate-500">
          Auto-refresh: 10s • Prices update in real-time
        </p>
      </div>
    </div>
    </TileState>
    </div>
  )
}
