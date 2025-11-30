import React from 'react'
import { useAutoTraderStatus, extractTradingEnhancements } from '../hooks/useAutoTrader'

/**
 * TradingEnhancementsPanel - Display Trading Enhancements Status
 *
 * Created: 2025-11-30
 *
 * Shows real-time status of:
 * - Circuit Breaker (resilience pattern for API failures)
 * - Kill Switch (multi-threshold emergency stop)
 * - Slippage Manager (dynamic slippage control)
 * - Execution Timer (position monitoring intervals)
 * - Advanced Position Sizer (Kelly Criterion, Optimal F, ATR-based)
 * - Smart Order Executor (TWAP, VWAP, Iceberg, POV algorithms)
 *
 * Design follows existing KeyMetricsStrip pattern for consistency
 */

const StatusBadge = ({ status, label }) => {
  const getStatusColors = () => {
    switch (status?.toLowerCase()) {
      case 'closed':
      case 'active':
      case 'healthy':
        return {
          bg: 'bg-emerald-500/10',
          border: 'border-emerald-500/30',
          text: 'text-emerald-400',
          dot: 'bg-emerald-500',
        }
      case 'half_open':
      case 'warning':
        return {
          bg: 'bg-amber-500/10',
          border: 'border-amber-500/30',
          text: 'text-amber-400',
          dot: 'bg-amber-500',
        }
      case 'open':
      case 'triggered':
      case 'error':
        return {
          bg: 'bg-rose-500/10',
          border: 'border-rose-500/30',
          text: 'text-rose-400',
          dot: 'bg-rose-500',
        }
      default:
        return {
          bg: 'bg-slate-500/10',
          border: 'border-slate-500/30',
          text: 'text-slate-400',
          dot: 'bg-slate-500',
        }
    }
  }

  const colors = getStatusColors()

  return (
    <span className={`
      inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium
      ${colors.bg} ${colors.border} border ${colors.text}
    `}>
      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot} animate-pulse`}></span>
      {label || status}
    </span>
  )
}

const EnhancementCard = ({ title, children, icon, isLoading }) => (
  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 backdrop-blur-sm">
    <div className="flex items-center gap-2 mb-3">
      {icon && <span className="text-slate-400">{icon}</span>}
      <h4 className="text-sm font-semibold text-slate-200">{title}</h4>
    </div>
    {isLoading ? (
      <div className="animate-pulse space-y-2">
        <div className="h-4 bg-slate-700 rounded w-3/4"></div>
        <div className="h-4 bg-slate-700 rounded w-1/2"></div>
      </div>
    ) : (
      children
    )}
  </div>
)

const MetricRow = ({ label, value, subValue, trend }) => {
  const getTrendColor = () => {
    if (trend === 'positive') return 'text-emerald-400'
    if (trend === 'negative') return 'text-rose-400'
    return 'text-slate-100'
  }

  return (
    <div className="flex justify-between items-center py-1.5">
      <span className="text-xs text-slate-400">{label}</span>
      <div className="text-right">
        <span className={`text-sm font-medium ${getTrendColor()}`}>{value}</span>
        {subValue && (
          <span className="text-xs text-slate-500 ml-1">({subValue})</span>
        )}
      </div>
    </div>
  )
}

export default function TradingEnhancementsPanel() {
  const { data: statusData, isLoading, isError } = useAutoTraderStatus()

  const enhancements = extractTradingEnhancements(statusData)

  const ShieldIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  )

  const AlertIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  )

  const ChartIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
    </svg>
  )

  const ClockIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )

  const ScaleIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
    </svg>
  )

  const CogIcon = (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  )

  if (isError) {
    return (
      <div className="bg-slate-800/50 rounded-lg p-6 border border-slate-700/50">
        <div className="text-center text-rose-400">
          Failed to load trading enhancements status
        </div>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-100">
            Trading Enhancements
          </h3>
          <span className="text-xs px-2 py-1 bg-cyan-500/10 text-cyan-400 rounded-full border border-cyan-500/20">
            Research-Backed
          </span>
        </div>
        <p className="text-xs text-slate-500 mt-1">
          Advanced trading controls and risk management systems
        </p>
      </div>

      <div className="p-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Circuit Breaker */}
        <EnhancementCard title="Circuit Breaker" icon={ShieldIcon} isLoading={isLoading}>
          <div className="space-y-1">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-slate-400">State</span>
              <StatusBadge status={enhancements?.circuitBreaker?.state} />
            </div>
            <MetricRow
              label="Consecutive Failures"
              value={`${enhancements?.circuitBreaker?.failures || 0} / ${enhancements?.circuitBreaker?.threshold || 5}`}
              trend={enhancements?.circuitBreaker?.failures > 0 ? 'negative' : 'positive'}
            />
          </div>
        </EnhancementCard>

        {/* Kill Switch */}
        <EnhancementCard title="Kill Switch" icon={AlertIcon} isLoading={isLoading}>
          <div className="space-y-1">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-slate-400">Status</span>
              <StatusBadge
                status={enhancements?.killSwitch?.isActive ? 'triggered' : 'healthy'}
                label={enhancements?.killSwitch?.isActive ? 'ACTIVE' : 'Ready'}
              />
            </div>
            {enhancements?.killSwitch?.isActive && (
              <div className="text-xs text-rose-400 bg-rose-500/10 rounded p-2 mt-2">
                Reason: {enhancements?.killSwitch?.reason || 'Unknown'}
              </div>
            )}
            {!enhancements?.killSwitch?.isActive && (
              <MetricRow label="Thresholds" value="Monitoring" />
            )}
          </div>
        </EnhancementCard>

        {/* Slippage Manager */}
        <EnhancementCard title="Slippage Manager" icon={ChartIcon} isLoading={isLoading}>
          <div className="space-y-1">
            <MetricRow
              label="Max Slippage"
              value={`${((enhancements?.slippageManager?.maxSlippage || 0) * 100).toFixed(2)}%`}
            />
            <MetricRow
              label="Total Trades"
              value={enhancements?.slippageManager?.stats?.total_trades || 0}
            />
            <MetricRow
              label="Avg Slippage"
              value={`${((enhancements?.slippageManager?.stats?.avg_slippage || 0) * 100).toFixed(3)}%`}
              trend={enhancements?.slippageManager?.stats?.avg_slippage > 0.001 ? 'negative' : 'positive'}
            />
          </div>
        </EnhancementCard>

        {/* Execution Timer */}
        <EnhancementCard title="Execution Timer" icon={ClockIcon} isLoading={isLoading}>
          <div className="space-y-1">
            <MetricRow
              label="Mode"
              value={enhancements?.executionTimer?.mode?.toUpperCase() || 'PAPER'}
            />
            <MetricRow
              label="Min Interval"
              value={`${enhancements?.executionTimer?.minInterval || 60}s`}
            />
          </div>
        </EnhancementCard>

        {/* Advanced Position Sizer */}
        <EnhancementCard title="Position Sizer" icon={ScaleIcon} isLoading={isLoading}>
          {enhancements?.positionSizer ? (
            <div className="space-y-1">
              <MetricRow
                label="Max Position"
                value={`${((enhancements?.positionSizer?.max_position_pct || 0) * 100).toFixed(1)}%`}
              />
              <MetricRow
                label="Kelly Fraction"
                value={enhancements?.positionSizer?.kelly_fraction || 'N/A'}
              />
              <MetricRow
                label="Method"
                value={enhancements?.positionSizer?.default_method?.replace('_', ' ') || 'Fixed'}
              />
            </div>
          ) : (
            <div className="text-xs text-slate-500">Not configured</div>
          )}
        </EnhancementCard>

        {/* Smart Order Executor */}
        <EnhancementCard title="Smart Executor" icon={CogIcon} isLoading={isLoading}>
          {enhancements?.smartExecutor ? (
            <div className="space-y-1">
              <MetricRow
                label="Algorithm"
                value={enhancements?.smartExecutor?.default_algorithm?.toUpperCase() || 'MARKET'}
              />
              <MetricRow
                label="Max Slices"
                value={enhancements?.smartExecutor?.max_slices || 1}
              />
              <MetricRow
                label="Slice Interval"
                value={`${enhancements?.smartExecutor?.slice_interval || 0}s`}
              />
            </div>
          ) : (
            <div className="text-xs text-slate-500">Not configured</div>
          )}
        </EnhancementCard>
      </div>

      {/* Footer */}
      <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
        <p className="text-xs text-slate-500">
          Auto-refresh every 10s | Based on research: Circuit Breaker, Kill Switch, OMS patterns
        </p>
      </div>
    </div>
  )
}
