# Phase 1 Dashboard Implementation Guide

## Status: IN PROGRESS

### ✅ Completed (Step 1/5)

**Backend Metrics Provider Created**:
- File: `services/trading-engine/app/phase1_metrics.py` (230 lines)
- Parses Phase 1 logs and extracts metrics
- Provides real-time filtering stats, GATEKEEPER blocks, VALIDATOR rejections
- Timeline of recent signals

### 🚧 Remaining Steps

## Step 2: Add API Endpoint to Trading Engine

**File to Edit**: `services/trading-engine/app/main.py`

**Add import at top** (after line 30):
```python
from app.phase1_metrics import get_phase1_metrics
```

**Add endpoint** (after line 386, before root endpoint):
```python
# Phase 1 Metrics endpoints
@app.get("/api/v1/phase1/metrics", tags=["Phase 1"])
async def get_phase1_metrics_endpoint(hours: int = 24):
    """
    Get Phase 1 performance metrics

    Args:
        hours: Number of hours to analyze (default: 24)

    Returns:
        Phase 1 metrics including filtering rates, GATEKEEPER/VALIDATOR stats
    """
    try:
        provider = get_phase1_metrics()
        metrics = provider.get_metrics(hours=hours)

        return {
            "success": True,
            "data": metrics,
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        logger.error(f"Error getting Phase 1 metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/phase1/health", tags=["Phase 1"])
async def get_phase1_health():
    """Get Phase 1 system health status"""
    try:
        provider = get_phase1_metrics()
        health = provider.get_system_health()

        return {
            "success": True,
            "data": health,
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        logger.error(f"Error getting Phase 1 health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/phase1/latest", tags=["Phase 1"])
async def get_latest_phase1_signal():
    """Get the most recent Phase 1 signal"""
    try:
        provider = get_phase1_metrics()
        signal = provider.get_latest_signal()

        if not signal:
            return {
                "success": True,
                "data": None,
                "message": "No recent signals",
                "timestamp": int(time.time() * 1000)
            }

        return {
            "success": True,
            "data": signal,
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        logger.error(f"Error getting latest Phase 1 signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Update root endpoint** (line 399) to include Phase 1 endpoints:
```python
"endpoints": {
    "health": "/health",
    "status": "/status",
    "docs": "/docs",
    "signals": "/api/v1/signals/{symbol}",
    "positions": "/api/v1/positions",
    "performance": "/api/v1/performance",
    "phase1_metrics": "/api/v1/phase1/metrics",      # NEW
    "phase1_health": "/api/v1/phase1/health",        # NEW
    "phase1_latest": "/api/v1/phase1/latest"         # NEW
}
```

**Restart trading-engine**:
```bash
# Kill existing
pkill -f "trading-engine"

# Restart
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine
PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005 > /tmp/trading-engine.log 2>&1 &
```

**Test endpoints**:
```bash
curl http://localhost:8005/api/v1/phase1/metrics
curl http://localhost:8005/api/v1/phase1/health
curl http://localhost:8005/api/v1/phase1/latest
```

## Step 3: Create React Dashboard Component

**File to Create**: `frontend/src/pages/Phase1Dashboard.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

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
  filtering: {
    hold_rate: number;
    action_rate: number;
    reduction_rate: number;
  };
  timeline: Array<{
    timestamp: string;
    action: string;
    confidence: number | null;
  }>;
}

