/**
 * useChartData.js - Chart Data Transformation Hook
 *
 * Purpose: Custom hook for transforming raw API data into chart-ready formats.
 * Handles aggregation, interpolation, and formatting for various chart types.
 *
 * Features:
 * - Equity curve data transformation
 * - Daily P&L aggregation
 * - Returns distribution calculation
 * - Rolling metrics computation
 * - Data interpolation for missing points
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import { useMemo, useCallback } from 'react'
import {
  format,
  parseISO,
  isValid,
  startOfDay,
  eachDayOfInterval,
  eachHourOfInterval,
  differenceInDays,
} from 'date-fns'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Parse timestamp to Date object
 *
 * @param {string|number|Date} timestamp - Timestamp to parse
 * @returns {Date|null} Parsed Date or null
 */
function parseTimestamp(timestamp) {
  if (!timestamp) return null

  if (timestamp instanceof Date) {
    return isValid(timestamp) ? timestamp : null
  }

  if (typeof timestamp === 'string') {
    const parsed = parseISO(timestamp)
    return isValid(parsed) ? parsed : null
  }

  if (typeof timestamp === 'number') {
    const date = timestamp > 1e12 ? new Date(timestamp) : new Date(timestamp * 1000)
    return isValid(date) ? date : null
  }

  return null
}

/**
 * Group data by time interval
 *
 * @param {Array} data - Data array with timestamps
 * @param {string} interval - Grouping interval ('hour', 'day', 'week', 'month')
 * @returns {Map} Grouped data by interval key
 */
function groupByInterval(data, interval = 'day') {
  const groups = new Map()

  const formatMap = {
    hour: 'yyyy-MM-dd HH:00',
    day: 'yyyy-MM-dd',
    week: 'yyyy-ww',
    month: 'yyyy-MM',
  }

  const formatStr = formatMap[interval] || formatMap.day

  data.forEach((item) => {
    const date = parseTimestamp(item.timestamp || item.closed_at || item.date)
    if (!date) return

    const key = format(date, formatStr)

    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key).push(item)
  })

  return groups
}

// ============================================================================
// MAIN HOOK
// ============================================================================

/**
 * useChartData - Chart Data Transformation Hook
 *
 * @param {Object} options - Hook options
 * @param {Array} options.trades - Trade history data
 * @param {Array} options.equityCurve - Equity curve data
 * @param {number} options.initialBalance - Initial balance for calculations
 * @param {string} options.period - Time period for aggregation
 * @returns {Object} Transformed chart data
 */
