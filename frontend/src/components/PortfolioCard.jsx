import React from 'react'
import { usePortfolio } from '../hooks/usePortfolio'

/**
 * PortfolioCard component displays current portfolio status
 * Shows: cash balance, total P&L, positions, and exposure
 */
export default function PortfolioCard() {
  const { data, isLoading, error } = usePortfolio()

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

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-red-600">
          <h3 className="font-semibold mb-2">Error Loading Portfolio</h3>
          <p className="text-sm">{error.message}</p>
        </div>
      </div>
    )
  }

  const portfolio = data?.portfolio || {}
  // API returns "holdings" not "positions" - fix field name
  const positions = portfolio.holdings || []

  // Convert string values to numbers (API returns strings)
  const totalPnl = parseFloat(portfolio.total_pnl) || 0
  const totalPnlPct = parseFloat(portfolio.total_pnl_percentage) || parseFloat(portfolio.total_return_pct) || 0
  const cashBalance = parseFloat(portfolio.cash_balance) || 0
  const totalValue = parseFloat(portfolio.total_value) || 0

  // Calculate total exposure
  const totalExposure = positions.reduce((sum, pos) => sum + (parseFloat(pos.current_value) || 0), 0)
  const exposurePercentage = totalValue > 0 ? (totalExposure / totalValue * 100) : 0

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Portfolio</h2>
        <div className="text-sm text-gray-500">
          Last updated: {new Date().toLocaleTimeString()}
        </div>
      </div>

      {/* Balance Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Cash Balance</p>
          <p className="text-2xl font-bold text-gray-800">
            ${cashBalance.toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Total Value</p>
          <p className="text-2xl font-bold text-gray-800">
            ${totalValue.toFixed(2)}
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-1">Total P&L</p>
          <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            ${totalPnl.toFixed(2)}
            <span className="text-sm ml-2">
              ({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(2)}%)
            </span>
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
              const pnl = position.unrealized_pnl || 0
              const pnlPct = position.unrealized_pnl_percentage || 0

              return (
                <div
                  key={index}
                  className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h4 className="font-semibold text-gray-800">{position.symbol}</h4>
                      <p className="text-sm text-gray-600">
                        {position.quantity} @ ${position.avg_entry_price?.toFixed(2) || '0.00'}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={`font-semibold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${pnl.toFixed(2)}
                      </p>
                      <p className={`text-sm ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-sm text-gray-600">
                    <div>
                      <span className="font-medium">Current:</span> ${position.current_price?.toFixed(2) || '0.00'}
                    </div>
                    <div>
                      <span className="font-medium">Value:</span> ${position.current_value?.toFixed(2) || '0.00'}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
