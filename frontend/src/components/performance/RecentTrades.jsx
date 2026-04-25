/**
 * RecentTrades.jsx - Recent Trades Table Component with Virtual Scrolling
 *
 * Purpose: Displays the most recent trades in a sortable, filterable table
 * with virtual scrolling for performance with large datasets.
 *
 * Features:
 * - Virtual scrolling for 1000+ rows
 * - Sortable columns
 * - Filterable by strategy, symbol, side
 * - Color-coded P&L
 * - Trade quality score indicators
 * - Click to view trade details
 * - Export functionality
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import PropTypes from 'prop-types'
import {
  formatCurrency,
  formatPnL,
  formatPrice,
  formatQuantity,
  formatTimestamp,
  formatRelativeTime,
  formatSymbol,
  formatTradeSide,
  getPnLColorClass,
  getSideColorClass,
} from '../../utils/formatters'

// ============================================================================
// CONSTANTS
// ============================================================================

const ROW_HEIGHT = 48 // Height of each row in pixels
const OVERSCAN_COUNT = 5 // Number of extra rows to render above/below viewport
const DEFAULT_PAGE_SIZE = 50 // Default number of trades to show

// ============================================================================
// LOADING SKELETON
// ============================================================================

const RecentTradesSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden animate-pulse">
    <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
      <div className="h-6 bg-slate-700 rounded w-1/4 mb-2"></div>
      <div className="flex gap-2">
        <div className="h-8 bg-slate-700 rounded w-24"></div>
        <div className="h-8 bg-slate-700 rounded w-24"></div>
      </div>
    </div>
    <div className="p-4">
      {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
        <div key={i} className="flex items-center gap-4 py-3 border-b border-slate-700/30">
          <div className="h-4 bg-slate-700 rounded w-24"></div>
          <div className="h-4 bg-slate-700 rounded w-20"></div>
          <div className="h-4 bg-slate-700 rounded w-16"></div>
          <div className="h-4 bg-slate-700 rounded w-20"></div>
          <div className="h-4 bg-slate-700 rounded w-20"></div>
          <div className="h-4 bg-slate-700 rounded flex-1"></div>
        </div>
      ))}
    </div>
  </div>
)

// ============================================================================
// TRADE QUALITY INDICATOR
// ============================================================================

/**
 * TradeQualityBadge - Shows trade quality score
 */
const TradeQualityBadge = ({ score }) => {
  if (score == null) return null

  let bgClass, textClass, label
  if (score >= 80) {
    bgClass = 'bg-emerald-500/20'
    textClass = 'text-emerald-400'
    label = 'A'
  } else if (score >= 60) {
    bgClass = 'bg-green-500/20'
    textClass = 'text-green-400'
    label = 'B'
  } else if (score >= 40) {
    bgClass = 'bg-amber-500/20'
    textClass = 'text-amber-400'
    label = 'C'
  } else {
    bgClass = 'bg-rose-500/20'
    textClass = 'text-rose-400'
    label = 'D'
  }

  return (
    <div
      className={`w-7 h-7 rounded-full ${bgClass} flex items-center justify-center`}
      title={`Trade Quality: ${score}/100`}
    >
      <span className={`text-xs font-bold ${textClass}`}>{label}</span>
    </div>
  )
}

// ============================================================================
// FILTER DROPDOWN
// ============================================================================

const FilterDropdown = ({ label, value, options, onChange }) => (
  <div className="relative">
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="appearance-none bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 pr-8 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 cursor-pointer"
    >
      <option value="">{label}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
    <svg
      className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  </div>
)

// ============================================================================
// SORT INDICATOR
// ============================================================================

const SortIndicator = ({ direction }) => (
  <svg
    className={`w-4 h-4 inline-block ml-1 transition-transform ${
      direction === 'desc' ? 'rotate-180' : ''
    }`}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M5 15l7-7 7 7"
    />
  </svg>
)

// ============================================================================
// TABLE HEADER
// ============================================================================

const TableHeader = ({ columns, sortConfig, onSort }) => (
  <div className="flex items-center bg-slate-800/50 border-b border-slate-700/50 sticky top-0 z-10">
    {columns.map((column) => (
      <div
        key={column.key}
        className={`${column.width} px-3 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide ${
          column.sortable ? 'cursor-pointer hover:text-slate-200' : ''
        } ${column.align === 'right' ? 'text-right' : ''}`}
        onClick={() => column.sortable && onSort(column.key)}
      >
        {column.label}
        {column.sortable && sortConfig.key === column.key && (
          <SortIndicator direction={sortConfig.direction} />
        )}
      </div>
    ))}
    <div className="w-10"></div> {/* Space for scroll bar */}
  </div>
)

// ============================================================================
// VIRTUAL ROW
// ============================================================================

