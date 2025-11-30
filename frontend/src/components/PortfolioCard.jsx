import React from 'react'
import { usePositions, useTradingStatus, usePerformance } from '../hooks/usePositions'

/**
 * PortfolioCard component displays current portfolio status
 * Shows: cash balance, total P&L, positions, and exposure
 *
 * Data sources:
 * - Performance data: /api/trading/performance (trading-engine service) - for balance
 * - Trading positions: /api/trading/positions (trading-engine service) - for open positions
 * - Trading status: /api/trading/status (trading-engine service) - for bot status
 *
 * UPDATED 2025-11-28: Now uses trading-engine performance for correct balance tracking
 */
export default function PortfolioCard() {
  // Fetch performance data from trading-engine (correct balance!)
  const { data: performanceData, isLoading: performanceLoading, error: performanceError } = usePerformance()

  // Fetch trading positions from trading-engine
  const { data: positionsData, isLoading: positionsLoading, error: positionsError } = usePositions()

  // Fetch trading status
  const { data: statusData, isLoading: statusLoading } = useTradingStatus()

  // Debug logging for data flow
  console.log('[PortfolioCard] Data state:', {
    performanceData,
    positionsData,
    statusData,
    performanceLoading,
    positionsLoading,
    performanceError: performanceError?.message,
    positionsError: positionsError?.message
  })

  // Combined loading state
  const isLoading = performanceLoading || positionsLoading

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="space-y-3">
            <div className="h-4 bg-gray-200 rounded"></div>
            <div className="h-4 bg-gray-200 rounded w-5/6"></div>
          </div>
        </div>
      </div>
    )
  }

  if (performanceError && positionsError) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-red-600">
          <h3 className="font-semibold mb-2">Error Loading Portfolio</h3>
          <p className="text-sm">{performanceError?.message || positionsError?.message}</p>
        </div>
      </div>
    )
  }

  // Extract performance metrics from trading-engine (correct balance source!)
  const metrics = performanceData?.metrics || {}

  // Extract trading positions from trading-engine
  // API returns: { success: true, positions: [...], count: N }
  const positions = positionsData?.positions || []

  // Extract trading status
  const tradingStatus = statusData?.status || {}

  // Get balance data from trading-engine performance (correct values!)
  const cashBalance = parseFloat(metrics.current_balance) || 10000
  const initialBalance = parseFloat(metrics.initial_balance) || 10000
  const totalPnl = parseFloat(metrics.total_pnl) || 0
  const roi = parseFloat(metrics.roi) || 0

  // Calculate unrealized PnL from trading positions (live prices!)
  const unrealizedPnl = positions.reduce((sum, pos) => {
    return sum + (parseFloat(pos.unrealized_pnl) || 0)
  }, 0)

  // Calculate total exposure from trading positions (using current_price * quantity)
  const totalExposure = positions.reduce((sum, pos) => {
    const currentPrice = parseFloat(pos.current_price) || parseFloat(pos.entry_price) || 0
    const quantity = parseFloat(pos.quantity) || 0
    return sum + (currentPrice * quantity)
  }, 0)

  // Total value = cash + positions value
  const totalValue = cashBalance + totalExposure

  // Calculate exposure percentage
  const exposurePercentage = initialBalance > 0 ? (totalExposure / initialBalance * 100) : 0

  // Calculate P&L percentage
  const totalPnlPct = roi

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Portfolio</h2>
        <div className="flex items-center space-x-3">
          {/* Trading Bot Status Indicator */}
          {tradingStatus.is_running !== undefined && (
            <div className={`flex items-center space-x-1 px-2 py-1 rounded-full text-xs font-medium ${
              tradingStatus.is_running
                ? 'bg-green-100 text-green-800'
                : 'bg-red-100 text-red-800'
            }`}>
              <div className={`w-2 h-2 rounded-full ${
                tradingStatus.is_running ? 'bg-green-500 animate-pulse' : 'bg-red-500'
              }`}></div>
              <span>{tradingStatus.is_running ? 'Bot Running' : 'Bot Stopped'}</span>
            </div>
          )}
          <div className="text-sm text-gray-500">
            Last updated: {new Date().toLocaleTimeString()}
          </div>
        </div>
      </div>

      {/* Balance Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Initial Balance</p>
          <p className="text-xl font-bold text-gray-500">
            ${initialBalance.toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Cash Balance</p>
          <p className="text-xl font-bold text-gray-800">
            ${cashBalance.toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">In Positions</p>
          <p className="text-xl font-bold text-blue-600">
            ${totalExposure.toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Total Equity</p>
          <p className="text-xl font-bold text-gray-800">
            ${totalValue.toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Unrealized P&L</p>
          <p className={`text-xl font-bold ${unrealizedPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Exposure Bar */}
      <div className="mb-6">
        <div className="flex justify-between items-center mb-2">
          <p className="text-sm text-gray-600">Total Exposure</p>
          <p className="text-sm font-semibold text-gray-800">
            {exposurePercentage.toFixed(1)}%
          </p>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className={`h-3 rounded-full transition-all duration-300 ${
              exposurePercentage > 80 ? 'bg-red-500' :
              exposurePercentage > 50 ? 'bg-yellow-500' :
              'bg-green-500'
            }`}
            style={{ width: `${Math.min(exposurePercentage, 100)}%` }}
          ></div>
        </div>
      </div>

      {/* Trading Stats (if available) */}
      {tradingStatus.total_trades_executed !== undefined && (
        <div className="mb-6 p-4 bg-blue-50 rounded-lg">
          <h3 className="text-sm font-semibold text-blue-800 mb-2">Trading Activity</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-blue-600">Signals Checked:</span>
              <span className="ml-2 font-bold">{tradingStatus.total_signals_checked || 0}</span>
            </div>
            <div>
              <span className="text-blue-600">Trades Executed:</span>
              <span className="ml-2 font-bold text-green-600">{tradingStatus.total_trades_executed || 0}</span>
            </div>
            <div>
              <span className="text-blue-600">Trades Rejected:</span>
              <span className="ml-2 font-bold text-red-600">{tradingStatus.total_trades_rejected || 0}</span>
            </div>
            <div>
              <span className="text-blue-600">Last Check:</span>
              <span className="ml-2 font-bold">
                {tradingStatus.last_check_time
                  ? new Date(tradingStatus.last_check_time).toLocaleTimeString()
                  : 'N/A'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Positions */}
      <div>
        <h3 className="text-lg font-semibold text-gray-800 mb-3">
          Active Positions ({positions.length})
        </h3>

        {positions.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <p>No active positions</p>
            <p className="text-sm mt-1">Trading bot will open positions when signals are detected</p>
          </div>
        ) : (
          <div className="space-y-3">
            {positions.map((position, index) => {
              // Handle both trading-engine and portfolio-manager position formats
              const symbol = position.symbol || 'Unknown'
              const side = position.side || 'LONG'
              const quantity = parseFloat(position.quantity) || 0
              const entryPrice = parseFloat(position.entry_price) || parseFloat(position.avg_entry_price) || 0
              const currentPrice = parseFloat(position.current_price) || entryPrice
              const stopLoss = parseFloat(position.stop_loss) || 0
              const takeProfit = parseFloat(position.take_profit) || 0
              const unrealizedPnl = parseFloat(position.unrealized_pnl) || 0
              const pnlPct = entryPrice > 0
                ? ((currentPrice - entryPrice) / entryPrice * 100) * (side === 'SHORT' ? -1 : 1)
                : 0
              const positionValue = currentPrice * quantity
              const openedAt = position.opened_at ? new Date(position.opened_at) : null

              return (
                <div
                  key={position.id || index}
                  className={`border-2 rounded-lg p-4 hover:shadow-md transition-shadow ${
                    side === 'LONG' ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
                  }`}
                >
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center space-x-2">
                      <h4 className="font-semibold text-gray-800 text-lg">{symbol}</h4>
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        side === 'LONG'
                          ? 'bg-green-600 text-white'
                          : 'bg-red-600 text-white'
                      }`}>
                        {side}
                      </span>
                      {position.strategy && (
                        <span className="px-2 py-1 rounded text-xs bg-blue-100 text-blue-800">
                          {position.strategy}
                        </span>
                      )}
                    </div>
                    <div className="text-right">
                      <p className={`font-bold text-lg ${unrealizedPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${unrealizedPnl.toFixed(2)}
                      </p>
                      <p className={`text-sm ${pnlPct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <span className="text-gray-600">Quantity:</span>
                      <p className="font-semibold">{quantity.toFixed(8)}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Entry Price:</span>
                      <p className="font-semibold">${entryPrice.toFixed(2)}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Current Price:</span>
                      <p className="font-semibold">${currentPrice.toFixed(2)}</p>
                    </div>
                    <div>
                      <span className="text-gray-600">Position Value:</span>
                      <p className="font-semibold">${positionValue.toFixed(2)}</p>
                    </div>
                  </div>

                  {/* Stop Loss / Take Profit */}
                  {(stopLoss > 0 || takeProfit > 0) && (
                    <div className="mt-3 pt-3 border-t border-gray-200 flex justify-between text-sm">
                      {stopLoss > 0 && (
                        <div>
                          <span className="text-red-600 font-medium">Stop Loss:</span>
                          <span className="ml-2 font-semibold">${stopLoss.toFixed(2)}</span>
                        </div>
                      )}
                      {takeProfit > 0 && (
                        <div>
                          <span className="text-green-600 font-medium">Take Profit:</span>
                          <span className="ml-2 font-semibold">${takeProfit.toFixed(2)}</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Opened At */}
                  {openedAt && (
                    <div className="mt-2 text-xs text-gray-500">
                      Opened: {openedAt.toLocaleString()}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
