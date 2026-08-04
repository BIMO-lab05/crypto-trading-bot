# PriceChart Component

> Merged from `frontend/PRICE_CHART_README.md`, `frontend/README_PRICECHART.md`, `frontend/COMPONENT_STRUCTURE.md`, and `frontend/CODE_SNIPPETS.md` on 2026-07-30. The index file (`README_PRICECHART.md`) was pure navigation and its content was dropped. References to `PRICE_CHART_INTEGRATION.md`, `INTEGRATION_SUMMARY.md`, and `IMPLEMENTATION_COMPLETE.md` were removed — those files no longer exist in the repo.

Professional price chart component (React 18 + Recharts) that displays 24-hour cryptocurrency price history with interactive visualization, integrated into the dashboard.

## Overview

**What it does:**
- Interactive line chart with 4 price indicators (Open, High, Low, Close)
- Volume bar chart overlay
- Real-time updates every 60 seconds (React Query polling)
- Custom tooltip with OHLCV data on hover
- Statistics panel (24H High/Low, Avg Volume, data-point count)
- Loading skeleton, error message, and empty-data states
- Responsive design (mobile/tablet/desktop), Tailwind styling
- Color-coded gains/losses

> **Note (2026-07-30):** Dashboard tiles standardized on the shared **TileState** error/empty/loading pattern on 2026-07-28. PriceChart's loading/error/empty renderers described below predate that; when touching this component's state handling, align it with TileState.

**Files:**

| File | Type | Purpose |
|------|------|---------|
| `src/components/PriceChart.jsx` | Component (339 lines, fully commented) | Main price chart with Recharts |
| `src/components/Dashboard.jsx` | Modified | Added PriceChart to dashboard layout |

**Dependencies** (all already installed, no additional packages required):
- `recharts` (v2.15.4) — chart library
- `date-fns` (v2.30.0) — date formatting
- `@tanstack/react-query` (v5.12.2) — data fetching

## Quick Start

```bash
npm run dev
# Open http://localhost:3000
# Chart appears under "Price Tickers" section
```

