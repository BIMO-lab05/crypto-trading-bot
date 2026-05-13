import React from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import TileState from './TileState'

/**
 * TradeHistory - Displays closed trades with win/loss statistics
 *
 * Shows:
 * - Closed trade history with entry/exit prices
 * - Win/loss indicators with P&L
 * - Trading statistics (win rate, profit factor, averages)
 * - Best/worst trade highlights
 *
 * Date: 2025-11-29
 *
 * UPDATED 2026-05-14 (Plan 06-05, DASH-05): wrapped in <TileState/> per
 * audit verdict FIXED. Inline isLoading/error early-returns removed.
 */

// Fetch trade history from trading engine
const fetchTradeHistory = async () => {
  const response = await axios.get('/api/trading/trades/history?limit=50', { timeout: 5000 })
  return response.data
}

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

// Format time ago
const formatTimeAgo = (dateStr) => {
  if (!dateStr) return 'Unknown'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

// Stats card component
const StatCard = ({ label, value, subValue, isPositive, isNegative }) => {
  const valueColor = isPositive
    ? 'text-emerald-400'
    : isNegative
    ? 'text-rose-400'
    : 'text-slate-100'

  return (
    <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-700/30">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${valueColor}`}>{value}</p>
      {subValue && <p className="text-xs text-slate-500">{subValue}</p>}
    </div>
  )
}

export default function TradeHistory() {
  const q = useQuery({
    queryKey: ['tradeHistory'],
    queryFn: fetchTradeHistory,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const trades = q.data?.trades || []
  const stats = q.data?.stats || {}

  return (
    <TileState
      query={q}
      title="Trade History"
      thresholdKey="positions"
      lastUpdatedAt={undefined}
      isEmpty={(d) => !d || (d.trades ?? []).length === 0}
    >
    <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 backdrop-blur-sm">
      {/* Header */}
      <div className="p-4 border-b border-slate-700/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-slate-100">Trade History</h3>
            <span className="px-2 py-0.5 bg-slate-700 text-slate-300 text-xs font-medium rounded-full">
              {trades.length} Closed
            </span>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-500">Total Realized P&L</p>
            <p className={`text-lg font-bold ${stats.total_realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {stats.total_realized_pnl >= 0 ? '+' : ''}${(stats.total_realized_pnl || 0).toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Statistics Grid */}
      {trades.length > 0 && (
        <div className="p-4 border-b border-slate-700/50">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard
              label="Win Rate"
              value={`${stats.win_rate || 0}%`}
              subValue={`${stats.winning_trades || 0}W / ${stats.losing_trades || 0}L`}
              isPositive={stats.win_rate >= 50}
              isNegative={stats.win_rate < 50 && stats.total_trades > 0}
            />
            <StatCard
              label="Total Trades"
              value={stats.total_trades || 0}
            />
            <StatCard
              label="Avg Win"
              value={`$${(stats.avg_win || 0).toFixed(2)}`}
              isPositive
            />
            <StatCard
              label="Avg Loss"
              value={`$${Math.abs(stats.avg_loss || 0).toFixed(2)}`}
              isNegative
            />
            <StatCard
              label="Best Trade"
              value={`$${(stats.best_trade || 0).toFixed(2)}`}
              isPositive
            />
            <StatCard
              label="Profit Factor"
              value={(stats.profit_factor || 0).toFixed(2)}
              isPositive={stats.profit_factor >= 1}
              isNegative={stats.profit_factor < 1 && stats.total_trades > 0}
            />
          </div>
        </div>
      )}

      {/* Trades List */}
      <div className="divide-y divide-slate-700/50 max-h-96 overflow-y-auto">
        {trades.length === 0 ? (
          <div className="p-8 text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-slate-700/50 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </div>
            <p className="text-slate-400 text-sm">No closed trades yet</p>
            <p className="text-slate-500 text-xs mt-1">Trade history will appear here after positions are closed</p>
          </div>
        ) : (
          trades.map((trade, index) => {
            const pnl = formatPnL(trade.realized_pnl)
            const isWin = parseFloat(trade.realized_pnl || 0) > 0
            const isLoss = parseFloat(trade.realized_pnl || 0) < 0

            return (
              <div key={trade.id || index} className="p-4 hover:bg-slate-700/20 transition-colors">
                {/* Top Row: Symbol, Side, P&L */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    {/* Win/Loss Badge */}
                    <div className={`
                      w-8 h-8 rounded-full flex items-center justify-center
                      ${isWin
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : isLoss
                        ? 'bg-rose-500/20 text-rose-400'
                        : 'bg-slate-700/50 text-slate-400'
                      }
                    `}>
                      {isWin ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : isLoss ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                        </svg>
                      )}
                    </div>

                    <div className={`
                      px-2 py-0.5 rounded text-xs font-medium
                      ${trade.side === 'LONG'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-rose-500/10 text-rose-400'
                      }
                    `}>
                      {trade.side}
                    </div>

                    <div>
                      <span className="text-base font-bold text-slate-100">
                        {trade.symbol?.replace('USDT', '')}
                      </span>
                      <span className="text-slate-500 text-sm">/USDT</span>
                    </div>
                  </div>

                  <div className="text-right">
                    <p className={`text-lg font-bold ${pnl.isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pnl.value}
                    </p>
                    <p className="text-xs text-slate-500">
                      {isWin ? 'WIN' : isLoss ? 'LOSS' : 'BREAK-EVEN'}
                    </p>
                  </div>
                </div>

                {/* Price Row */}
                <div className="grid grid-cols-3 gap-4 mb-2">
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Entry</p>
                    <p className="text-sm font-medium text-slate-200">{formatPrice(trade.entry_price)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Exit</p>
                    <p className={`text-sm font-medium ${pnl.isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {formatPrice(trade.exit_price || trade.current_price)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">Quantity</p>
                    <p className="text-sm font-medium text-slate-200">
                      {parseFloat(trade.quantity).toFixed(6)}
                    </p>
                  </div>
                </div>

                {/* Bottom Row: Strategy, Time */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-slate-700 rounded text-slate-400">
                      {trade.strategy || 'manual'}
                    </span>
                  </div>
                  <span className="text-slate-500">
                    Closed {formatTimeAgo(trade.closed_at)}
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-slate-700/50 text-center">
        <p className="text-xs text-slate-500">
          Auto-refresh: 30s • Showing last {trades.length} trades
        </p>
      </div>
    </div>
    </TileState>
  )
}
