import React, { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

// Type definitions for live prices
interface TickerData {
  symbol: string;
  last_price: number;
  price_change_24h: number;
  high_24h: number;
  low_24h: number;
  volume_24h: number;
}

interface CryptoPrice {
  symbol: string;
  name: string;
  icon: string;
  price: number;
  change24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
  loading: boolean;
  error: boolean;
}

// Type definitions for Phase 1 metrics
interface Phase1Metrics {
  period_hours: number;
  signals: {
    total: number;
    buy: number;
    sell: number;
    hold: number;
  };
  gatekeeper: {
    blocks: number;
    bullish_trends: number;
    bearish_trends: number;
    neutral_trends: number;
  };
  validator: {
    confirmed: number;
    rejected: number;
  };
  atr: {
    extreme: number;
    high: number;
    medium: number;
    low: number;
  };
  stochastic: {
    overbought: number;
    oversold: number;
  };
  filtering: {
    hold_rate: number;
    action_rate: number;
    reduction_rate: number;
  };
  timeline: Array<{
    timestamp: string;
    action: string;
    confidence: number | null;
    filters: {
      gatekeeper: boolean;
      validator: boolean;
      atr: boolean;
      trend: boolean;
    };
  }>;
}

interface SystemHealth {
  status: string;
  last_signal_time: string | null;
  signals_last_hour: number;
  filters_active: {
    gatekeeper: boolean;
    validator: boolean;
    atr: boolean;
  };
}

// Crypto symbols to track
const TRACKED_CRYPTOS = [
  { symbol: 'BTCUSDT', name: 'Bitcoin', icon: '₿' },
  { symbol: 'ETHUSDT', name: 'Ethereum', icon: 'Ξ' },
  { symbol: 'BNBUSDT', name: 'BNB', icon: '◆' },
  { symbol: 'SOLUSDT', name: 'Solana', icon: '◎' },
];

const Phase1Dashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<Phase1Metrics | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [timeRange, setTimeRange] = useState(24); // 1H, 24H, 7D
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cryptoPrices, setCryptoPrices] = useState<CryptoPrice[]>(
    TRACKED_CRYPTOS.map(c => ({
      ...c,
      price: 0,
      change24h: 0,
      high24h: 0,
      low24h: 0,
      volume24h: 0,
      loading: true,
      error: false,
    }))
  );

  // Fetch Phase 1 metrics
  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch metrics
      const metricsResponse = await fetch(
        `http://localhost:8005/api/v1/phase1/metrics?hours=${timeRange}`
      );
      const metricsData = await metricsResponse.json();

      if (metricsData.success) {
        setMetrics(metricsData.data);
      } else {
        setError('Failed to fetch metrics');
      }

      // Fetch health
      const healthResponse = await fetch('http://localhost:8005/api/v1/phase1/health');
      const healthData = await healthResponse.json();

      if (healthData.success) {
        setHealth(healthData.data);
      }

      setLoading(false);
    } catch (err) {
      setError(`Error fetching data: ${err}`);
      setLoading(false);
    }
  };

  // Fetch live crypto prices
  const fetchPrices = async () => {
    const updatedPrices = await Promise.all(
      TRACKED_CRYPTOS.map(async (crypto) => {
        try {
          const response = await fetch(
            `http://localhost:8002/api/v1/ticker/${crypto.symbol}`
          );
          const data = await response.json();

          if (data.success && data.data) {
            return {
              ...crypto,
              price: data.data.last_price,
              change24h: data.data.price_change_24h * 100,
              high24h: data.data.high_24h,
              low24h: data.data.low_24h,
              volume24h: data.data.volume_24h,
              loading: false,
              error: false,
            };
          }
          return { ...crypto, price: 0, change24h: 0, high24h: 0, low24h: 0, volume24h: 0, loading: false, error: true };
        } catch {
          return { ...crypto, price: 0, change24h: 0, high24h: 0, low24h: 0, volume24h: 0, loading: false, error: true };
        }
      })
    );
    setCryptoPrices(updatedPrices);
  };

  // Auto-refresh metrics every 30 seconds
  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 30000);
    return () => clearInterval(interval);
  }, [timeRange]);

  // Auto-refresh prices every 5 seconds
  useEffect(() => {
    fetchPrices();
    const priceInterval = setInterval(fetchPrices, 5000);
    return () => clearInterval(priceInterval);
  }, []);

  // Prepare data for charts
  const signalDistributionData = metrics
    ? [
        { name: 'BUY', value: metrics.signals.buy, color: '#10b981' },
        { name: 'SELL', value: metrics.signals.sell, color: '#ef4444' },
        { name: 'HOLD', value: metrics.signals.hold, color: '#f59e0b' }
      ]
    : [];

  const atrDistributionData = metrics
    ? [
        { name: 'Extreme', value: metrics.atr.extreme, color: '#ef4444' },
        { name: 'High', value: metrics.atr.high, color: '#f59e0b' },
        { name: 'Medium', value: metrics.atr.medium, color: '#3b82f6' },
        { name: 'Low', value: metrics.atr.low, color: '#10b981' }
      ]
    : [];

  const COLORS = ['#10b981', '#ef4444', '#f59e0b', '#3b82f6'];

  if (loading && !metrics) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-xl text-gray-600">Loading Phase 1 Dashboard...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Phase 1 Dashboard</h1>
          <p className="text-gray-600 mt-2">
            Real-time monitoring of trading signal filtering and quality control
          </p>
        </div>

        {/* Live Crypto Prices Ticker */}
        <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-xl shadow-lg p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              Live Prices
            </h2>
            <span className="text-xs text-gray-400">Updates every 5s</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {cryptoPrices.map((crypto) => (
              <div
                key={crypto.symbol}
                className="bg-gray-800/50 rounded-lg p-4 border border-gray-700 hover:border-gray-600 transition-all"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{crypto.icon}</span>
                    <div>
                      <div className="text-white font-semibold">{crypto.name}</div>
                      <div className="text-gray-400 text-xs">{crypto.symbol}</div>
                    </div>
                  </div>
                </div>
                {crypto.loading ? (
                  <div className="text-gray-400 text-lg">Loading...</div>
                ) : crypto.error ? (
                  <div className="text-red-400 text-lg">Error</div>
                ) : (
                  <>
                    <div className="text-2xl font-bold text-white">
                      ${crypto.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className={`flex items-center gap-1 text-sm mt-1 ${crypto.change24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      <span>{crypto.change24h >= 0 ? '▲' : '▼'}</span>
                      <span>{Math.abs(crypto.change24h).toFixed(2)}%</span>
                      <span className="text-gray-500 ml-2">24h</span>
                    </div>
                    <div className="mt-2 pt-2 border-t border-gray-700">
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-400">H: ${crypto.high24h.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                        <span className="text-gray-400">L: ${crypto.low24h.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Vol: {(crypto.volume24h).toLocaleString(undefined, { maximumFractionDigits: 0 })} {crypto.symbol.replace('USDT', '')}
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {/* Time Range Selector */}
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <div className="flex gap-4">
            <button
              onClick={() => setTimeRange(1)}
              className={`px-4 py-2 rounded ${
                timeRange === 1
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Last 1H
            </button>
            <button
              onClick={() => setTimeRange(24)}
              className={`px-4 py-2 rounded ${
                timeRange === 24
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Last 24H
            </button>
            <button
              onClick={() => setTimeRange(168)}
              className={`px-4 py-2 rounded ${
                timeRange === 168
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Last 7D
            </button>
          </div>
        </div>

        {/* System Health */}
        {health && (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">System Health</h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="text-center">
                <div
                  className={`text-3xl font-bold ${
                    health.status === 'healthy' ? 'text-green-600' : 'text-yellow-600'
                  }`}
                >
                  {health.status === 'healthy' ? '✓' : '⚠'}
                </div>
                <div className="text-gray-600 text-sm mt-2">
                  {health.status === 'healthy' ? 'Healthy' : 'Warning'}
                </div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {health.signals_last_hour}
                </div>
                <div className="text-gray-600 text-sm mt-2">Signals (1H)</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {health.filters_active.gatekeeper ? '✓' : '✗'}
                </div>
                <div className="text-gray-600 text-sm mt-2">GATEKEEPER</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {health.filters_active.validator ? '✓' : '✗'}
                </div>
                <div className="text-gray-600 text-sm mt-2">VALIDATOR</div>
              </div>
            </div>
          </div>
        )}

        {/* Summary Cards */}
        {metrics && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-gray-600 text-sm font-medium">Total Signals</h3>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {metrics.signals.total}
              </p>
              <p className="text-gray-500 text-sm mt-1">Last {timeRange}H</p>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-gray-600 text-sm font-medium">HOLD Rate</h3>
              <p className="text-3xl font-bold text-yellow-600 mt-2">
                {metrics.filtering.hold_rate.toFixed(1)}%
              </p>
              <p className="text-gray-500 text-sm mt-1">Signals Filtered</p>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-gray-600 text-sm font-medium">GATEKEEPER Blocks</h3>
              <p className="text-3xl font-bold text-red-600 mt-2">
                {metrics.gatekeeper.blocks}
              </p>
              <p className="text-gray-500 text-sm mt-1">Counter-trend Blocked</p>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-gray-600 text-sm font-medium">VALIDATOR Rejections</h3>
              <p className="text-3xl font-bold text-orange-600 mt-2">
                {metrics.validator.rejected}
              </p>
              <p className="text-gray-500 text-sm mt-1">Low Volume Rejected</p>
            </div>
          </div>
        )}

        {/* Charts Row */}
        {metrics && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            {/* Signal Distribution */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold mb-4">Signal Distribution</h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={signalDistributionData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name}: ${value}`}
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {signalDistributionData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* ATR Volatility Distribution */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold mb-4">ATR Volatility Levels</h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={atrDistributionData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name}: ${value}`}
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {atrDistributionData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Filter Performance */}
        {metrics && (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h3 className="text-lg font-semibold mb-4">Filter Performance</h3>
            <div className="space-y-4">
              {/* GATEKEEPER */}
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">GATEKEEPER (Trend Filter)</span>
                  <span className="text-sm text-gray-600">
                    {metrics.gatekeeper.blocks} blocks
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full"
                    style={{
                      width: `${
                        metrics.signals.total > 0
                          ? (metrics.gatekeeper.blocks / metrics.signals.total) * 100
                          : 0
                      }%`
                    }}
                  ></div>
                </div>
                <div className="flex justify-between mt-1 text-xs text-gray-500">
                  <span>Bullish: {metrics.gatekeeper.bullish_trends}</span>
                  <span>Bearish: {metrics.gatekeeper.bearish_trends}</span>
                  <span>Neutral: {metrics.gatekeeper.neutral_trends}</span>
                </div>
              </div>

              {/* VALIDATOR */}
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">VALIDATOR (Volume Check)</span>
                  <span className="text-sm text-gray-600">
                    {metrics.validator.rejected} rejections
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full"
                    style={{
                      width: `${
                        metrics.signals.total > 0
                          ? (metrics.validator.confirmed /
                              (metrics.validator.confirmed + metrics.validator.rejected)) *
                            100
                          : 0
                      }%`
                    }}
                  ></div>
                </div>
                <div className="flex justify-between mt-1 text-xs text-gray-500">
                  <span>Confirmed: {metrics.validator.confirmed}</span>
                  <span>Rejected: {metrics.validator.rejected}</span>
                </div>
              </div>

              {/* Overall Filtering */}
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">Overall Filtering</span>
                  <span className="text-sm text-gray-600">
                    {metrics.filtering.hold_rate.toFixed(1)}% filtered
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-yellow-600 h-2 rounded-full"
                    style={{ width: `${metrics.filtering.hold_rate}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Recent Signals Timeline */}
        {metrics && metrics.timeline.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-4">Recent Signals</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-4 text-sm font-medium text-gray-700">
                      Time
                    </th>
                    <th className="text-left py-2 px-4 text-sm font-medium text-gray-700">
                      Action
                    </th>
                    <th className="text-left py-2 px-4 text-sm font-medium text-gray-700">
                      Confidence
                    </th>
                    <th className="text-left py-2 px-4 text-sm font-medium text-gray-700">
                      GATEKEEPER
                    </th>
                    <th className="text-left py-2 px-4 text-sm font-medium text-gray-700">
                      VALIDATOR
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.timeline.slice(0, 10).map((signal, idx) => (
                    <tr key={idx} className="border-b hover:bg-gray-50">
                      <td className="py-2 px-4 text-sm text-gray-600">
                        {new Date(signal.timestamp).toLocaleString()}
                      </td>
                      <td className="py-2 px-4">
                        <span
                          className={`px-2 py-1 rounded text-xs font-medium ${
                            signal.action === 'BUY'
                              ? 'bg-green-100 text-green-800'
                              : signal.action === 'SELL'
                              ? 'bg-red-100 text-red-800'
                              : 'bg-yellow-100 text-yellow-800'
                          }`}
                        >
                          {signal.action}
                        </span>
                      </td>
                      <td className="py-2 px-4 text-sm text-gray-600">
                        {signal.confidence ? signal.confidence.toFixed(2) : 'N/A'}
                      </td>
                      <td className="py-2 px-4 text-sm">
                        {signal.filters.gatekeeper ? (
                          <span className="text-green-600">✓ Passed</span>
                        ) : (
                          <span className="text-red-600">✗ Blocked</span>
                        )}
                      </td>
                      <td className="py-2 px-4 text-sm">
                        {signal.filters.validator ? (
                          <span className="text-green-600">✓ Confirmed</span>
                        ) : (
                          <span className="text-red-600">✗ Rejected</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* No Signals Message */}
        {metrics && metrics.timeline.length === 0 && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="text-center text-gray-500 py-8">
              <p className="text-lg">No signals recorded yet in the selected time range.</p>
              <p className="text-sm mt-2">The dashboard will auto-refresh every 30 seconds.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Phase1Dashboard;