> **Corrected 2026-07-30:** earlier docs said `http://localhost:5173` (Vite's out-of-the-box default). This project's frontend serves on **:3000**.

Production build:
```bash
npm run build
npm run preview
```

## Props / Usage

```jsx
import PriceChart from './components/PriceChart'

<PriceChart
  symbol="BTCUSDT"  // Trading pair (default: BTCUSDT)
  interval="60"     // Candle size in minutes (default: 60)
/>
```

```typescript
interface PriceChartProps {
  // Trading symbol (e.g., 'BTCUSDT', 'ETHUSDT')
  symbol: string = 'BTCUSDT'

  // Kline interval in minutes
  // Valid values: '1', '5', '15', '30', '60', '240', '1440'
  interval: string = '60'
}
```

Examples:
```jsx
<PriceChart />                                  // default BTCUSDT, 1h candles
<PriceChart symbol="ETHUSDT" interval="60" />   // different symbol
<PriceChart symbol="BTCUSDT" interval="5" />    // 5-minute candles
<PriceChart symbol="BTCUSDT" interval="240" />  // 4-hour candles
```

## API Integration

The frontend talks **only to the api-gateway on :8000**; routes are `/api/<domain>/...` with **no `/v1` prefix** (the gateway dropped `/v1` — older docs showing `/api/v1/...` are stale).

**Endpoint used:**
```
GET /api/market/kline/{symbol}
Query Params:
  - interval: "60" (minutes)
  - limit: 24 (number of candles)
```

Requests go through the axios instance at `baseURL='/api'`, which the gateway routes to the backing service.

**Expected response (array format):**
```javascript
[
  [openTime, open, high, low, close, volume],
  [1700610600000, 42500, 42850.50, 42300, 42750, 125.5],
  // ... more candles
]
```

The component also handles **object format** responses:
```javascript
[
  {
    open_time: 1700610600000,
    open: 42500,
    high: 42850.50,
    low: 42300.25,
    close: 42750,
    volume: 125.5,
  },
  // ...
]
```

**Backend contract (FastAPI reference implementation):**
```python
from fastapi import APIRouter, Query
from typing import List

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/kline/{symbol}")
async def get_klines(
    symbol: str,
    interval: str = "60",
    limit: int = 24
) -> List[List]:
    """
    Get kline/candlestick data for a symbol
    Returns data in array format: [openTime, open, high, low, close, volume]
    """
    klines = await fetch_klines_from_db(symbol, interval, limit)
    return [
        [
            candle.open_time.timestamp() * 1000,  # milliseconds
            float(candle.open),
            float(candle.high),
            float(candle.low),
            float(candle.close),
            float(candle.volume),
        ]
        for candle in klines
    ]
```

## Architecture & Structure

### Component hierarchy (within Dashboard)

```
Dashboard.jsx (Main Dashboard)
│
├── Header (Logo & Title, Status Indicator)
│
├── Main Content (max-width 7xl)
│   ├── Section 1: Price Tickers (PriceTickerGrid)
│   │
│   ├── Section 2: PRICE CHART
│   │   └── PriceChart (symbol="BTCUSDT", interval="60")
│   │       ├── useKlines Hook
│   │       │   └── Fetches /api/market/kline/BTCUSDT via api-gateway :8000
│   │       ├── Data Transformation (useMemo)
│   │       ├── State Management (isLoading / error / data)
│   │       ├── Chart Rendering
│   │       │   ├── Header (Symbol, Current Price, 24H Change)
│   │       │   ├── ResponsiveContainer → Recharts ComposedChart
│   │       │   │   ├── CartesianGrid
│   │       │   │   ├── XAxis (Time), YAxis Left (Price USD), YAxis Right (Volume)
│   │       │   │   ├── Tooltip (Custom), Legend
│   │       │   │   ├── Bar (Volume)
│   │       │   │   └── Lines: Close (primary), Open, High band, Low band
│   │       │   └── Footer (24H High, 24H Low, Avg Volume, Data Points)
│   │       └── State Renderers (Loading skeleton / Error / Empty)
│   │
│   ├── Section 3: Trading Signals (TradingSignals)
│   ├── Section 4: Portfolio & Emergency Stop (PortfolioCard, EmergencyStop)
│   └── Information Banners & Config
│
└── Footer (Version & Status)
```

### File organization

```
frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard.jsx          (Modified - PriceChart import & usage)
│   │   ├── PriceChart.jsx         (Main component, 339 lines)
│   │   ├── PriceTickerGrid.jsx    (Existing)
│   │   ├── TradingSignals.jsx     (Existing)
│   │   ├── PortfolioCard.jsx      (Existing)
│   │   └── EmergencyStop.jsx      (Existing)
│   ├── hooks/
│   │   ├── useTicker.js           (Existing - includes useKlines)
│   │   ├── usePortfolio.js        (Existing)
│   │   └── useSignals.js          (Existing)
│   ├── services/
│   │   └── api.js                 (Existing - marketAPI.getKlines)
│   └── main.jsx, App.jsx          (Existing)
└── package.json                   (No changes needed)
```

### Data flow

1. Dashboard renders → `PriceChart` mounts with props `symbol="BTCUSDT"`, `interval="60"`.
2. `useKlines` hook creates a React Query:
   ```
   queryKey: ['klines', 'BTCUSDT', '60', { limit: 24 }]
   queryFn:  () => marketAPI.getKlines(...)
   refetchInterval: 60000 (1 minute)
   ```
3. Request: `GET /api/market/kline/BTCUSDT?interval=60&limit=24` (axios `baseURL='/api'`).
4. **api-gateway (:8000)** routes the request to the backing candle store (market-data-service ingests candles into TimescaleDB).
   > **Corrected 2026-07-30:** an earlier diagram said "market-data-service (port 8005)". market-data-service is **:8002** (8005 is trading-engine), and the frontend never calls services directly — everything goes through the gateway on :8000.
5. Response cached by React Query; component state updates (`isLoading=false`, `data=[...]`).
6. Data transformation (`useMemo`): per candle, parse numeric values, format timestamp to `HH:MM`, calculate mid-range →
   ```javascript
   { time: "14:30", timestamp: 1700610600000, open: 42500.00, high: 42850.50,
     low: 42300.25, close: 42750.00, volume: 125.5, mid: 42575.38 }
   ```
7. Statistics calculation (`useMemo`): `minPrice = min(lows)`, `maxPrice = max(highs)`, `avgVolume = sum(volumes)/count`.
8. Render: header (current price, 24H change), chart, footer stats. Hover shows custom OHLCV tooltip.
9. Auto-refetch repeats every 60 seconds.

### Hook integration

```
useKlines(symbol, interval, params)
  ├── Uses React Query (useQuery)
  ├── Key: ['klines', symbol, interval, params]
  ├── Function: marketAPI.getKlines(symbol, interval, params)
  ├── Refetch: Every 60 seconds
  └── Returns: {
      data: OHLCV[],      // Array of candlesticks
      isLoading: boolean, // Fetching in progress
      error: Error | null // Any error that occurred
    }
```

### Recharts composition

```
ComposedChart
├── CartesianGrid (background grid)
├── XAxis (dataKey: 'time', labels rotated -45°)
├── YAxis Left  (Price USD, domain [min-10, max+10])
├── YAxis Right (Volume, orientation: right)
├── Tooltip (custom, OHLCV on hover)
├── Legend
├── Bar   (volume, yAxisId 'right', fill #d1d5db, fillOpacity 0.3)
└── Line × 4
    ├── Close (primary): stroke #3b82f6, strokeWidth 2.5
    ├── High band: stroke #e0e7ff
    ├── Low band:  stroke #e0e7ff
    └── Open: stroke #8b5cf6, strokeDasharray '5 5'
```

### Color scheme

```
Primary:
  - Close Price Line: #3b82f6 (blue-500)
  - Open Price Line:  #8b5cf6 (purple-500)
  - High/Low Bands:   #e0e7ff (indigo-100)
  - Volume Bars:      #d1d5db (gray-300)
Text:
  - Headers: #1f2937 (gray-900) | Labels: #6b7280 (gray-500) | Values: #1f2937 (gray-800)
Positive/Negative:
  - Gains: #22c55e (green-500) | Losses: #dc2626 (red-600)
Background:
  - Cards: #ffffff | Container: #f3f4f6 (gray-100)
```

### Responsive breakpoints

```
Mobile (<768px):       2-column stats grid, full-width chart (400px), stacked layout
Tablet (768-1024px):   4-column stats grid, full-width chart (400px), side-by-side
Desktop (>1024px):     4-column stats grid, full-width chart (400px), integrated dashboard
```

### State management flow

```
Mount → isLoading=true → Skeleton loader
      → API call
        ├─ Success → data loaded, isLoading=false → chartData (useMemo) → render chart
        └─ Error   → error set → render error message
      → auto-refetch after 60s (repeats)
```

### Error handling strategy

| Error type | Cause | Behavior |
|---|---|---|
| API connection error | Backend not running | "Error Loading Price Chart" + debugging info |
| Invalid data format | API returns unexpected format | Graceful fallback in data transform → empty state |
| Empty data | No kline data yet | "No price data available" placeholder until data arrives |

### Performance notes

- `useMemo` for data transformation and statistics — prevents unnecessary recalculation
- `isAnimationActive={false}` — chart animations disabled for performance
- React Query caching — prevents duplicate API calls
- Recharts handles rendering optimization for the 24 data points
- Bundle impact: +8KB (recharts already included)

## Customization

### Change symbol / timeframe (Dashboard.jsx)
```jsx
<PriceChart symbol="ETHUSDT" interval="60" />
```

### Change chart colors (PriceChart.jsx)
```jsx
// Close price line - change stroke color
<Line dataKey="close" stroke="#3b82f6" ... />
// Change to: stroke="#dc2626" for red

// Or use a gradient area:
<defs>
  <linearGradient id="colorClose" x1="0" y1="0" x2="0" y2="1">
    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
  </linearGradient>
</defs>
<Area yAxisId="left" type="monotone" dataKey="close"
      fill="url(#colorClose)" stroke="#3b82f6" />
```

### Show different number of hours (Dashboard.jsx)
```jsx
// Change limit from 24 to show more/fewer candles
const { data, isLoading, error } = useKlines(symbol, interval, { limit: 48 })
```

### Adjust refresh rate (PriceChart.jsx)
```jsx
// Change from 60000ms (1 minute) to 30000ms (30 seconds)
refetchInterval: 30000
```

## Code Snippets

### Multiple charts for different symbols
```jsx
import PriceChart from './components/PriceChart'

export default function CryptoCharts() {
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT']
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
      {symbols.map(symbol => (
        <PriceChart key={symbol} symbol={symbol} interval="60" />
      ))}
    </div>
  )
}
```

### Tabbed chart view
```jsx
import { useState } from 'react'
import PriceChart from './components/PriceChart'

export default function TabbedCharts() {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT')
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {symbols.map(symbol => (
          <button
            key={symbol}
            onClick={() => setActiveSymbol(symbol)}
            className={`px-4 py-2 rounded ${
              activeSymbol === symbol
                ? 'bg-blue-500 text-white'
                : 'bg-gray-200 text-gray-800'
            }`}
          >
            {symbol}
          </button>
        ))}
      </div>
      <PriceChart symbol={activeSymbol} interval="60" />
    </div>
  )
}
```

### Interval selector
```jsx
import { useState } from 'react'
import PriceChart from './components/PriceChart'

export default function ChartWithIntervalSelector() {
  const [interval, setInterval] = useState('60')
  const intervals = [
    { value: '5', label: '5m' },
    { value: '15', label: '15m' },
    { value: '60', label: '1h' },
    { value: '240', label: '4h' },
    { value: '1440', label: '1d' },
  ]

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {intervals.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setInterval(value)}
            className={`px-3 py-1 rounded text-sm ${
              interval === value
                ? 'bg-blue-500 text-white'
                : 'bg-gray-200 text-gray-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <PriceChart symbol="BTCUSDT" interval={interval} />
    </div>
  )
}
```

### Add RSI indicator
```jsx
// Add to PriceChart component data transformation
const chartData = useMemo(() => {
  const raw = transformToChartFormat(data)
  return raw.map((candle, index) => {
    let rsi = 50 // Default
    if (index > 14) {
      const closes = raw.slice(index - 14, index).map(c => c.close)
      rsi = calculateRSI(closes)
    }
    return { ...candle, rsi }
  })
}, [data])

