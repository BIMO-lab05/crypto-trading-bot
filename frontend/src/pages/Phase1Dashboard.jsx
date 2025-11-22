import React from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

/**
 * Phase1Dashboard - Monitoring dashboard for Phase 1 signal processing
 * Displays GATEKEEPER, VOTER, and VALIDATOR metrics for signal quality
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
      const response = await api.get(`/trading/phase1/metrics?hours=${hours}`)
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
      const response = await api.get('/trading/phase1/health')
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
      const response = await api.get('/trading/phase1/latest')
      return response.data
    },
    refetchInterval: 5000, // Refetch every 5 seconds
  })
}

export default function Phase1Dashboard() {
  const [hoursFilter, setHoursFilter] = React.useState(24)
  const { data: metricsData, isLoading: metricsLoading } = usePhase1Metrics(hoursFilter)
  const { data: healthData, isLoading: healthLoading } = usePhase1Health()
  const { data: latestData, isLoading: latestLoading } = useLatestPhase1Signal()

  const metrics = metricsData?.data || {}
  const health = healthData?.data || {}
  const latest = latestData?.data

  return (
    <div className="min-h-screen bg-gray-100 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Phase 1 Signal Processing Monitor
          </h1>
          <p className="text-gray-600">
            Real-time monitoring of GATEKEEPER → VOTER → VALIDATOR signal pipeline
          </p>
        </div>

        {/* Time Filter */}
        <div className="mb-6 flex items-center space-x-4">
          <span className="text-sm font-medium text-gray-700">Time Range:</span>
          <div className="flex space-x-2">
            {[1, 6, 24, 168].map((hours) => (
              <button
                key={hours}
                onClick={() => setHoursFilter(hours)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  hoursFilter === hours
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                {hours === 1 ? '1h' : hours === 168 ? '7d' : `${hours}h`}
              </button>
            ))}
          </div>
        </div>

        {/* System Health Status */}
        <div className="mb-6 bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-bold text-gray-800 mb-4">System Health</h2>

          {healthLoading ? (
            <div className="animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Overall Status</p>
                <p className={`text-lg font-bold ${
                  health.status === 'healthy' ? 'text-green-600' :
                  health.status === 'degraded' ? 'text-yellow-600' : 'text-red-600'
                }`}>
                  {health.status?.toUpperCase() || 'UNKNOWN'}
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Signal Processing Rate</p>
                <p className="text-lg font-bold text-gray-800">
                  {health.signals_per_hour || 0} signals/hour
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Last Signal</p>
                <p className="text-lg font-bold text-gray-800">
                  {health.last_signal_time || 'No signals yet'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Latest Signal */}
        {latest && (
          <div className="mb-6 bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Latest Signal</h2>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Symbol</p>
                <p className="text-lg font-bold text-gray-800">{latest.symbol}</p>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Action</p>
                <p className={`text-lg font-bold ${
                  latest.action === 'BUY' ? 'text-green-600' :
                  latest.action === 'SELL' ? 'text-red-600' : 'text-gray-600'
                }`}>
                  {latest.action}
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Confidence</p>
                <p className="text-lg font-bold text-blue-600">
                  {(latest.confidence * 100).toFixed(1)}%
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Consensus</p>
                <p className="text-lg font-bold text-purple-600">
                  {latest.consensus_count || 0} / {latest.total_indicators || 0}
                </p>
              </div>
            </div>

            {latest.metadata?.passed_validation !== undefined && (
              <div className={`mt-4 p-4 rounded-lg ${
                latest.metadata.passed_validation
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-red-50 border border-red-200'
              }`}>
                <p className={`font-semibold ${
                  latest.metadata.passed_validation ? 'text-green-800' : 'text-red-800'
                }`}>
                  {latest.metadata.passed_validation
                    ? '✅ Signal passed validation'
                    : '❌ Signal did not meet requirements'}
                </p>
                {latest.metadata.rejection_reason && (
                  <p className="text-sm text-red-700 mt-1">
                    Reason: {latest.metadata.rejection_reason}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {!latest && !latestLoading && (
          <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-6">
            <p className="text-yellow-800 text-center">
              No recent signals generated yet. Automated trading will check signals every 5 minutes.
            </p>
          </div>
        )}

        {/* Phase 1 Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* GATEKEEPER Metrics */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">
              GATEKEEPER (Min Indicators Check)
            </h2>

            {metricsLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 rounded w-1/2"></div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Total Signals</span>
                  <span className="text-2xl font-bold text-gray-800">
                    {metrics.gatekeeper?.total_signals || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Passed</span>
                  <span className="text-2xl font-bold text-green-600">
                    {metrics.gatekeeper?.passed || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Rejected</span>
                  <span className="text-2xl font-bold text-red-600">
                    {metrics.gatekeeper?.rejected || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center pt-4 border-t">
                  <span className="text-gray-600 font-semibold">Pass Rate</span>
                  <span className="text-2xl font-bold text-blue-600">
                    {metrics.gatekeeper?.pass_rate
                      ? `${(metrics.gatekeeper.pass_rate * 100).toFixed(1)}%`
                      : '0%'}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* VOTER Metrics */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">
              VOTER (Consensus Check)
            </h2>

            {metricsLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 rounded w-1/2"></div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Total Signals</span>
                  <span className="text-2xl font-bold text-gray-800">
                    {metrics.voter?.total_signals || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600">Consensus Reached</span>
                  <span className="text-2xl font-bold text-green-600">
                    {metrics.voter?.consensus_reached || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-gray-600">No Consensus</span>
                  <span className="text-2xl font-bold text-red-600">
                    {metrics.voter?.no_consensus || 0}
                  </span>
                </div>

                <div className="flex justify-between items-center pt-4 border-t">
                  <span className="text-gray-600 font-semibold">Consensus Rate</span>
                  <span className="text-2xl font-bold text-blue-600">
                    {metrics.voter?.consensus_rate
                      ? `${(metrics.voter.consensus_rate * 100).toFixed(1)}%`
                      : '0%'}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* VALIDATOR Metrics */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-bold text-gray-800 mb-4">
            VALIDATOR (Confidence Threshold Check)
          </h2>

          {metricsLoading ? (
            <div className="animate-pulse space-y-3">
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
              <div className="h-4 bg-gray-200 rounded w-2/3"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Total Signals</p>
                <p className="text-2xl font-bold text-gray-800">
                  {metrics.validator?.total_signals || 0}
                </p>
              </div>

              <div className="bg-green-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Validated</p>
                <p className="text-2xl font-bold text-green-600">
                  {metrics.validator?.validated || 0}
                </p>
              </div>

              <div className="bg-red-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Rejected</p>
                <p className="text-2xl font-bold text-red-600">
                  {metrics.validator?.rejected || 0}
                </p>
              </div>

              <div className="bg-blue-50 rounded-lg p-4">
                <p className="text-sm text-gray-600 mb-1">Validation Rate</p>
                <p className="text-2xl font-bold text-blue-600">
                  {metrics.validator?.validation_rate
                    ? `${(metrics.validator.validation_rate * 100).toFixed(1)}%`
                    : '0%'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Pipeline Summary */}
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg shadow p-6">
          <h2 className="text-xl font-bold text-gray-800 mb-4">
            Phase 1 Pipeline Summary
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h3 className="font-semibold text-gray-700 mb-2">Pipeline Flow</h3>
              <div className="space-y-2">
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-blue-500 mr-2"></div>
                  <span className="text-sm">All Signals → GATEKEEPER</span>
                </div>
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-green-500 mr-2"></div>
                  <span className="text-sm">Passed → VOTER</span>
                </div>
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-purple-500 mr-2"></div>
                  <span className="text-sm">Consensus → VALIDATOR</span>
                </div>
                <div className="flex items-center">
                  <div className="w-4 h-4 rounded-full bg-yellow-500 mr-2"></div>
                  <span className="text-sm">Validated → TRADE</span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="font-semibold text-gray-700 mb-2">Current Settings</h3>
              <div className="space-y-1 text-sm text-gray-600">
                <p>Min Indicators: <span className="font-semibold">4</span></p>
                <p>Min Consensus: <span className="font-semibold">4</span></p>
                <p>Min Confidence: <span className="font-semibold">60%</span></p>
                <p>Check Frequency: <span className="font-semibold">5 min</span></p>
              </div>
            </div>

            <div>
              <h3 className="font-semibold text-gray-700 mb-2">Data Quality</h3>
              <p className="text-sm text-gray-600 mb-2">
                Phase 1 filtering ensures only high-quality signals proceed to trade execution.
                The three-stage validation (GATEKEEPER → VOTER → VALIDATOR) reduces false signals
                and improves trading accuracy.
              </p>
            </div>
          </div>
        </div>

        {/* Footer Info */}
        <div className="mt-6 text-center text-sm text-gray-500">
          Data auto-refreshes: Metrics every 30s • Health every 10s • Latest signal every 5s
        </div>
      </div>
    </div>
  )
}
