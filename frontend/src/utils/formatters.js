/**
 * formatters.js - Number and Currency Formatting Utilities
 *
 * Purpose: Provides consistent formatting functions for currencies, percentages,
 * numbers, and dates across the performance dashboard.
 *
 * Features:
 * - Currency formatting with locale support
 * - Percentage formatting with sign indicators
 * - Compact number formatting (1.2K, 3.5M)
 * - Date and time formatting
 * - Relative time formatting
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import { format, formatDistance, parseISO, isValid } from 'date-fns'

// ============================================================================
// CURRENCY FORMATTING
// ============================================================================

/**
 * Format value as currency
 *
 * @param {number} value - Value to format
 * @param {Object} options - Formatting options
 * @param {string} options.currency - Currency code (default: 'USD')
 * @param {number} options.decimals - Decimal places (default: 2)
 * @param {boolean} options.showSign - Show +/- sign (default: false)
 * @param {boolean} options.compact - Use compact notation (default: false)
 * @returns {string} Formatted currency string
 */
export function formatCurrency(value, options = {}) {
  // Handle null/undefined/NaN
  if (value == null || isNaN(value)) return 'N/A'

  const {
    currency = 'USD',
    decimals = 2,
    showSign = false,
    compact = false,
  } = options

  // Determine sign prefix
  const sign = showSign && value > 0 ? '+' : ''

  // Use compact notation for large numbers
  if (compact && Math.abs(value) >= 1000) {
    return `${sign}${formatCompact(value, { prefix: '$', decimals: 1 })}`
  }

  // Standard currency formatting
  const formatted = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })

  // Handle negative values
  if (value < 0) {
    return `-$${formatted}`
  }

  return `${sign}$${formatted}`
}

/**
 * Format value as currency with sign indicator
 * Convenience wrapper for P&L values
 *
 * @param {number} value - P&L value
 * @param {number} decimals - Decimal places
 * @returns {string} Formatted P&L string with sign
 */
export function formatPnL(value, decimals = 2) {
  return formatCurrency(value, { showSign: true, decimals })
}

/**
 * Format currency in compact form
 * e.g., $1.2K, $3.5M, $1.2B
 *
 * @param {number} value - Value to format
 * @returns {string} Compact currency string
 */
export function formatCurrencyCompact(value) {
  return formatCurrency(value, { compact: true })
}

// ============================================================================
// PERCENTAGE FORMATTING
// ============================================================================

/**
 * Format value as percentage
 *
 * @param {number} value - Value to format (0.5 = 50% or 50 = 50% depending on isRaw)
 * @param {Object} options - Formatting options
 * @param {boolean} options.isRaw - If true, value is already in percentage form (default: false)
 * @param {number} options.decimals - Decimal places (default: 2)
 * @param {boolean} options.showSign - Show +/- sign (default: false)
 * @returns {string} Formatted percentage string
 */
export function formatPercent(value, options = {}) {
  // Handle null/undefined/NaN
  if (value == null || isNaN(value)) return 'N/A'

  const {
    isRaw = false,
    decimals = 2,
    showSign = false,
  } = options

  // Convert to percentage if not raw
  const percentValue = isRaw ? value : value * 100

  // Determine sign prefix
  const sign = showSign && percentValue > 0 ? '+' : ''

  return `${sign}${percentValue.toFixed(decimals)}%`
}

/**
 * Format win rate (always positive, 0-100 range)
 *
 * @param {number} value - Win rate value (0-100)
 * @param {number} decimals - Decimal places
 * @returns {string} Formatted win rate
 */
export function formatWinRate(value, decimals = 1) {
  return formatPercent(value, { isRaw: true, decimals })
}

/**
 * Format percentage change with sign
 *
 * @param {number} value - Change value (0.1 = +10%)
 * @param {number} decimals - Decimal places
 * @returns {string} Formatted change string
 */
export function formatChange(value, decimals = 2) {
  return formatPercent(value, { showSign: true, decimals })
}

// ============================================================================
// NUMBER FORMATTING
// ============================================================================

/**
 * Format number with locale-aware separators
 *
 * @param {number} value - Value to format
 * @param {Object} options - Formatting options
 * @param {number} options.decimals - Decimal places (default: 0)
 * @param {boolean} options.showSign - Show +/- sign (default: false)
 * @returns {string} Formatted number string
 */
export function formatNumber(value, options = {}) {
  // Handle null/undefined/NaN
  if (value == null || isNaN(value)) return 'N/A'

  const {
    decimals = 0,
    showSign = false,
  } = options

  const sign = showSign && value > 0 ? '+' : ''

  return `${sign}${value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`
}

/**
 * Format number in compact form
 * e.g., 1.2K, 3.5M, 1.2B
 *
 * @param {number} value - Value to format
 * @param {Object} options - Formatting options
 * @param {string} options.prefix - Prefix string (default: '')
 * @param {string} options.suffix - Suffix string (default: '')
 * @param {number} options.decimals - Decimal places (default: 1)
 * @returns {string} Compact number string
 */
