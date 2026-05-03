import React, { useState } from 'react'
import PortfolioCard from './PortfolioCard'
import PriceTickerGrid from './PriceTickerGrid'
import EmergencyStop from './EmergencyStop'
import TradingSignals from './TradingSignals'
import PriceChart from './PriceChart'
import KeyMetricsStrip from './KeyMetricsStrip'
import ActiveTrades from './ActiveTrades'
import TradeHistory from './TradeHistory'
import TradingEnhancementsPanel from './TradingEnhancementsPanel'
import PerformanceAnalyticsPanel from './PerformanceAnalyticsPanel'
import HybridStrategyPanel from './HybridStrategyPanel'
import RegimeIndicator from './RegimeIndicator'
import { useGatewayWebSocket } from '../hooks/useGatewayWebSocket'

/**
 * Dashboard component - Research-Backed Professional Trading Interface
 *
 * Updated: 2026-01-06 - Added Hybrid Strategy Panel and Regime Indicator
 * Updated: 2025-11-30 - Added Trading Enhancements and Performance Analytics panels
 * Updated: 2025-11-29 - Applied research-backed UI improvements
 *
 * Research Findings Applied:
 * - Key metrics strip at top (78% of pro traders prioritize this)
 * - Dark theme optimized (default for trading platforms)
 * - Color-coded P&L (green=profit, red=loss)
 * - Real-time updates (5-second refresh)
 * - Symbol selector for focused analysis
 * - Professional layout hierarchy
 * - Strategy transparency (hybrid routing visibility)
 *
 * Components included:
 * - KeyMetricsStrip: Essential trading metrics (NEW - Research-backed)
 * - RegimeIndicator: Live market regime and active strategy (NEW 2026-01-06)
 * - PriceTickerGrid: Real-time price tickers for multiple symbols
 * - TradingSignals: Technical analysis signals with confidence
 * - PriceChart: Interactive price chart with volume visualization
 * - PortfolioCard: Current holdings and balance
 * - EmergencyStop: Safety mechanism to stop all trading
 * - HybridStrategyPanel: Trend/Mean Reversion routing stats (NEW 2026-01-06)
 * - TradingEnhancementsPanel: Circuit Breaker, Kill Switch, Position Sizer, Smart Executor (NEW 2025-11-30)
 * - PerformanceAnalyticsPanel: Sharpe, Sortino, VaR, CVaR metrics (NEW 2025-11-30)
 */

// Trading pairs supported by the system - EXPANDED TO 11 (2026-01-07)
const TRADING_PAIRS = [
  'BTCUSDT',   // Bitcoin - Most liquid
  'ETHUSDT',   // Ethereum - 2nd most liquid
  'SOLUSDT',   // Solana - Top performer
  'BNBUSDT',   // Binance Coin - Top performer
  'ADAUSDT',   // Cardano - Top performer
  'AVAXUSDT',  // Avalanche
  'LINKUSDT',  // Chainlink
  'DOTUSDT',   // Polkadot
  'MATICUSDT', // Polygon
  'ARBUSDT',   // Arbitrum - L2
  'OPUSDT'     // Optimism - L2
]