const Phase1Dashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<Phase1Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(24);

  // Fetch metrics from API
  const fetchMetrics = async () => {
    try {
      const response = await fetch(`http://localhost:8005/api/v1/phase1/metrics?hours=${timeRange}`);
      const data = await response.json();
      if (data.success) {
        setMetrics(data.data);
      }
    } catch (error) {
      console.error('Error fetching Phase 1 metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  // Auto-refresh every 30 seconds
  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 30000);
    return () => clearInterval(interval);
  }, [timeRange]);

  if (loading || !metrics) {
    return <div className="p-8">Loading Phase 1 metrics...</div>;
  }

  // Prepare chart data
  const signalDistribution = [
    { name: 'BUY', value: metrics.signals.buy, color: '#10b981' },
    { name: 'SELL', value: metrics.signals.sell, color: '#ef4444' },
    { name: 'HOLD', value: metrics.signals.hold, color: '#6b7280' }
  ];

  const filteringData = [
    { name: 'HOLD Rate', value: metrics.filtering.hold_rate },
    { name: 'Action Rate', value: metrics.filtering.action_rate }
  ];

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Phase 1 Monitoring Dashboard</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setTimeRange(1)}
            className={`px-4 py-2 rounded ${timeRange === 1 ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            1H
          </button>
          <button
            onClick={() => setTimeRange(24)}
            className={`px-4 py-2 rounded ${timeRange === 24 ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            24H
          </button>
          <button
            onClick={() => setTimeRange(168)}
            className={`px-4 py-2 rounded ${timeRange === 168 ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
          >
            7D
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-gray-500">Total Signals</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{metrics.signals.total}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-gray-500">HOLD Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{metrics.filtering.hold_rate.toFixed(1)}%</div>
            <p className="text-xs text-gray-500 mt-1">
              {metrics.filtering.hold_rate > 60 ? '✅ Protecting capital' : 'Normal filtering'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-gray-500">GATEKEEPER Blocks</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-orange-600">{metrics.gatekeeper.blocks}</div>
            <p className="text-xs text-gray-500 mt-1">Counter-trend trades prevented</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-gray-500">VALIDATOR Rejections</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-red-600">{metrics.validator.rejected}</div>
            <p className="text-xs text-gray-500 mt-1">Low-volume signals filtered</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Signal Distribution Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Signal Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={signalDistribution}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={(entry) => `${entry.name}: ${entry.value}`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {signalDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Filtering Effectiveness */}
        <Card>
          <CardHeader>
            <CardTitle>Filtering Effectiveness</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium">HOLD Rate</span>
                  <span className="text-sm font-bold">{metrics.filtering.hold_rate.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div
                    className="bg-blue-600 h-2.5 rounded-full"
                    style={{ width: `${metrics.filtering.hold_rate}%` }}
                  ></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium">Action Rate</span>
                  <span className="text-sm font-bold">{metrics.filtering.action_rate.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div
                    className="bg-green-600 h-2.5 rounded-full"
                    style={{ width: `${metrics.filtering.action_rate}%` }}
                  ></div>
                </div>
              </div>

              <div className="pt-4 border-t">
                <p className="text-sm text-gray-600">
                  <strong>Goal:</strong> 40-50% filtering rate
                </p>
                <p className="text-sm text-gray-600 mt-1">
                  <strong>Status:</strong> {
                    metrics.filtering.hold_rate >= 40 && metrics.filtering.hold_rate <= 60
                      ? '✅ Meeting target'
                      : metrics.filtering.hold_rate > 60
                      ? '⚠️ Aggressive filtering (protecting capital)'
                      : '⚠️ Low filtering'
                  }
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Signals Timeline */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Signals (Last 20)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {metrics.timeline.slice(0, 20).map((signal, index) => (
              <div key={index} className="flex items-center justify-between p-3 border rounded">
                <div className="flex items-center gap-3">
                  <Badge
                    variant={signal.action === 'BUY' ? 'default' : signal.action === 'SELL' ? 'destructive' : 'secondary'}
                  >
                    {signal.action}
                  </Badge>
                  <span className="text-sm text-gray-600">
                    {new Date(signal.timestamp).toLocaleString()}
                  </span>
                </div>
                {signal.confidence && (
                  <span className="text-sm font-medium">
                    Confidence: {(signal.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Phase 1 Goals Progress */}
      <Card>
        <CardHeader>
          <CardTitle>Phase 1 Goals Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-1">
                <span className="font-medium">Goal 1: Increase Win Rate (+10-15%)</span>
                <span className="text-sm text-gray-500">Monitoring...</span>
              </div>
              <p className="text-sm text-gray-600">Requires 7-14 days of live data</p>
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <span className="font-medium">Goal 2: Reduce Drawdown (-20-30%)</span>
                <span className="text-sm text-gray-500">Monitoring...</span>
              </div>
              <p className="text-sm text-gray-600">Requires 7-14 days of live data</p>
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <span className="font-medium">Goal 3: Signal Filtering (40-50%)</span>
                <span className={`text-sm font-bold ${
                  metrics.filtering.hold_rate >= 40 && metrics.filtering.hold_rate <= 60
                    ? 'text-green-600'
                    : 'text-orange-600'
                }`}>
                  {metrics.filtering.hold_rate >= 40 ? '✅ On Track' : '⚠️ Below Target'}
                </span>
              </div>
              <p className="text-sm text-gray-600">
                Current: {metrics.filtering.hold_rate.toFixed(1)}% | Target: 40-50%
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Phase1Dashboard;
```

## Step 4: Add Route to Frontend

**File to Edit**: `frontend/src/App.tsx`

**Add import**:
```typescript
import Phase1Dashboard from './pages/Phase1Dashboard';
```

**Add route** (in your router configuration):
```typescript
<Route path="/phase1" element={<Phase1Dashboard />} />
```

## Step 5: Add Navigation Link

**File to Edit**: `frontend/src/components/Navigation.tsx` (or wherever your nav is)

**Add link**:
```typescript
<Link to="/phase1">Phase 1 Dashboard</Link>
```

## Step 6: Install Chart Dependencies

```bash
cd frontend
npm install recharts
```

## Step 7: Restart Frontend

```bash
cd frontend
npm run dev
```

## Step 8: Access Dashboard

Open browser:
```
http://localhost:5173/phase1
```

## Features Included

✅ Real-time metrics display (auto-refresh every 30 seconds)
✅ Signal distribution pie chart
✅ Filtering effectiveness bars
✅ GATEKEEPER blocks counter
✅ VALIDATOR rejections counter
✅ Recent signals timeline (last 20)
✅ Phase 1 goals progress tracker
✅ Time range selector (1H, 24H, 7D)
✅ Responsive design

## API Endpoints

Once Step 2 is complete, these endpoints will be available:

```
GET /api/v1/phase1/metrics?hours=24
GET /api/v1/phase1/health
GET /api/v1/phase1/latest
```

## Testing

**1. Test backend endpoints**:
```bash
curl http://localhost:8005/api/v1/phase1/metrics?hours=24 | jq
curl http://localhost:8005/api/v1/phase1/health | jq
curl http://localhost:8005/api/v1/phase1/latest | jq
```

**2. Open dashboard in browser**:
- Navigate to `http://localhost:5173/phase1`
- Should see real-time metrics
- Change time range (1H, 24H, 7D) to verify data updates
- Check that it refreshes automatically every 30 seconds

## Troubleshooting

**No data showing**:
- Check if log file exists: `ls -lh /tmp/trading-engine-phase1.log`
- Check if signals are being generated: `tail /tmp/trading-engine-phase1.log`
- Verify API responds: `curl http://localhost:8005/api/v1/phase1/metrics`

**Frontend errors**:
- Check browser console for errors
- Verify trading-engine is running: `curl http://localhost:8005/health`
- Check CORS is enabled in trading-engine

**Charts not rendering**:
- Ensure `recharts` is installed: `npm list recharts`
- Check for TypeScript errors: `npm run build`

## Next Enhancements (Optional)

After basic dashboard works, you can add:
- WebSocket real-time updates (instead of polling)
- Export metrics to CSV/JSON
- Historical performance charts (trend over days)
- Alert notifications when filtering rate changes significantly
- Indicator value charts (RSI, MACD, etc. over time)

## Files Created/Modified

✅ Created:
- `services/trading-engine/app/phase1_metrics.py` (230 lines)
- `frontend/src/pages/Phase1Dashboard.tsx` (code above)

🚧 Need to Edit:
- `services/trading-engine/app/main.py` (add 3 endpoints)
- `frontend/src/App.tsx` (add 1 route)
- `frontend/src/components/Navigation.tsx` (add 1 link)

## Estimated Time to Complete

- Step 2 (Backend endpoint): 5 minutes
- Step 3-5 (Frontend): 15 minutes
- Step 6-8 (Setup & test): 10 minutes

**Total: ~30 minutes to have working dashboard**

---

**Current Status**: Backend metrics provider complete. Continue with Step 2 to add API endpoints.