export function formatCompact(value, options = {}) {
  // Handle null/undefined/NaN
  if (value == null || isNaN(value)) return 'N/A'

  const {
    prefix = '',
    suffix = '',
    decimals = 1,
  } = options

  const absValue = Math.abs(value)
  const sign = value < 0 ? '-' : ''

  // Define thresholds and suffixes
  const thresholds = [
    { value: 1e12, suffix: 'T' },
    { value: 1e9, suffix: 'B' },
    { value: 1e6, suffix: 'M' },
    { value: 1e3, suffix: 'K' },
    { value: 1, suffix: '' },
  ]

  // Find appropriate threshold
  for (const threshold of thresholds) {
    if (absValue >= threshold.value) {
      const formatted = (absValue / threshold.value).toFixed(decimals)
      return `${sign}${prefix}${formatted}${threshold.suffix}${suffix}`
    }
  }

  return `${sign}${prefix}${absValue.toFixed(decimals)}${suffix}`
}

/**
 * Format ratio value (e.g., Sharpe ratio)
 *
 * @param {number} value - Ratio value
 * @param {number} decimals - Decimal places (default: 2)
 * @returns {string} Formatted ratio
 */
export function formatRatio(value, decimals = 2) {
  if (value == null || isNaN(value)) return 'N/A'
  return value.toFixed(decimals)
}

/**
 * Format integer value
 *
 * @param {number} value - Integer value
 * @returns {string} Formatted integer
 */
export function formatInteger(value) {
  if (value == null || isNaN(value)) return 'N/A'
  return Math.round(value).toLocaleString('en-US')
}

// ============================================================================
// DATE/TIME FORMATTING
// ============================================================================

/**
 * Parse timestamp to Date object
 *
 * @param {string|number|Date} timestamp - Timestamp to parse
 * @returns {Date|null} Parsed Date object or null
 */
export function parseTimestamp(timestamp) {
  if (!timestamp) return null

  // Handle Date objects
  if (timestamp instanceof Date) {
    return isValid(timestamp) ? timestamp : null
  }

  // Handle ISO strings
  if (typeof timestamp === 'string') {
    const parsed = parseISO(timestamp)
    return isValid(parsed) ? parsed : null
  }

  // Handle Unix timestamps
  if (typeof timestamp === 'number') {
    // Check if milliseconds or seconds
    const date = timestamp > 1e12 ? new Date(timestamp) : new Date(timestamp * 1000)
    return isValid(date) ? date : null
  }

  return null
}

/**
 * Parse a backend timestamp as UTC
 *
 * Backend services emit naive UTC ISO strings without an offset
 * (e.g. '2026-08-20T18:37:09.559552'); `new Date()` parses those as
 * LOCAL time. Append 'Z' when no offset is present so the string is
 * interpreted as UTC. Strings already carrying 'Z' or a +HH:MM/-HH:MM
 * offset pass through unchanged, so this stays correct once the
 * backend starts emitting explicit offsets.
 *
 * @param {string|number|Date} timestamp - Timestamp to parse
 * @returns {Date|null} Parsed Date object (UTC for naive strings), or null
 *   for null/undefined/empty input (mirrors parseTimestamp — without this
 *   guard, `new Date(null)` yields the 1970 epoch)
 */
export function parseUtc(timestamp) {
  if (!timestamp) return null

  if (
    typeof timestamp === 'string' &&
    timestamp.includes('T') &&
    !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestamp)
  ) {
    return new Date(`${timestamp}Z`)
  }
  return new Date(timestamp)
}

/**
 * Format timestamp for display
 *
 * @param {string|number|Date} timestamp - Timestamp to format
 * @param {string} formatStr - date-fns format string (default: 'MMM d, yyyy HH:mm')
 * @returns {string} Formatted date string
 */
export function formatTimestamp(timestamp, formatStr = 'MMM d, yyyy HH:mm') {
  const date = parseTimestamp(timestamp)
  if (!date) return 'N/A'
  return format(date, formatStr)
}

/**
 * Format date only (no time)
 *
 * @param {string|number|Date} timestamp - Timestamp to format
 * @returns {string} Formatted date string
 */
export function formatDate(timestamp) {
  return formatTimestamp(timestamp, 'MMM d, yyyy')
}

/**
 * Format time only (no date)
 *
 * @param {string|number|Date} timestamp - Timestamp to format
 * @returns {string} Formatted time string
 */
export function formatTime(timestamp) {
  return formatTimestamp(timestamp, 'HH:mm:ss')
}

/**
 * Format date for charts based on time period
 *
 * @param {string|number|Date} timestamp - Timestamp to format
 * @param {string} period - Time period ('1d', '7d', '30d', '90d', 'all')
 * @returns {string} Formatted date string appropriate for period
 */
export function formatChartDate(timestamp, period = '30d') {
  const date = parseTimestamp(timestamp)
  if (!date) return ''

  const formatMap = {
    '1d': 'HH:mm',
    '7d': 'EEE HH:mm',
    '30d': 'MMM d',
    '90d': 'MMM d',
    '365d': 'MMM d',
    'ytd': 'MMM d',
    'all': 'MMM yyyy',
  }

  return format(date, formatMap[period] || 'MMM d')
}

