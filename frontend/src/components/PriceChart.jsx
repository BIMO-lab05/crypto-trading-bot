import React, { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  Bar,
} from 'recharts'
import { useKlines } from '../hooks/useTicker'
import { formatDistanceToNow } from 'date-fns'
import ChartFigure from './a11y/ChartFigure'
import TileState from './TileState'

/**
 * PriceChart component displays historical price data for a cryptocurrency
 * Shows the last 24 hours of price data with interactive chart
 *
 * Features:
 * - Real-time price updates every minute
 * - Candlestick-style display with high/low bands
 * - Volume visualization as bar chart
 * - Responsive design that adapts to container
 * - Tooltip showing detailed price information
 * - Error handling and loading states
 *
 * @param {string} symbol - The trading symbol (e.g., 'BTCUSDT')
 * @param {string} interval - Kline interval in minutes (default: '60' for hourly)
 */
export default function PriceChart({ symbol = 'BTCUSDT', interval = '60' }) {
  // Fetch kline data using custom hook.
  // Plan 06-05 DASH-05: audit verdict LABELED_STALE (market-data unhealthy
  // at audit time 2026-05-13). Wrapped in <TileState forceStale/> below;
  // F-05 precedence ensures real errors still surface as Failed (...) UI.
  const q = useKlines(symbol, interval, { limit: 24 })
  const { data, isLoading, error } = q

  // Transform API data into recharts-compatible format
  // Handles data normalization and price band calculations
  const chartData = useMemo(() => {
    if (!data || !Array.isArray(data)) return []

    // First, transform all candles
    const transformed = data.map((candle) => {
      // Extract OHLCV data from API response
      // API returns: { timestamp, open, high, low, close, volume, ... }
      const openTime = Array.isArray(candle) ? candle[0] : (candle.timestamp || candle.open_time)
      const open = parseFloat(Array.isArray(candle) ? candle[1] : candle.open)
      const high = parseFloat(Array.isArray(candle) ? candle[2] : candle.high)
      const low = parseFloat(Array.isArray(candle) ? candle[3] : candle.low)
      const close = parseFloat(Array.isArray(candle) ? candle[4] : candle.close)
      const volume = parseFloat(Array.isArray(candle) ? candle[5] : candle.volume)
      // Use turnover (USD value) for volume display - much more meaningful
      const turnover = parseFloat(candle.turnover || volume * close)

      // Format timestamp for display
      const timestamp = new Date(openTime)
      const timeLabel = timestamp.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })

      // Return normalized data point for recharts
      return {
        time: timeLabel,
        timestamp: openTime,
        open,
        high,
        low,
        close,
        volume: turnover, // Use turnover (USD) instead of volume (BTC)
        volumeBTC: volume, // Keep original BTC volume for reference
        // Calculate mid-range for display purposes
        mid: (high + low) / 2,
      }
    })

    // Sort by timestamp ascending (oldest first for chart)
    return transformed.sort((a, b) => a.timestamp - b.timestamp)
  }, [data])

  // Calculate price range statistics for axis scaling
  const stats = useMemo(() => {
    if (chartData.length === 0) {
      return { minPrice: 0, maxPrice: 0, avgVolume: 0 }
    }

    const closes = chartData.map(d => d.close)
    const volumes = chartData.map(d => d.volume)

    return {
      minPrice: Math.min(...chartData.map(d => d.low)),
      maxPrice: Math.max(...chartData.map(d => d.high)),
      avgVolume: volumes.reduce((a, b) => a + b, 0) / volumes.length,
    }
  }, [chartData])

  // Custom tooltip to display detailed information on hover
  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || payload.length === 0) return null

    const data = payload[0].payload

    return (
      <div className="bg-gray-900 text-white p-3 rounded shadow-lg border border-gray-700">
        <p className="text-sm font-semibold">{symbol}</p>
        <p className="text-xs text-gray-400">{new Date(data.timestamp).toLocaleString()}</p>
        <p className="text-sm mt-1">
          <span className="text-blue-400">O:</span> ${data.open.toFixed(2)}
          <span className="ml-2 text-green-400">H:</span> ${data.high.toFixed(2)}
        </p>
        <p className="text-sm">
          <span className="text-red-400">L:</span> ${data.low.toFixed(2)}
          <span className="ml-2 text-yellow-400">C:</span> ${data.close.toFixed(2)}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          Vol: {(data.volume / 1000000).toFixed(2)}M
        </p>
      </div>
    )
  }

  // Loading and error states are now handled by <TileState/> below.
  // Empty-data state is also handled by TileState (default isEmpty
  // predicate: array length 0).

  // Calculate current price and change
  const currentPrice = chartData[chartData.length - 1]?.close || 0
  const previousPrice = chartData[0]?.close || 0
  const priceChange = currentPrice - previousPrice
  const priceChangePercent = previousPrice !== 0 ? (priceChange / previousPrice) * 100 : 0

  return (
    <TileState
      query={q}
      title={`${symbol} Price Chart`}
      thresholdKey="ticker"
      lastUpdatedAt={undefined}
      forceStale
      isEmpty={(d) => !d || !Array.isArray(d) || d.length === 0}
    >
    <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 backdrop-blur-sm p-6">
      {/* Header with title and current price */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-2xl font-bold text-slate-100">
            {symbol} Price Chart
          </h3>
          <p className="text-sm text-slate-400">
            Last 24 hours ({interval}-minute candles)
          </p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold text-slate-100">
            ${currentPrice.toFixed(2)}
          </p>
          <p className={`text-sm font-semibold ${priceChange >= 0 ? 'text-green-400' : 'text-rose-400'}`}>
            {priceChange >= 0 ? '+' : ''}${priceChange.toFixed(2)}
            <span className="ml-2">
              ({priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
            </span>
          </p>
        </div>
      </div>

      {/* Combined chart showing price and volume */}
      <ChartFigure
        summary={`${symbol} price chart, last ${chartData.length} ${interval}-minute candles. Current price ${currentPrice.toFixed(2)} dollars, ${priceChange >= 0 ? 'up' : 'down'} ${Math.abs(priceChange).toFixed(2)} (${priceChangePercent.toFixed(2)} percent) over period. 24h high ${stats.maxPrice.toFixed(2)}, 24h low ${stats.minPrice.toFixed(2)}, average volume ${(stats.avgVolume / 1000000).toFixed(2)} million.`}
        tableCaption={`${symbol} price summary`}
        columns={[
          { key: 'metric', label: 'Metric' },
          { key: 'value', label: 'Value' },
        ]}
        rows={[
          { metric: 'Current price', value: `$${currentPrice.toFixed(2)}` },
          { metric: 'Change', value: `${priceChange >= 0 ? '+' : ''}$${priceChange.toFixed(2)} (${priceChangePercent.toFixed(2)}%)` },
          { metric: '24h high', value: `$${stats.maxPrice.toFixed(2)}` },
          { metric: '24h low', value: `$${stats.minPrice.toFixed(2)}` },
          { metric: 'Avg volume', value: `${(stats.avgVolume / 1000000).toFixed(2)}M` },
          { metric: 'Data points', value: String(chartData.length) },
        ]}
      >
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={chartData}
          margin={{ top: 10, right: 30, left: 0, bottom: 30 }}
        >
          {/* Grid background */}
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />

          {/* X-axis: Time labels */}
          <XAxis
            dataKey="time"
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
            tick={{ angle: -45, textAnchor: 'end', height: 60 }}
          />

          {/* Left Y-axis: Price in USD */}
          <YAxis
            yAxisId="left"
            label={{ value: 'Price (USD)', angle: -90, position: 'insideLeft' }}
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
            domain={['dataMin - 10', 'dataMax + 10']}
          />

          {/* Right Y-axis: Volume */}
          <YAxis
            yAxisId="right"
            orientation="right"
            label={{ value: 'Volume', angle: 90, position: 'insideRight' }}
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
          />

          {/* Tooltip on hover */}
          <Tooltip content={<CustomTooltip />} />

          {/* Legend */}
          <Legend
            wrapperStyle={{ paddingTop: '20px', fontSize: '12px' }}
            iconType="line"
          />

          {/* Volume bars (background) */}
          <Bar
            yAxisId="right"
            dataKey="volume"
            fill="#d1d5db"
            fillOpacity={0.3}
            name="Volume"
            isAnimationActive={false}
          />

          {/* High/Low price band (area) */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="high"
            stroke="#e0e7ff"
            strokeWidth={1}
            dot={false}
            name="High"
            isAnimationActive={false}
            legendType="line"
          />

          <Line
            yAxisId="left"
            type="monotone"
            dataKey="low"
            stroke="#e0e7ff"
            strokeWidth={1}
            dot={false}
            name="Low"
            isAnimationActive={false}
            legendType="line"
          />

          {/* Close price line (main indicator) */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="close"
            stroke="#3b82f6"
            strokeWidth={2.5}
            dot={false}
            name="Close Price"
            isAnimationActive={false}
            legendType="line"
          />

          {/* Open price line (supporting indicator) */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="open"
            stroke="#8b5cf6"
            strokeWidth={1.5}
            dot={false}
            name="Open Price"
            strokeDasharray="5 5"
            isAnimationActive={false}
            legendType="line"
          />
        </ComposedChart>
      </ResponsiveContainer>
      </ChartFigure>

      {/* Data summary statistics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-700/50">
        <div className="bg-slate-700/30 rounded p-3">
          <p className="text-xs text-slate-400 font-medium mb-1">24H High</p>
          <p className="text-lg font-bold text-slate-100">
            ${stats.maxPrice.toFixed(2)}
          </p>
        </div>

        <div className="bg-slate-700/30 rounded p-3">
          <p className="text-xs text-slate-400 font-medium mb-1">24H Low</p>
          <p className="text-lg font-bold text-slate-100">
            ${stats.minPrice.toFixed(2)}
          </p>
        </div>

        <div className="bg-slate-700/30 rounded p-3">
          <p className="text-xs text-slate-400 font-medium mb-1">Avg Volume</p>
          <p className="text-lg font-bold text-slate-100">
            {(stats.avgVolume / 1000000).toFixed(2)}M
          </p>
        </div>

        <div className="bg-slate-700/30 rounded p-3">
          <p className="text-xs text-slate-400 font-medium mb-1">Data Points</p>
          <p className="text-lg font-bold text-slate-100">
            {chartData.length}
          </p>
        </div>
      </div>
    </div>
    </TileState>
  )
}