export function useChartData(options = {}) {
  const {
    trades = [],
    equityCurve = [],
    initialBalance = 10000,
    period = '30d',
  } = options

  // ============================================================================
  // EQUITY CURVE DATA
  // ============================================================================

  /**
   * Process equity curve for area chart
   */
  const equityChartData = useMemo(() => {
    if (equityCurve.length === 0) {
      // Generate from trades if equity curve not provided
      if (trades.length === 0) {
        return [{
          timestamp: Date.now(),
          equity: initialBalance,
          pnl: 0,
          cumulativePnl: 0,
        }]
      }

      // Sort trades by close time
      const sortedTrades = [...trades].sort((a, b) => {
        const dateA = parseTimestamp(a.closed_at || a.timestamp)
        const dateB = parseTimestamp(b.closed_at || b.timestamp)
        return (dateA || 0) - (dateB || 0)
      })

      let cumEquity = initialBalance
      const data = [{
        timestamp: sortedTrades[0]?.closed_at || Date.now(),
        equity: initialBalance,
        pnl: 0,
        cumulativePnl: 0,
        tradeCount: 0,
      }]

      sortedTrades.forEach((trade, index) => {
        const pnl = parseFloat(trade.realized_pnl || 0)
        cumEquity += pnl

        data.push({
          timestamp: trade.closed_at || trade.timestamp,
          equity: cumEquity,
          pnl,
          cumulativePnl: cumEquity - initialBalance,
          tradeCount: index + 1,
        })
      })

      return data
    }

    return equityCurve.map((point) => ({
      timestamp: point.timestamp,
      equity: point.equity,
      pnl: point.pnl || 0,
      cumulativePnl: point.cumulativePnl || (point.equity - initialBalance),
      tradeCount: point.tradeCount || 0,
    }))
  }, [equityCurve, trades, initialBalance])

  // ============================================================================
  // DAILY P&L DATA
  // ============================================================================

  /**
   * Aggregate P&L by day for bar chart
   */
  const dailyPnLData = useMemo(() => {
    if (trades.length === 0) return []

    // Group trades by day
    const grouped = groupByInterval(trades, 'day')

    // Aggregate P&L for each day
    const dailyData = []

    grouped.forEach((dayTrades, dateKey) => {
      const totalPnL = dayTrades.reduce((sum, trade) => {
        return sum + parseFloat(trade.realized_pnl || 0)
      }, 0)

      const winCount = dayTrades.filter((t) => parseFloat(t.realized_pnl || 0) > 0).length
      const lossCount = dayTrades.filter((t) => parseFloat(t.realized_pnl || 0) < 0).length

      dailyData.push({
        date: dateKey,
        timestamp: parseISO(dateKey).getTime(),
        pnl: totalPnL,
        tradeCount: dayTrades.length,
        winCount,
        lossCount,
        winRate: dayTrades.length > 0 ? (winCount / dayTrades.length) * 100 : 0,
      })
    })

    // Sort by date
    return dailyData.sort((a, b) => a.timestamp - b.timestamp)
  }, [trades])

  /**
   * Calculate cumulative daily P&L
   */
  const cumulativeDailyPnL = useMemo(() => {
    let cumulative = 0
    return dailyPnLData.map((day) => {
      cumulative += day.pnl
      return {
        ...day,
        cumulativePnl: cumulative,
      }
    })
  }, [dailyPnLData])

  // ============================================================================
  // RETURNS DISTRIBUTION DATA
  // ============================================================================

  /**
   * Calculate returns distribution for histogram
   */
  const returnsDistribution = useMemo(() => {
    if (trades.length === 0) {
      return { bins: [], stats: null }
    }

    // Extract P&L values
    const returns = trades
      .filter((t) => t.realized_pnl != null)
      .map((t) => parseFloat(t.realized_pnl))

    if (returns.length === 0) {
      return { bins: [], stats: null }
    }

    // Calculate statistics
    const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length
    const stdDev = Math.sqrt(variance)
    const min = Math.min(...returns)
    const max = Math.max(...returns)
    const sortedReturns = [...returns].sort((a, b) => a - b)
    const median = sortedReturns[Math.floor(returns.length / 2)]

    // Calculate skewness
    const skewness = stdDev !== 0
      ? returns.reduce((sum, r) => sum + Math.pow((r - mean) / stdDev, 3), 0) / returns.length
      : 0

    // Calculate kurtosis
    const kurtosis = stdDev !== 0
      ? returns.reduce((sum, r) => sum + Math.pow((r - mean) / stdDev, 4), 0) / returns.length - 3
      : 0

    // Create histogram bins (20 bins)
    const binCount = 20
    const binWidth = (max - min) / binCount
    const bins = []

    for (let i = 0; i < binCount; i++) {
      const binStart = min + i * binWidth
      const binEnd = binStart + binWidth
      const count = returns.filter((r) =>
        r >= binStart && (i === binCount - 1 ? r <= binEnd : r < binEnd)
      ).length

      bins.push({
        binStart,
        binEnd,
        binMid: (binStart + binEnd) / 2,
        count,
        frequency: count / returns.length,
      })
    }

    return {
      bins,
      stats: {
        count: returns.length,
        mean,
        median,
        stdDev,
        variance,
        min,
        max,
        skewness,
        kurtosis,
        range: max - min,
      },
    }
  }, [trades])

  // ============================================================================
  // ROLLING METRICS DATA
  // ============================================================================

  /**
   * Calculate rolling Sharpe ratio (30-day window)
   */
  const rollingSharpeData = useMemo(() => {
    if (dailyPnLData.length < 10) return []

    const windowSize = 30
    const rollingData = []

    for (let i = windowSize - 1; i < dailyPnLData.length; i++) {
      const window = dailyPnLData.slice(i - windowSize + 1, i + 1)
      const returns = window.map((d) => d.pnl)

      const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length
      const stdDev = Math.sqrt(variance)

      // Annualize Sharpe (assuming daily data, ~252 trading days)
      const sharpe = stdDev !== 0 ? (mean / stdDev) * Math.sqrt(252) : 0

      rollingData.push({
        date: dailyPnLData[i].date,
        timestamp: dailyPnLData[i].timestamp,
        sharpe,
      })
    }

    return rollingData
  }, [dailyPnLData])

  /**
   * Calculate rolling win rate (30-day window)
   */
  const rollingWinRateData = useMemo(() => {
    if (dailyPnLData.length < 10) return []

    const windowSize = 30
    const rollingData = []

    for (let i = windowSize - 1; i < dailyPnLData.length; i++) {
      const window = dailyPnLData.slice(i - windowSize + 1, i + 1)

      const totalTrades = window.reduce((sum, d) => sum + d.tradeCount, 0)
      const totalWins = window.reduce((sum, d) => sum + d.winCount, 0)

      const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0

      rollingData.push({
        date: dailyPnLData[i].date,
        timestamp: dailyPnLData[i].timestamp,
        winRate,
        tradeCount: totalTrades,
      })
    }

    return rollingData
  }, [dailyPnLData])

  // ============================================================================
  // STRATEGY PERFORMANCE DATA
  // ============================================================================

  /**
   * Aggregate performance by strategy
   */
  const strategyPerformance = useMemo(() => {
    if (trades.length === 0) return []

    // Group trades by strategy
    const strategyMap = new Map()

    trades.forEach((trade) => {
      const strategy = trade.strategy || trade.signal_source || 'Unknown'

      if (!strategyMap.has(strategy)) {
        strategyMap.set(strategy, {
          strategy,
          trades: [],
          totalPnL: 0,
          winCount: 0,
          lossCount: 0,
        })
      }

      const strategyData = strategyMap.get(strategy)
      const pnl = parseFloat(trade.realized_pnl || 0)

      strategyData.trades.push(trade)
      strategyData.totalPnL += pnl

      if (pnl > 0) strategyData.winCount++
      else if (pnl < 0) strategyData.lossCount++
    })

    // Calculate metrics for each strategy
    return Array.from(strategyMap.values()).map((data) => {
      const tradeCount = data.trades.length
      const winRate = tradeCount > 0 ? (data.winCount / tradeCount) * 100 : 0

      // Calculate profit factor
      const grossProfit = data.trades
        .filter((t) => parseFloat(t.realized_pnl || 0) > 0)
        .reduce((sum, t) => sum + parseFloat(t.realized_pnl), 0)

      const grossLoss = Math.abs(
        data.trades
          .filter((t) => parseFloat(t.realized_pnl || 0) < 0)
          .reduce((sum, t) => sum + parseFloat(t.realized_pnl), 0)
      )

      const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0

      return {
        strategy: data.strategy,
        pnl: data.totalPnL,
        trades: tradeCount,
        winRate,
        profitFactor: profitFactor === Infinity ? 999 : profitFactor,
        avgWin: data.winCount > 0 ? grossProfit / data.winCount : 0,
        avgLoss: data.lossCount > 0 ? grossLoss / data.lossCount : 0,
      }
    }).sort((a, b) => b.pnl - a.pnl)
  }, [trades])

  // ============================================================================
  // SYMBOL PERFORMANCE DATA
  // ============================================================================

  /**
   * Aggregate performance by symbol
   */
  const symbolPerformance = useMemo(() => {
    if (trades.length === 0) return []

    // Group trades by symbol
    const symbolMap = new Map()

    trades.forEach((trade) => {
      const symbol = trade.symbol || 'Unknown'

      if (!symbolMap.has(symbol)) {
        symbolMap.set(symbol, {
          symbol,
          totalPnL: 0,
          tradeCount: 0,
          winCount: 0,
        })
      }

      const symbolData = symbolMap.get(symbol)
      const pnl = parseFloat(trade.realized_pnl || 0)

      symbolData.totalPnL += pnl
      symbolData.tradeCount++

      if (pnl > 0) symbolData.winCount++
    })

    return Array.from(symbolMap.values()).map((data) => ({
      symbol: data.symbol,
      pnl: data.totalPnL,
      trades: data.tradeCount,
      winRate: data.tradeCount > 0 ? (data.winCount / data.tradeCount) * 100 : 0,
    })).sort((a, b) => b.pnl - a.pnl)
  }, [trades])

  // ============================================================================
  // UTILITY FUNCTIONS
  // ============================================================================

  /**
   * Get data for specific date range
   */
  const getDataForRange = useCallback((startDate, endDate) => {
    const start = parseTimestamp(startDate)
    const end = parseTimestamp(endDate)

    if (!start || !end) return equityChartData

    return equityChartData.filter((point) => {
      const date = parseTimestamp(point.timestamp)
      return date && date >= start && date <= end
    })
  }, [equityChartData])

  /**
   * Calculate summary stats for data range
   */
  const getSummaryForRange = useCallback((startDate, endDate) => {
    const data = getDataForRange(startDate, endDate)

    if (data.length === 0) {
      return {
        startEquity: initialBalance,
        endEquity: initialBalance,
        totalPnL: 0,
        percentChange: 0,
        high: initialBalance,
        low: initialBalance,
      }
    }

    const equities = data.map((d) => d.equity)
    const startEquity = equities[0]
    const endEquity = equities[equities.length - 1]

    return {
      startEquity,
      endEquity,
      totalPnL: endEquity - startEquity,
      percentChange: startEquity > 0 ? ((endEquity - startEquity) / startEquity) * 100 : 0,
      high: Math.max(...equities),
      low: Math.min(...equities),
    }
  }, [getDataForRange, initialBalance])

  // ============================================================================
  // RETURN VALUE
  // ============================================================================

  return {
    // Core chart data
    equityChartData,
    dailyPnLData,
    cumulativeDailyPnL,

    // Distribution data
    returnsDistribution,

    // Rolling metrics
    rollingSharpeData,
    rollingWinRateData,

    // Aggregated performance
    strategyPerformance,
    symbolPerformance,

    // Utility functions
    getDataForRange,
    getSummaryForRange,

    // Data availability flags
    hasData: trades.length > 0 || equityCurve.length > 0,
    tradeCount: trades.length,
    dataPointCount: equityChartData.length,
  }
}