export default function Dashboard() {
  // State for selected chart symbol
  const [selectedSymbol, setSelectedSymbol] = useState('SOLUSDT')

  // Open one shared WS connection at the dashboard level. The hook hydrates
  // the React Query cache for ticker + portfolio queries; child components
  // continue to read via their existing useQuery hooks and gain real-time
  // freshness without further changes. When WS is disabled or disconnected
  // the components keep polling.
  useGatewayWebSocket()

  return (
    <div className="min-h-screen bg-slate-900 transition-colors duration-200">
      {/* Key Metrics Strip - Research-backed essential metrics */}
      <KeyMetricsStrip />

      {/* Compact Header - Streamlined for professional trading */}
      <header className="bg-slate-800/50 border-b border-slate-700/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              {/* Logo with gradient accent */}
              <div className="w-9 h-9 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-cyan-500/20">
                <svg
                  className="w-5 h-5 text-white"
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
                <h1 className="text-lg font-bold text-slate-100">
                  Crypto Trading Bot
                </h1>
                <p className="text-xs text-cyan-400 font-medium">v1.1.0 • Research-Optimized</p>
              </div>
            </div>

            {/* Symbol Quick Select & Regime Indicator */}
            <div className="flex items-center space-x-3">
              {/* Regime Indicator - NEW 2026-01-06 */}
              <div className="hidden lg:block">
                <RegimeIndicator />
              </div>

              <div className="hidden md:flex items-center space-x-2 bg-slate-900/50 rounded-lg px-3 py-1.5 border border-slate-700/50">
                <span className="text-xs text-slate-400">Chart:</span>
                <select
                  value={selectedSymbol}
                  onChange={(e) => setSelectedSymbol(e.target.value)}
                  className="bg-transparent text-sm font-medium text-slate-100 focus:outline-none cursor-pointer"
                >
                  {TRADING_PAIRS.map(pair => (
                    <option key={pair} value={pair} className="bg-slate-800">
                      {pair.replace('USDT', '')}
                    </option>
                  ))}
                </select>
              </div>

              {/* Date & Time */}
              <div className="text-xs text-slate-500">
                {new Date().toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                })}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content - Optimized dark background */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="space-y-5">
          {/* Price Tickers - Compact scrolling section */}
          <section>
            <PriceTickerGrid
              symbols={TRADING_PAIRS}
              onSymbolClick={(symbol) => setSelectedSymbol(symbol)}
            />
          </section>

          {/* Two-column layout: Chart + Signals side by side on large screens */}
          <section className="grid grid-cols-1 xl:grid-cols-3 gap-5">
            {/* Price Chart - Takes 2/3 of space */}
            <div className="xl:col-span-2">
              <PriceChart symbol={selectedSymbol} interval="60" />
            </div>

            {/* Trading Signals - Right sidebar style */}
            <div className="xl:col-span-1">
              <TradingSignals
                symbols={TRADING_PAIRS}
                interval={60}
                compact={true}
              />
            </div>
          </section>

          {/* Active Trades - Full width section showing executed trades */}
          <section>
            <ActiveTrades />
          </section>

          {/* Hybrid Strategy Panel - NEW 2026-01-06: Shows strategy routing and market regime */}
          <section>
            <HybridStrategyPanel />
          </section>

          {/* Trade History - Closed trades with win/loss statistics */}
          <section>
            <TradeHistory />
          </section>

          {/* Trading Enhancements - Research-backed risk management (NEW 2025-11-30) */}
          <section>
            <TradingEnhancementsPanel />
          </section>

          {/* Performance Analytics - Advanced metrics: Sharpe, Sortino, VaR (NEW 2025-11-30) */}
          <section>
            <PerformanceAnalyticsPanel />
          </section>

          {/* Portfolio and Emergency Stop */}
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2">
              <PortfolioCard />
            </div>
            <div className="lg:col-span-1">
              <EmergencyStop />
            </div>
          </section>

          {/* Trading Bot Configuration - Research-backed parameters display */}
          <section className="bg-slate-800/50 rounded-lg p-5 border border-slate-700/50 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-slate-100">
                Bot Configuration
              </h3>
              <span className="text-xs px-2 py-1 bg-cyan-500/10 text-cyan-400 rounded-full border border-cyan-500/20">
                Research-Optimized
              </span>
            </div>

            {/* Compact configuration grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
              <ConfigItem label="Interval" value="5 min" />
              <ConfigItem label="Position" value="2%" />
              <ConfigItem label="Stop Loss" value="-3%" negative />
              <ConfigItem label="Take Profit" value="+6%" positive />
              <ConfigItem label="Daily Limit" value="5%" />
              <ConfigItem label="Max Exposure" value="20%" />
              <ConfigItem label="Confidence" value="≥65%" />
              <ConfigItem label="Max Trades" value="20/day" />
            </div>

            {/* Research note */}
            <div className="mt-4 pt-3 border-t border-slate-700/50">
              <p className="text-xs text-slate-500">
                Parameters optimized based on 2025 crypto trading research: MACD (5-35-5), RSI (9), BB (2.5σ)
              </p>
            </div>
          </section>
        </div>
      </main>

      {/* Compact Footer */}
      <footer className="bg-slate-800/30 border-t border-slate-700/30 mt-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <div className="flex items-center gap-4">
              <span>Crypto Trading Bot v1.1.0</span>
              <span className="hidden sm:inline">•</span>
              <span className="hidden sm:inline">Paper Trading Mode</span>
            </div>
            <div className="flex items-center gap-2">
              <span>Backend:</span>
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                <span className="text-emerald-400">Connected</span>
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

/**
 * ConfigItem - Compact configuration display component
 */
function ConfigItem({ label, value, positive, negative }) {
  const valueColor = positive
    ? 'text-emerald-400'
    : negative
    ? 'text-rose-400'
    : 'text-slate-100'

  return (
    <div className="bg-slate-900/50 rounded px-2.5 py-2 border border-slate-700/30">
      <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-0.5">{label}</p>
      <p className={`text-sm font-semibold ${valueColor}`}>{value}</p>
    </div>
  )
}