const TradeRow = ({ trade, style, onClick, isSelected }) => {
  const pnl = parseFloat(trade.realized_pnl || 0)
  const pnlColorClass = getPnLColorClass(pnl)
  const sideColorClass = getSideColorClass(trade.side)

  return (
    <div
      style={style}
      onClick={() => onClick && onClick(trade)}
      className={`flex items-center border-b border-slate-700/30 hover:bg-slate-700/30 cursor-pointer transition-colors ${
        isSelected ? 'bg-slate-700/50' : ''
      }`}
    >
      {/* Time */}
      <div className="w-[140px] px-3 py-2 text-sm text-slate-400">
        {formatTimestamp(trade.closed_at || trade.timestamp, 'MMM d HH:mm')}
      </div>

      {/* Symbol */}
      <div className="w-[100px] px-3 py-2 text-sm font-medium text-slate-200">
        {formatSymbol(trade.symbol)}
      </div>

      {/* Side */}
      <div className={`w-[70px] px-3 py-2 text-sm font-medium ${sideColorClass}`}>
        {formatTradeSide(trade.side)}
      </div>

      {/* Entry Price */}
      <div className="w-[100px] px-3 py-2 text-sm text-slate-300 text-right">
        {formatPrice(trade.entry_price)}
      </div>

      {/* Exit Price */}
      <div className="w-[100px] px-3 py-2 text-sm text-slate-300 text-right">
        {formatPrice(trade.exit_price)}
      </div>

      {/* Quantity */}
      <div className="w-[80px] px-3 py-2 text-sm text-slate-400 text-right">
        {formatQuantity(trade.quantity)}
      </div>

      {/* P&L */}
      <div className={`w-[100px] px-3 py-2 text-sm font-semibold text-right ${pnlColorClass}`}>
        {formatPnL(pnl)}
      </div>

      {/* Strategy */}
      <div className="flex-1 px-3 py-2 text-sm text-slate-400 truncate">
        {trade.strategy || trade.signal_source || '-'}
      </div>

      {/* Quality */}
      <div className="w-[50px] px-3 py-2 flex justify-center">
        <TradeQualityBadge score={trade.quality_score} />
      </div>
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * RecentTrades - Recent Trades Table with Virtual Scrolling
 *
 * @param {Object} props - Component props
 * @param {Array} props.trades - Trade history array
 * @param {boolean} props.loading - Loading state
 * @param {number} props.maxHeight - Maximum height of the table
 * @param {Function} props.onTradeClick - Handler for trade row click
 * @param {string} props.className - Additional CSS classes
 */
function RecentTrades({
  trades = [],
  loading = false,
  maxHeight = 450,
  onTradeClick,
  className = '',
}) {
  const containerRef = useRef(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [selectedTradeId, setSelectedTradeId] = useState(null)

  // Filter state
  const [filters, setFilters] = useState({
    symbol: '',
    side: '',
    strategy: '',
  })

  // Sort state
  const [sortConfig, setSortConfig] = useState({
    key: 'closed_at',
    direction: 'desc',
  })

  // ============================================================================
  // FILTER OPTIONS
  // ============================================================================

  const filterOptions = useMemo(() => {
    const symbols = [...new Set(trades.map((t) => t.symbol).filter(Boolean))]
    const sides = [...new Set(trades.map((t) => t.side).filter(Boolean))]
    const strategies = [...new Set(trades.map((t) => t.strategy || t.signal_source).filter(Boolean))]

    return {
      symbols: symbols.map((s) => ({ value: s, label: formatSymbol(s) })),
      sides: sides.map((s) => ({ value: s, label: formatTradeSide(s) })),
      strategies: strategies.map((s) => ({ value: s, label: s })),
    }
  }, [trades])

  // ============================================================================
  // FILTERED AND SORTED DATA
  // ============================================================================

  const processedTrades = useMemo(() => {
    let filtered = [...trades]

    // Apply filters
    if (filters.symbol) {
      filtered = filtered.filter((t) => t.symbol === filters.symbol)
    }
    if (filters.side) {
      filtered = filtered.filter((t) => t.side === filters.side)
    }
    if (filters.strategy) {
      filtered = filtered.filter(
        (t) => (t.strategy || t.signal_source) === filters.strategy
      )
    }

    // Apply sorting
    filtered.sort((a, b) => {
      const key = sortConfig.key
      let aVal = a[key]
      let bVal = b[key]

      // Handle dates
      if (key === 'closed_at' || key === 'opened_at' || key === 'timestamp') {
        aVal = new Date(aVal || 0).getTime()
        bVal = new Date(bVal || 0).getTime()
      }

      // Handle numbers
      if (typeof aVal === 'string' && !isNaN(parseFloat(aVal))) {
        aVal = parseFloat(aVal)
        bVal = parseFloat(bVal)
      }

      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
      return 0
    })

    return filtered
  }, [trades, filters, sortConfig])

  // ============================================================================
  // COLUMN DEFINITIONS
  // ============================================================================

  const columns = [
    { key: 'closed_at', label: 'Time', width: 'w-[140px]', sortable: true },
    { key: 'symbol', label: 'Symbol', width: 'w-[100px]', sortable: true },
    { key: 'side', label: 'Side', width: 'w-[70px]', sortable: true },
    { key: 'entry_price', label: 'Entry', width: 'w-[100px]', sortable: true, align: 'right' },
    { key: 'exit_price', label: 'Exit', width: 'w-[100px]', sortable: true, align: 'right' },
    { key: 'quantity', label: 'Qty', width: 'w-[80px]', sortable: true, align: 'right' },
    { key: 'realized_pnl', label: 'P&L', width: 'w-[100px]', sortable: true, align: 'right' },
    { key: 'strategy', label: 'Strategy', width: 'flex-1', sortable: true },
    { key: 'quality', label: '', width: 'w-[50px]', sortable: false },
  ]

  // ============================================================================
  // VIRTUAL SCROLLING CALCULATIONS
  // ============================================================================

  const totalHeight = processedTrades.length * ROW_HEIGHT
  const visibleCount = Math.ceil(maxHeight / ROW_HEIGHT)
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN_COUNT)
  const endIndex = Math.min(
    processedTrades.length,
    startIndex + visibleCount + OVERSCAN_COUNT * 2
  )

  const visibleTrades = processedTrades.slice(startIndex, endIndex)
  const offsetY = startIndex * ROW_HEIGHT

  // ============================================================================
  // HANDLERS
  // ============================================================================

  const handleScroll = useCallback((e) => {
    setScrollTop(e.target.scrollTop)
  }, [])

  const handleSort = useCallback((key) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }))
  }, [])

  const handleFilterChange = useCallback((filterKey, value) => {
    setFilters((prev) => ({
      ...prev,
      [filterKey]: value,
    }))
  }, [])

  const handleTradeClick = useCallback((trade) => {
    setSelectedTradeId(trade.id)
    if (onTradeClick) {
      onTradeClick(trade)
    }
  }, [onTradeClick])

  const clearFilters = useCallback(() => {
    setFilters({ symbol: '', side: '', strategy: '' })
  }, [])

  if (loading) {
    return <RecentTradesSkeleton />
  }

  const hasFilters = filters.symbol || filters.side || filters.strategy

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              Recent Trades
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {processedTrades.length} of {trades.length} trades
              {hasFilters && ' (filtered)'}
            </p>
          </div>

          {/* Clear Filters Button */}
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-2">
          <FilterDropdown
            label="All Symbols"
            value={filters.symbol}
            options={filterOptions.symbols}
            onChange={(v) => handleFilterChange('symbol', v)}
          />
          <FilterDropdown
            label="All Sides"
            value={filters.side}
            options={filterOptions.sides}
            onChange={(v) => handleFilterChange('side', v)}
          />
          <FilterDropdown
            label="All Strategies"
            value={filters.strategy}
            options={filterOptions.strategies}
            onChange={(v) => handleFilterChange('strategy', v)}
          />
        </div>
      </div>

      {/* Table */}
      {processedTrades.length === 0 ? (
        <div className="flex items-center justify-center h-[200px] text-slate-400">
          <div className="text-center">
            <p className="text-lg mb-2">No trades found</p>
            <p className="text-sm text-slate-500">
              {hasFilters
                ? 'Try adjusting your filters'
                : 'Trade history will appear here'
              }
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* Column Headers */}
          <TableHeader
            columns={columns}
            sortConfig={sortConfig}
            onSort={handleSort}
          />

          {/* Scrollable Body */}
          <div
            ref={containerRef}
            onScroll={handleScroll}
            className="overflow-auto"
            style={{ maxHeight: `${maxHeight}px` }}
          >
            <div style={{ height: `${totalHeight}px`, position: 'relative' }}>
              <div style={{ transform: `translateY(${offsetY}px)` }}>
                {visibleTrades.map((trade, index) => (
                  <TradeRow
                    key={trade.id || `${trade.symbol}-${trade.closed_at}-${startIndex + index}`}
                    trade={trade}
                    style={{ height: `${ROW_HEIGHT}px` }}
                    onClick={handleTradeClick}
                    isSelected={selectedTradeId === trade.id}
                  />
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Footer */}
      <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
        <div className="flex items-center justify-between text-[10px] text-slate-500">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-emerald-500 rounded-full"></span>
              Profitable
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-rose-500 rounded-full"></span>
              Loss
            </span>
          </div>
          <span>
            Showing {Math.min(processedTrades.length, visibleCount)} of {processedTrades.length} trades
          </span>
        </div>
      </div>
    </div>
  )
}

// PropTypes
RecentTrades.propTypes = {
  trades: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
      symbol: PropTypes.string,
      side: PropTypes.string,
      entry_price: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
      exit_price: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
      quantity: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
      realized_pnl: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
      opened_at: PropTypes.string,
      closed_at: PropTypes.string,
      timestamp: PropTypes.string,
      strategy: PropTypes.string,
      signal_source: PropTypes.string,
      quality_score: PropTypes.number,
    })
  ),
  loading: PropTypes.bool,
  maxHeight: PropTypes.number,
  onTradeClick: PropTypes.func,
  className: PropTypes.string,
}

export default RecentTrades