/**
 * Format relative time (e.g., "2 hours ago")
 *
 * @param {string|number|Date} timestamp - Timestamp to format
 * @param {Date} baseDate - Base date for comparison (default: now)
 * @returns {string} Relative time string
 */
export function formatRelativeTime(timestamp, baseDate = new Date()) {
  const date = parseTimestamp(timestamp)
  if (!date) return 'N/A'
  return formatDistance(date, baseDate, { addSuffix: true })
}

// ============================================================================
// SPECIALIZED FORMATTERS
// ============================================================================

/**
 * Format trade side (BUY/SELL) with proper casing
 *
 * @param {string} side - Trade side
 * @returns {string} Formatted side
 */
export function formatTradeSide(side) {
  if (!side) return 'N/A'
  const normalized = side.toUpperCase()
  return normalized === 'BUY' ? 'Long' : normalized === 'SELL' ? 'Short' : side
}

/**
 * Format trade status
 *
 * @param {string} status - Trade status
 * @returns {string} Formatted status
 */
export function formatTradeStatus(status) {
  if (!status) return 'N/A'

  const statusMap = {
    'OPEN': 'Open',
    'CLOSED': 'Closed',
    'PARTIAL': 'Partial',
    'PENDING': 'Pending',
    'CANCELLED': 'Cancelled',
  }

  return statusMap[status.toUpperCase()] || status
}

/**
 * Format symbol for display (remove USDT suffix)
 *
 * @param {string} symbol - Trading symbol
 * @returns {string} Formatted symbol
 */
export function formatSymbol(symbol) {
  if (!symbol) return 'N/A'
  return symbol.replace(/USDT$/i, '')
}

/**
 * Format quantity with appropriate decimals based on size
 *
 * @param {number} quantity - Quantity value
 * @returns {string} Formatted quantity
 */
export function formatQuantity(quantity) {
  if (quantity == null || isNaN(quantity)) return 'N/A'

  // Use more decimals for smaller quantities
  if (quantity < 0.01) return quantity.toFixed(6)
  if (quantity < 1) return quantity.toFixed(4)
  if (quantity < 100) return quantity.toFixed(2)
  return quantity.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

/**
 * Format price with appropriate decimals based on value
 *
 * @param {number} price - Price value
 * @returns {string} Formatted price
 */
export function formatPrice(price) {
  if (price == null || isNaN(price)) return 'N/A'

  // Use more decimals for smaller prices
  if (price < 1) return `$${price.toFixed(6)}`
  if (price < 100) return `$${price.toFixed(4)}`
  return `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/**
 * Format duration in human-readable form
 *
 * @param {number} milliseconds - Duration in milliseconds
 * @returns {string} Formatted duration
 */
export function formatDuration(milliseconds) {
  if (milliseconds == null || isNaN(milliseconds)) return 'N/A'

  const seconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) return `${days}d ${hours % 24}h`
  if (hours > 0) return `${hours}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`
  return `${seconds}s`
}

// ============================================================================
// VALUE GETTERS FOR COLOR CODING
// ============================================================================

/**
 * Get color class based on P&L value
 *
 * @param {number} value - P&L value
 * @returns {string} Tailwind color class
 */
export function getPnLColorClass(value) {
  if (value == null) return 'text-slate-400'
  if (value > 0) return 'text-emerald-400'
  if (value < 0) return 'text-rose-400'
  return 'text-slate-400'
}

/**
 * Get background color class based on P&L value
 *
 * @param {number} value - P&L value
 * @returns {string} Tailwind background color class
 */
export function getPnLBgClass(value) {
  if (value == null) return 'bg-slate-500/20'
  if (value > 0) return 'bg-emerald-500/20'
  if (value < 0) return 'bg-rose-500/20'
  return 'bg-slate-500/20'
}

/**
 * Get color for trade side
 *
 * @param {string} side - Trade side (BUY/SELL)
 * @returns {string} Tailwind color class
 */
export function getSideColorClass(side) {
  if (!side) return 'text-slate-400'
  const normalized = side.toUpperCase()
  return normalized === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
}

// ============================================================================
// EXPORTS
// ============================================================================

export default {
  // Currency
  formatCurrency,
  formatPnL,
  formatCurrencyCompact,

  // Percentage
  formatPercent,
  formatWinRate,
  formatChange,

  // Number
  formatNumber,
  formatCompact,
  formatRatio,
  formatInteger,

  // Date/Time
  parseUtc,
  parseTimestamp,
  formatTimestamp,
  formatDate,
  formatTime,
  formatChartDate,
  formatRelativeTime,

  // Specialized
  formatTradeSide,
  formatTradeStatus,
  formatSymbol,
  formatQuantity,
  formatPrice,
  formatDuration,

  // Color classes
  getPnLColorClass,
  getPnLBgClass,
  getSideColorClass,
}
