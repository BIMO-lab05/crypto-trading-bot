import React from 'react'
import PortfolioCard from './PortfolioCard'
import PriceTickerGrid from './PriceTickerGrid'
import EmergencyStop from './EmergencyStop'
import TradingSignals from './TradingSignals'
import PriceChart from './PriceChart'

/**
 * Dashboard component - Main layout for the trading bot interface
 * Combines all major components into a cohesive dashboard view
 *
 * Components included:
 * - PriceTickerGrid: Real-time price tickers for multiple symbols
 * - TradingSignals: Technical analysis signals
 * - PriceChart: 24-hour price chart with volume visualization
 * - PortfolioCard: Current holdings and balance
 * - EmergencyStop: Safety mechanism to stop all trading
 */
export default function Dashboard() {
  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-primary-500 rounded-lg flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-white"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                  />
                </svg>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  Crypto Trading Bot
                </h1>
                <p className="text-sm text-gray-500">Paper Trading Mode</p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              {/* System Status Indicator */}
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm font-medium text-gray-700">
                  System Online
                </span>
              </div>

              {/* Date & Time */}
              <div className="hidden md:block text-sm text-gray-600">
                {new Date().toLocaleDateString('en-US', {
                  weekday: 'short',
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">
          {/* Price Tickers - Top Section */}
          <section>
            <PriceTickerGrid symbols={['BTCUSDT', 'ETHUSDT', 'BNBUSDT']} />
          </section>

          {/* Price Chart - Second Section */}
          <section>
            <PriceChart symbol="BTCUSDT" interval="60" />
          </section>

          {/* Trading Signals - Third Section */}
          <section>
            <TradingSignals symbols={['BTCUSDT', 'ETHUSDT', 'BNBUSDT']} interval={60} />
          </section>

          {/* Portfolio and Emergency Stop - Fourth Section */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <PortfolioCard />
            </div>

            <div className="lg:col-span-1">
              <EmergencyStop />
            </div>
          </section>

          {/* Information Banner */}
          <section className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <svg
                className="h-6 w-6 text-blue-600 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-blue-900 mb-1">
                  Paper Trading Mode Active
                </h3>
                <p className="text-sm text-blue-800">
                  This dashboard is connected to a paper trading bot using virtual funds ($10,000 starting capital).
                  No real money is at risk. The bot analyzes BTC, ETH, and BNB markets every 5 minutes and executes
                  trades based on technical analysis signals with 65%+ confidence.
                </p>
                <p className="text-xs text-blue-700 mt-2">
                  Data refreshes automatically every 3-5 seconds. Check logs at <code className="bg-blue-100 px-1 rounded">logs/trading_bot.log</code> for detailed activity.
                </p>
              </div>
            </div>
          </section>

          {/* Trading Bot Status */}
          <section className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">
              Trading Bot Configuration
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Check Interval</p>
                <p className="text-lg font-bold text-gray-800">5 minutes</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Max Position Size</p>
                <p className="text-lg font-bold text-gray-800">2% per trade</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Stop Loss</p>
                <p className="text-lg font-bold text-red-600">-3%</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Take Profit</p>
                <p className="text-lg font-bold text-green-600">+6%</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Daily Loss Limit</p>
                <p className="text-lg font-bold text-gray-800">5%</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Max Exposure</p>
                <p className="text-lg font-bold text-gray-800">20%</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Signal Confidence</p>
                <p className="text-lg font-bold text-gray-800">≥ 65%</p>
              </div>

              <div className="bg-gray-50 rounded p-3">
                <p className="text-xs text-gray-600 mb-1">Max Trades/Day</p>
                <p className="text-lg font-bold text-gray-800">20</p>
              </div>
            </div>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between text-sm text-gray-600">
            <p>
              Crypto Trading Bot Dashboard • Version 1.0.0
            </p>
            <p>
              Backend: <span className="font-medium text-green-600">Connected</span>
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