// Then add to chart:
<Line yAxisId="right" dataKey="rsi" stroke="#f59e0b" name="RSI (14)" strokeWidth={2} />
```

### Error boundary wrapper
```jsx
import { Component } from 'react'

class ChartErrorBoundary extends Component {
  state = { hasError: false }

  static getDerivedStateFromError(error) {
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Chart error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-50 border border-red-200 rounded">
          <h3 className="text-red-800 font-bold">Chart Error</h3>
          <p className="text-red-700">Failed to load price chart</p>
        </div>
      )
    }
    return this.props.children
  }
}

// Usage:
<ChartErrorBoundary>
  <PriceChart />
</ChartErrorBoundary>
```

### Retry wrapper
```jsx
import { useState } from 'react'
import PriceChart from './PriceChart'

export default function ChartWithRetry() {
  const [error, setError] = useState(null)
  const [retryCount, setRetryCount] = useState(0)

  const handleRetry = () => {
    setRetryCount(prev => prev + 1)
    setError(null)
  }

  if (error && retryCount < 3) {
    return (
      <div className="p-4">
        <p className="text-red-600 mb-2">{error}</p>
        <button onClick={handleRetry}
                className="px-4 py-2 bg-blue-500 text-white rounded">
          Retry ({retryCount}/3)
        </button>
      </div>
    )
  }
  return <PriceChart />
}
```

### Memoized component
```jsx
import { memo } from 'react'
import PriceChart from './PriceChart'