// ============================================================================
// SPECIALIZED HOOKS
// ============================================================================

/**
 * useDailyPnLChart - Specialized hook for daily P&L bar chart
 */
export function useDailyPnLChart(trades = []) {
  return useMemo(() => {
    if (trades.length === 0) return []

    const grouped = groupByInterval(trades, 'day')
    const dailyData = []

    grouped.forEach((dayTrades, dateKey) => {
      const wins = dayTrades.filter((t) => parseFloat(t.realized_pnl || 0) > 0)
      const losses = dayTrades.filter((t) => parseFloat(t.realized_pnl || 0) < 0)

      const grossProfit = wins.reduce((sum, t) => sum + parseFloat(t.realized_pnl), 0)
      const grossLoss = Math.abs(losses.reduce((sum, t) => sum + parseFloat(t.realized_pnl), 0))

      dailyData.push({
        date: dateKey,
        timestamp: parseISO(dateKey).getTime(),
        profit: grossProfit,
        loss: -grossLoss,
        net: grossProfit - grossLoss,
        tradeCount: dayTrades.length,
        winCount: wins.length,
        lossCount: losses.length,
      })
    })

    return dailyData.sort((a, b) => a.timestamp - b.timestamp)
  }, [trades])
}

/**
 * useRollingSharpe - Specialized hook for rolling Sharpe chart
 */
export function useRollingSharpe(dailyPnLData = [], windowSize = 30) {
  return useMemo(() => {
    if (dailyPnLData.length < windowSize) return []

    const rollingData = []

    for (let i = windowSize - 1; i < dailyPnLData.length; i++) {
      const window = dailyPnLData.slice(i - windowSize + 1, i + 1)
      const returns = window.map((d) => d.pnl || d.net || 0)

      const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length
      const stdDev = Math.sqrt(variance)

      const sharpe = stdDev !== 0 ? (mean / stdDev) * Math.sqrt(252) : 0

      rollingData.push({
        date: dailyPnLData[i].date,
        timestamp: dailyPnLData[i].timestamp,
        sharpe,
      })
    }

    return rollingData
  }, [dailyPnLData, windowSize])
}

// Default export
export default useChartData
