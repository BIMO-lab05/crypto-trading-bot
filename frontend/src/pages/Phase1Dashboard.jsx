import React from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

/**
 * Phase1Dashboard - Monitoring dashboard for Phase 1 signal processing
 * Displays GATEKEEPER, VOTER, and VALIDATOR metrics for signal quality
 *
 * UPDATED 2025-11-28: Added full dark mode support with Tailwind dark: variants
 * FIXED 2025-11-27: Updated field names to match actual API response structure
 */

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

// Fetch Phase 1 metrics
const usePhase1Metrics = (hours = 24) => {
  return useQuery({
    queryKey: ['phase1', 'metrics', hours],
    queryFn: async () => {
      console.log('[Phase1Dashboard] Fetching metrics for hours:', hours)
      const response = await api.get(`/trading/phase1/metrics?hours=${hours}`)
      console.log('[Phase1Dashboard] Metrics response:', response.data)
      return response.data
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  })
}

// Fetch Phase 1 system health
const usePhase1Health = () => {
  return useQuery({
    queryKey: ['phase1', 'health'],
    queryFn: async () => {
      console.log('[Phase1Dashboard] Fetching health status')
      const response = await api.get('/trading/phase1/health')
      console.log('[Phase1Dashboard] Health response:', response.data)
      return response.data
    },
    refetchInterval: 10000, // Refetch every 10 seconds
  })
}

// Fetch latest Phase 1 signal
const useLatestPhase1Signal = () => {
  return useQuery({
    queryKey: ['phase1', 'latest'],
    queryFn: async () => {
      console.log('[Phase1Dashboard] Fetching latest signal')
      const response = await api.get('/trading/phase1/latest')
      console.log('[Phase1Dashboard] Latest signal response:', response.data)
      return response.data
    },
    refetchInterval: 5000, // Refetch every 5 seconds
  })
}

export default function Phase1Dashboard() {
  const [hoursFilter, setHoursFilter] = React.useState(24)
  const { data: metricsData, isLoading: metricsLoading, error: metricsError } = usePhase1Metrics(hoursFilter)
  const { data: healthData, isLoading: healthLoading, error: healthError } = usePhase1Health()
  const { data: latestData, isLoading: latestLoading, error: latestError } = useLatestPhase1Signal()

  // Debug logging - raw data from hooks
  console.log('[Phase1Dashboard] Raw hook data:', {
    metricsData,
    healthData,
    latestData,
    metricsLoading,
    healthLoading,
    latestLoading
  })

  // Extract data with proper null safety - API returns { success: true, data: {...} }
  const metrics = metricsData?.data || {}
  const health = healthData?.data || {}
  const latest = latestData?.data

  // Debug logging - extracted data
  console.log('[Phase1Dashboard] Extracted metrics:', {
    metrics,
    health,
    latest,
    gatekeeperPassed: metrics.gatekeeper?.passed,
    gatekeeperBlocks: metrics.gatekeeper?.blocks,
    signalsTotal: metrics.signals?.total,
    healthStatus: health.status
  })

  // Calculate derived metrics for GATEKEEPER
  const gatekeeperTotal = (metrics.gatekeeper?.passed || 0) + (metrics.gatekeeper?.blocks || 0)
  const gatekeeperPassRate = gatekeeperTotal > 0
    ? ((metrics.gatekeeper?.passed || 0) / gatekeeperTotal)
    : 0

  // Calculate derived metrics for VALIDATOR
  const validatorTotal = (metrics.validator?.confirmed || 0) + (metrics.validator?.rejected || 0)
  const validatorPassRate = validatorTotal > 0
    ? ((metrics.validator?.confirmed || 0) / validatorTotal)
    : 0

  // Calculate vote distribution from signals
  const signalsTotal = metrics.signals?.total || 0
  const buySignals = metrics.signals?.buy || 0
  const sellSignals = metrics.signals?.sell || 0
  const holdSignals = metrics.signals?.hold || 0
  const actionSignals = buySignals + sellSignals
  const consensusRate = signalsTotal > 0 ? (actionSignals / signalsTotal) : 0

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-slate-900 py-8 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-slate-100 mb-2 transition-colors duration-200">
            Phase 1 Signal Processing Monitor
          </h1>
          <p className="text-gray-600 dark:text-slate-400 transition-colors duration-200">
            Real-time monitoring of GATEKEEPER - VOTER - VALIDATOR signal pipeline
          </p>
        </div>

        {/* Error Display */}
        {(metricsError || healthError) && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-4 transition-colors duration-200">
            <p className="text-red-800 dark:text-red-300">
              Error loading data: {metricsError?.message || healthError?.message}
            </p>
          </div>
        )}

        {/* Time Filter */}
        <div className="mb-6 flex items-center space-x-4">
          <span className="text-sm font-medium text-gray-700 dark:text-slate-300 transition-colors duration-200">Time Range:</span>
          <div className="flex space-x-2">
            {[1, 6, 24, 168].map((hours) => (
              <button
                key={hours}
                onClick={() => setHoursFilter(hours)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
                  hoursFilter === hours
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 border border-gray-200 dark:border-slate-700'
                }`}
              >
                {hours === 1 ? '1h' : hours === 168 ? '7d' : `${hours}h`}
              </button>
            ))}
          </div>
        </div>

        {/* System Health Status */}
        <div className="mb-6 bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 transition-colors duration-200">
          <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4 transition-colors duration-200">System Health</h2>

          {healthLoading ? (
            <div className="animate-pulse">
              <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-1/4 mb-2"></div>
              <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-1/2"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Overall Status</p>
                <p className={`text-lg font-bold ${
                  health.status === 'healthy' ? 'text-green-600 dark:text-green-400' :
                  health.status === 'warning' ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'
                }`}>
                  {health.status?.toUpperCase() || 'UNKNOWN'}
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Signals Last Hour</p>
                <p className="text-lg font-bold text-gray-800 dark:text-slate-100">
                  {health.signals_last_hour || 0}
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Total Processed</p>
                <p className="text-lg font-bold text-gray-800 dark:text-slate-100">
                  {health.total_signals_processed || 0}
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Last Signal</p>
                <p className="text-sm font-bold text-gray-800 dark:text-slate-100">
                  {health.last_signal_time
                    ? new Date(health.last_signal_time).toLocaleTimeString()
                    : 'No signals yet'}
                </p>
              </div>
            </div>
          )}

          {/* Filter Activity Status */}
          {health.filters_active && (
            <div className="mt-4 flex space-x-4">
              <div className={`flex items-center px-3 py-1 rounded-full text-sm transition-colors duration-200 ${
                health.filters_active.gatekeeper ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-400'
              }`}>
                <div className={`w-2 h-2 rounded-full mr-2 ${
                  health.filters_active.gatekeeper ? 'bg-green-500 dark:bg-green-400' : 'bg-gray-400 dark:bg-slate-500'
                }`}></div>
                Gatekeeper
              </div>
              <div className={`flex items-center px-3 py-1 rounded-full text-sm transition-colors duration-200 ${
                health.filters_active.validator ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-400'
              }`}>
                <div className={`w-2 h-2 rounded-full mr-2 ${
                  health.filters_active.validator ? 'bg-green-500 dark:bg-green-400' : 'bg-gray-400 dark:bg-slate-500'
                }`}></div>
                Validator
              </div>
              <div className={`flex items-center px-3 py-1 rounded-full text-sm transition-colors duration-200 ${
                health.filters_active.atr ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-400'
              }`}>
                <div className={`w-2 h-2 rounded-full mr-2 ${
                  health.filters_active.atr ? 'bg-green-500 dark:bg-green-400' : 'bg-gray-400 dark:bg-slate-500'
                }`}></div>
                ATR
              </div>
            </div>
          )}
        </div>

        {/* Latest Signal */}
        {latest && (
          <div className="mb-6 bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 transition-colors duration-200">
            <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">Latest Signal</h2>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Timestamp</p>
                <p className="text-sm font-bold text-gray-800 dark:text-slate-100">
                  {latest.timestamp
                    ? new Date(latest.timestamp).toLocaleString()
                    : 'N/A'}
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Action</p>
                <p className={`text-lg font-bold ${
                  latest.action === 'BUY' ? 'text-emerald-600 dark:text-emerald-400' :
                  latest.action === 'SELL' ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-400'
                }`}>
                  {latest.action || 'HOLD'}
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Confidence</p>
                <p className="text-lg font-bold text-blue-600 dark:text-blue-400">
                  {latest.confidence != null
                    ? `${(latest.confidence * 100).toFixed(1)}%`
                    : 'N/A'}
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Filters</p>
                <div className="flex space-x-2">
                  {latest.filters?.gatekeeper && (
                    <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-2 py-1 rounded">GK</span>
                  )}
                  {latest.filters?.validator && (
                    <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-2 py-1 rounded">VAL</span>
                  )}
                  {latest.filters?.atr && (
                    <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-2 py-1 rounded">ATR</span>
                  )}
                </div>
              </div>
            </div>

            {/* Signal Details */}
            {latest.details && (
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Trend</p>
                  <p className={`text-sm font-bold ${
                    latest.details.trend === 'BULLISH' ? 'text-green-600 dark:text-green-400' :
                    latest.details.trend === 'BEARISH' ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-400'
                  }`}>
                    {latest.details.trend || 'NEUTRAL'}
                  </p>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Trend Blocked</p>
                  <p className={`text-sm font-bold ${
                    latest.details.trend_blocked ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
                  }`}>
                    {latest.details.trend_blocked ? 'YES' : 'NO'}
                  </p>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Volume Strength</p>
                  <p className="text-sm font-bold text-gray-800 dark:text-slate-100">
                    {latest.details.volume_strength || 'N/A'}
                  </p>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Volume Penalty</p>
                  <p className="text-sm font-bold text-gray-800 dark:text-slate-100">
                    {latest.details.volume_penalty != null
                      ? `${(latest.details.volume_penalty * 100).toFixed(0)}%`
                      : 'N/A'}
                  </p>
                </div>
              </div>
            )}

            {/* Metadata */}
            {latest.metadata && (
              <div className="mt-4 p-4 bg-gray-50 dark:bg-slate-700/50 rounded-lg transition-colors duration-200">
                <div className="grid grid-cols-3 md:grid-cols-6 gap-4 text-center">
                  <div>
                    <p className="text-xs text-gray-600 dark:text-slate-400">Buy Votes</p>
                    <p className="text-lg font-bold text-green-600 dark:text-green-400">{latest.metadata.buy_count || 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 dark:text-slate-400">Sell Votes</p>
                    <p className="text-lg font-bold text-red-600 dark:text-red-400">{latest.metadata.sell_count || 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 dark:text-slate-400">Hold Votes</p>
                    <p className="text-lg font-bold text-gray-600 dark:text-slate-400">{latest.metadata.hold_count || 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 dark:text-slate-400">Consensus</p>
                    <p className="text-lg font-bold text-purple-600 dark:text-purple-400">{latest.metadata.consensus_count || 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 dark:text-slate-400">Score</p>
                    <p className={`text-lg font-bold ${
                      (latest.metadata.aggregated_score || 0) > 0 ? 'text-green-600 dark:text-green-400' :
                      (latest.metadata.aggregated_score || 0) < 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-400'
                    }`}>
                      {(latest.metadata.aggregated_score || 0).toFixed(3)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 dark:text-slate-400">Requirements</p>
                    <p className={`text-lg font-bold ${
                      latest.metadata.meets_requirements ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                    }`}>
                      {latest.metadata.meets_requirements ? '+' : 'x'}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {!latest && !latestLoading && (
          <div className="mb-6 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-6 transition-colors duration-200">
            <p className="text-yellow-800 dark:text-yellow-300 text-center">
              No recent signals generated yet. Automated trading will check signals every 5 minutes.
            </p>
          </div>
        )}

        {/* Phase 1 Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* GATEKEEPER Metrics - FIXED to use actual API fields */}
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 transition-colors duration-200">
            <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">
              GATEKEEPER (Trend Filter)
            </h2>

            {metricsLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-1/2"></div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">Total Processed</span>
                  <span className="text-2xl font-bold text-gray-800 dark:text-slate-100">
                    {gatekeeperTotal}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">Passed</span>
                  <span className="text-2xl font-bold text-green-600 dark:text-green-400">
                    {metrics.gatekeeper?.passed || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">Blocked</span>
                  <span className="text-2xl font-bold text-red-600 dark:text-red-400">
                    {metrics.gatekeeper?.blocks || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center pt-4 border-t border-gray-200 dark:border-slate-700">
                  <span className="text-gray-600 dark:text-slate-400 font-semibold">Pass Rate</span>
                  <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {(gatekeeperPassRate * 100).toFixed(1)}%
                  </span>
                </div>

                {/* Trend Distribution */}
                <div className="pt-4 border-t border-gray-200 dark:border-slate-700">
                  <p className="text-sm text-gray-600 dark:text-slate-400 mb-2">Trend Distribution:</p>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-green-50 dark:bg-green-900/20 rounded p-2 transition-colors duration-200">
                      <p className="text-xs text-gray-600 dark:text-slate-400">Bullish</p>
                      <p className="font-bold text-green-600 dark:text-green-400">
                        {metrics.gatekeeper?.bullish_trends || 0}
                      </p>
                    </div>
                    <div className="bg-red-50 dark:bg-red-900/20 rounded p-2 transition-colors duration-200">
                      <p className="text-xs text-gray-600 dark:text-slate-400">Bearish</p>
                      <p className="font-bold text-red-600 dark:text-red-400">
                        {metrics.gatekeeper?.bearish_trends || 0}
                      </p>
                    </div>
                    <div className="bg-gray-50 dark:bg-slate-700/50 rounded p-2 transition-colors duration-200">
                      <p className="text-xs text-gray-600 dark:text-slate-400">Neutral</p>
                      <p className="font-bold text-gray-600 dark:text-slate-400">
                        {metrics.gatekeeper?.neutral_trends || 0}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* SIGNALS Summary (replacing VOTER) */}
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 transition-colors duration-200">
            <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">
              SIGNALS (Vote Distribution)
            </h2>

            {metricsLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-1/2"></div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">Total Signals</span>
                  <span className="text-2xl font-bold text-gray-800 dark:text-slate-100">
                    {signalsTotal}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">BUY Signals</span>
                  <span className="text-2xl font-bold text-green-600 dark:text-green-400">
                    {buySignals}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">SELL Signals</span>
                  <span className="text-2xl font-bold text-red-600 dark:text-red-400">
                    {sellSignals}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400">HOLD Signals</span>
                  <span className="text-2xl font-bold text-gray-600 dark:text-slate-400">
                    {holdSignals}
                  </span>
                </div>

                <div className="flex justify-between items-center pt-4 border-t border-gray-200 dark:border-slate-700">
                  <span className="text-gray-600 dark:text-slate-400 font-semibold">Action Rate</span>
                  <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {(metrics.filtering?.action_rate || 0).toFixed(1)}%
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-slate-400 font-semibold">Hold Rate</span>
                  <span className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                    {(metrics.filtering?.hold_rate || 0).toFixed(1)}%
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* VALIDATOR Metrics - FIXED to use actual API fields */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 mb-6 transition-colors duration-200">
          <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">
            VALIDATOR (Volume Confirmation)
          </h2>

          {metricsLoading ? (
            <div className="animate-pulse space-y-3">
              <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-1/2"></div>
              <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-2/3"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Total Processed</p>
                <p className="text-2xl font-bold text-gray-800 dark:text-slate-100">
                  {validatorTotal}
                </p>
              </div>

              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Confirmed</p>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {metrics.validator?.confirmed || 0}
                </p>
              </div>

              <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Rejected</p>
                <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                  {metrics.validator?.rejected || 0}
                </p>
              </div>

              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Confirmation Rate</p>
                <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                  {(validatorPassRate * 100).toFixed(1)}%
                </p>
              </div>

              <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400 mb-1">Rejection Rate</p>
                <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                  {(metrics.filtering?.validator_rejection_rate || 0).toFixed(1)}%
                </p>
              </div>
            </div>
          )}

          {/* Volume Strength Distribution */}
          {metrics.validator?.strength_distribution && (
            <div className="mt-4">
              <p className="text-sm text-gray-600 dark:text-slate-400 mb-2">Volume Strength Distribution:</p>
              <div className="grid grid-cols-4 gap-2 text-center">
                <div className="bg-green-50 dark:bg-green-900/20 rounded p-2 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Strong</p>
                  <p className="font-bold text-green-600 dark:text-green-400">
                    {metrics.validator.strength_distribution.STRONG || 0}
                  </p>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded p-2 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Moderate</p>
                  <p className="font-bold text-blue-600 dark:text-blue-400">
                    {metrics.validator.strength_distribution.MODERATE || 0}
                  </p>
                </div>
                <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded p-2 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Weak</p>
                  <p className="font-bold text-yellow-600 dark:text-yellow-400">
                    {metrics.validator.strength_distribution.WEAK || 0}
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-slate-700/50 rounded p-2 transition-colors duration-200">
                  <p className="text-xs text-gray-600 dark:text-slate-400">Minimal</p>
                  <p className="font-bold text-gray-600 dark:text-slate-400">
                    {metrics.validator.strength_distribution.MINIMAL || 0}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ATR Volatility Stats */}
        {metrics.atr && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 mb-6 transition-colors duration-200">
            <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">
              ATR Volatility Distribution
            </h2>
            <div className="grid grid-cols-4 gap-4 text-center">
              <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400">Extreme</p>
                <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                  {metrics.atr.extreme || 0}
                </p>
              </div>
              <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400">High</p>
                <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">
                  {metrics.atr.high || 0}
                </p>
              </div>
              <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400">Medium</p>
                <p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
                  {metrics.atr.medium || 0}
                </p>
              </div>
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 transition-colors duration-200">
                <p className="text-sm text-gray-600 dark:text-slate-400">Low</p>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {metrics.atr.low || 0}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Signal Timeline */}
        {metrics.timeline && metrics.timeline.length > 0 && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow dark:shadow-slate-900/50 p-6 mb-6 transition-colors duration-200">
            <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">
              Recent Signal Timeline
            </h2>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-slate-700">
                <thead className="bg-gray-50 dark:bg-slate-700/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase">Time</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase">Action</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase">Confidence</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase">Trend</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase">Volume</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-slate-400 uppercase">Filters</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-700">
                  {metrics.timeline.slice(0, 10).map((signal, index) => (
                    <tr key={index} className="hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors duration-150">
                      <td className="px-4 py-3 text-sm text-gray-600 dark:text-slate-300">
                        {new Date(signal.timestamp).toLocaleTimeString()}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${
                          signal.action === 'BUY' ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' :
                          signal.action === 'SELL' ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300' :
                          'bg-gray-100 dark:bg-slate-700 text-gray-800 dark:text-slate-300'
                        }`}>
                          {signal.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm font-semibold text-blue-600 dark:text-blue-400">
                        {((signal.confidence || 0) * 100).toFixed(0)}%
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-sm ${
                          signal.details?.trend === 'BULLISH' ? 'text-green-600 dark:text-green-400' :
                          signal.details?.trend === 'BEARISH' ? 'text-red-600 dark:text-red-400' :
                          'text-gray-600 dark:text-slate-400'
                        }`}>
                          {signal.details?.trend || 'N/A'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 dark:text-slate-300">
                        {signal.details?.volume_strength || 'N/A'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex space-x-1">
                          {signal.filters?.gatekeeper && (
                            <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-1 rounded">GK</span>
                          )}
                          {signal.filters?.validator && (
                            <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-1 rounded">VAL</span>
                          )}
                          {signal.filters?.atr && (
                            <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 px-1 rounded">ATR</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Pipeline Summary */}
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 rounded-lg shadow dark:shadow-slate-900/50 p-6 transition-colors duration-200">
          <h2 className="text-xl font-bold text-gray-800 dark:text-slate-100 mb-4">
            Phase 1 Pipeline Summary
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h3 className="font-semibold text-gray-700 dark:text-slate-300 mb-2">Pipeline Flow</h3>
              <div className="space-y-2">
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-blue-500 mr-2"></div>
                  <span className="text-sm text-gray-700 dark:text-slate-300">All Signals - GATEKEEPER (Trend)</span>
                </div>
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-green-500 mr-2"></div>
                  <span className="text-sm text-gray-700 dark:text-slate-300">Passed - VOTER (Consensus)</span>
                </div>
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-purple-500 mr-2"></div>
                  <span className="text-sm text-gray-700 dark:text-slate-300">Consensus - VALIDATOR (Volume)</span>
                </div>
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-yellow-500 mr-2"></div>
                  <span className="text-sm text-gray-700 dark:text-slate-300">Validated - TRADE EXECUTION</span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="font-semibold text-gray-700 dark:text-slate-300 mb-2">Current Settings</h3>
              <div className="space-y-1 text-sm text-gray-600 dark:text-slate-400">
                <p>Min Consensus: <span className="font-semibold text-gray-800 dark:text-slate-200">2 indicators</span></p>
                <p>Min Confidence: <span className="font-semibold text-gray-800 dark:text-slate-200">15%</span></p>
                <p>Aggregation Threshold: <span className="font-semibold text-gray-800 dark:text-slate-200">0.12</span></p>
                <p>Check Frequency: <span className="font-semibold text-gray-800 dark:text-slate-200">5 min</span></p>
              </div>
            </div>

            <div>
              <h3 className="font-semibold text-gray-700 dark:text-slate-300 mb-2">Filtering Rates</h3>
              <div className="space-y-1 text-sm text-gray-600 dark:text-slate-400">
                <p>Gatekeeper Block Rate: <span className="font-semibold text-red-600 dark:text-red-400">
                  {(metrics.filtering?.gatekeeper_block_rate || 0).toFixed(1)}%
                </span></p>
                <p>Validator Rejection Rate: <span className="font-semibold text-red-600 dark:text-red-400">
                  {(metrics.filtering?.validator_rejection_rate || 0).toFixed(1)}%
                </span></p>
                <p>Overall Reduction: <span className="font-semibold text-blue-600 dark:text-blue-400">
                  {(metrics.filtering?.reduction_rate || 0).toFixed(1)}%
                </span></p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer Info */}
        <div className="mt-6 text-center text-sm text-gray-500 dark:text-slate-500 transition-colors duration-200">
          Data auto-refreshes: Metrics every 30s | Health every 10s | Latest signal every 5s
        </div>
      </div>
    </div>
  )
}