// Only re-render if symbol or interval changes
const MemoizedPriceChart = memo(PriceChart, (prevProps, nextProps) => (
  prevProps.symbol === nextProps.symbol &&
  prevProps.interval === nextProps.interval
))

export default MemoizedPriceChart
```

### Lazy loading
```jsx
import { lazy, Suspense } from 'react'

const PriceChartLazy = lazy(() => import('./PriceChart'))

export default function Dashboard() {
  return (
    <Suspense fallback={<div>Loading chart...</div>}>
      <PriceChartLazy symbol="BTCUSDT" />
    </Suspense>
  )
}
```

### Virtual scrolling for many charts
```jsx
import { FixedSizeList as List } from 'react-window'
import PriceChart from './PriceChart'

export default function VirtualChartList() {
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT']

  const Row = ({ index, style }) => (
    <div style={style}>
      <PriceChart symbol={symbols[index]} interval="60" />
    </div>
  )

  return (
    <List height={800} itemCount={symbols.length} itemSize={450}>
      {Row}
    </List>
  )
}
```

### Custom tooltip formatting (prices in millions)
```jsx
const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload) return null
  const data = payload[0].payload
  return (
    <div className="bg-gray-900 text-white p-3 rounded">
      <p className="text-sm">
        <span className="text-blue-400">O:</span> ${(data.open / 1000000).toFixed(2)}M
        <span className="ml-2 text-green-400">H:</span> ${(data.high / 1000000).toFixed(2)}M
      </p>
      {/* ... more fields ... */}
    </div>
  )
}
```

## Testing

### Unit test
```jsx
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PriceChart from './PriceChart'

describe('PriceChart', () => {
  let queryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
  })

  test('renders chart with default props', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PriceChart />
      </QueryClientProvider>
    )
    expect(screen.getByText(/BTCUSDT Price Chart/i)).toBeInTheDocument()
  })

  test('displays loading skeleton initially', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PriceChart />
      </QueryClientProvider>
    )
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  test('renders with custom symbol', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PriceChart symbol="ETHUSDT" />
      </QueryClientProvider>
    )
    expect(screen.getByText(/ETHUSDT Price Chart/i)).toBeInTheDocument()
  })
})
```

### Integration test (Cypress)
```javascript
describe('PriceChart API Integration', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/market/kline/*', {
      statusCode: 200,
      body: [
        [1700610600000, 42500, 42850, 42300, 42750, 125.5],
        [1700614200000, 42750, 42900, 42400, 42600, 120.3],
      ],
    }).as('getKlines')
  })

  it('fetches and displays price chart', () => {
    cy.visit('/dashboard')
    cy.wait('@getKlines')
    cy.contains('BTCUSDT Price Chart').should('be.visible')
    cy.contains('$42,750.00').should('be.visible')
  })

  it('updates chart every 60 seconds', () => {
    cy.visit('/dashboard')
    cy.wait('@getKlines')
    cy.clock()
    cy.tick(60000)
    cy.wait('@getKlines')
  })
})
```

## Troubleshooting & Gotchas

| Issue | Solution |
|-------|----------|
| Chart is blank | Check api-gateway is running on port 8000 |
| "No data" message | Ensure `/api/market/kline/BTCUSDT` route exists on the gateway (no `/v1` prefix — the gateway dropped it; old `/api/v1/...` examples are stale) |
| Chart doesn't update | Check browser console for API errors; open DevTools Network tab and verify calls are firing; check refetch interval in useKlines |
| Tooltip doesn't appear | Move mouse over chart area |
| Performance issues | Reduce candle count (`limit`), increase refetch interval, check for other heavy components |

Gotchas:
- **Ports:** frontend :3000, api-gateway :8000. market-data-service (:8002) is never called directly by the frontend.
- **No login flow yet** — the dashboard is unauthenticated; this is a known gap that blocks LIVE mode.
- **TileState pattern (2026-07-28):** new/updated dashboard tiles should use the shared TileState error/empty/loading pattern rather than bespoke state renderers.
- **24h history:** the default `limit: 24` × 60-minute candles is what makes this a "24-hour" chart; changing either changes the window.

## Chart Layout Reference

- **Top section:** Symbol & timeframe (e.g. BTCUSDT, Last 24 hours), current price, 24H change ($ and %).
- **Main chart:** Blue line = closing price (main trend); purple dashed = opening price; light purple bands = high/low range; gray bars = volume (background); grid for reference.
- **Bottom section:** 24H High, 24H Low, Avg Volume, Data Points count.

## Browser Support

Chrome/Chromium, Edge, Firefox: full support. Safari: full support (14+). Mobile: full support.

## Next Steps / Future Enhancements

1. Test with real data (backend + market data service running)
2. Add more symbols (tabs for ETHUSDT, BNBUSDT, ...)
3. Add technical indicators (RSI, MACD, Bollinger Bands)
4. Enable WebSocket — replace polling with real-time updates
5. Add time picker for custom date ranges
6. Drawing tools / advanced interactions
