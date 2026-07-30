# PriceChart Component - Structure & Architecture

## Component Hierarchy

```
Dashboard.jsx (Main Dashboard)
│
├── Header
│   ├── Logo & Title
│   └── Status Indicator
│
├── Main Content (max-width 7xl)
│   │
│   ├── Section 1: Price Tickers
│   │   └── PriceTickerGrid
│   │       ├── BTCUSDT Ticker
│   │       ├── ETHUSDT Ticker
│   │       └── BNBUSDT Ticker
│   │
│   ├── Section 2: PRICE CHART ← NEW
│   │   └── PriceChart (symbol="BTCUSDT", interval="60")
│   │       ├── useKlines Hook
│   │       │   └── Fetches from /api/market/kline/BTCUSDT
│   │       │
│   │       ├── Data Transformation (useMemo)
│   │       │   └── Converts API data to chart format
│   │       │
│   │       ├── State Management
│   │       │   ├── isLoading State
│   │       │   ├── error State
│   │       │   └── data State
│   │       │
│   │       ├── Chart Rendering
│   │       │   ├── Header (Symbol, Current Price, Change)
│   │       │   │
│   │       │   ├── ResponsiveContainer
│   │       │   │   └── Recharts ComposedChart
│   │       │   │       ├── CartesianGrid
│   │       │   │       ├── XAxis (Time)
│   │       │   │       ├── YAxis Left (Price USD)
│   │       │   │       ├── YAxis Right (Volume)
│   │       │   │       ├── Tooltip (Custom)
│   │       │   │       ├── Legend
│   │       │   │       ├── Bar (Volume)
│   │       │   │       ├── Line (Close Price) ← Primary
│   │       │   │       ├── Line (Open Price)
│   │       │   │       ├── Line (High/Low Bands)
│   │       │   │       └── Line (Low/Low Bands)
│   │       │   │
│   │       │   └── Footer (Statistics)
│   │       │       ├── 24H High
│   │       │       ├── 24H Low
│   │       │       ├── Avg Volume
│   │       │       └── Data Points Count
│   │       │
│   │       └── State Renderers
│   │           ├── Loading: Skeleton Loader
│   │           ├── Error: Error Message
│   │           └── Empty: No Data Message
│   │
│   ├── Section 3: Trading Signals
│   │   └── TradingSignals
│   │
│   ├── Section 4: Portfolio & Emergency Stop
│   │   ├── PortfolioCard
│   │   └── EmergencyStop
│   │
│   └── Information Banners & Config
│
└── Footer
    └── Version & Status
```

## File Organization

```
frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard.jsx              (Modified - Added PriceChart import & usage)
│   │   ├── PriceChart.jsx            (New - Main component, 339 lines)
│   │   ├── PriceTickerGrid.jsx       (Existing)
│   │   ├── TradingSignals.jsx        (Existing)
│   │   ├── PortfolioCard.jsx         (Existing)
│   │   └── EmergencyStop.jsx         (Existing)
│   │
│   ├── hooks/
│   │   ├── useTicker.js              (Existing - includes useKlines)
│   │   ├── usePortfolio.js           (Existing)
│   │   └── useSignals.js             (Existing)
│   │
│   ├── services/
│   │   └── api.js                    (Existing - marketAPI.getKlines)
│   │
│   └── main.jsx, App.jsx             (Existing)
│
├── PRICE_CHART_INTEGRATION.md        (New - Full documentation)
├── PRICE_CHART_README.md             (New - Quick reference)
├── INTEGRATION_SUMMARY.md            (New - Code summary)
├── COMPONENT_STRUCTURE.md            (This file)
└── package.json                      (No changes needed)
```

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ User opens http://localhost:5173/dashboard                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Dashboard Component Renders                                 │
│ (max-width-7xl container)                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ PriceChart Component Mounts                                 │
│ Props: symbol="BTCUSDT", interval="60"                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ useKlines Hook Executed                                     │
│ Creates Query: {                                            │
│   queryKey: ['klines', 'BTCUSDT', '60', { limit: 24 }]    │
│   queryFn: () => marketAPI.getKlines(...)                  │
│   refetchInterval: 60000 (1 minute)                         │
│   enabled: true                                             │
│ }                                                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ React Query Sends API Request                               │
│ GET /api/market/kline/BTCUSDT?interval=60&limit=24          │
│ (via axios instance at baseURL='/api')                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend API Processes Request                               │
│ Service: market-data-service (port 8005)                    │
│ Returns: Array of OHLCV candles                             │
│ Format: [                                                    │
│   [openTime, open, high, low, close, volume],              │
│   ... (24 items)                                            │
│ ]                                                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Response Arrives at Frontend                                │
│ React Query caches data                                     │
│ Component state updates: isLoading = false, data = [...]   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Data Transformation (useMemo)                               │
│ Input:  [openTime, open, high, low, close, volume] array   │
│ Process: For each candle →                                  │
│   - Parse numeric values                                    │
│   - Format timestamp to HH:MM                               │
│   - Calculate mid-range                                     │
│ Output: {                                                    │
│   time: "14:30",                                            │
│   timestamp: 1700610600000,                                 │
│   open: 42500.00,                                           │
│   high: 42850.50,                                           │
│   low: 42300.25,                                            │
│   close: 42750.00,                                          │
│   volume: 125.5,                                            │
│   mid: 42575.38                                             │
│ } × 24                                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Statistics Calculation (useMemo)                            │
│ Calculates:                                                  │
│   - minPrice = min(all low values)                          │
│   - maxPrice = max(all high values)                         │
│   - avgVolume = sum(volumes) / count                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Component Render                                            │
│ ├─ Header Section                                           │
│ │  ├─ Symbol & Timeframe                                    │
│ │  ├─ Current Price: $42,750.00                             │
│ │  └─ 24H Change: +0.50 (+0.12%)                            │
│ │                                                            │
│ ├─ Chart Section (ResponsiveContainer)                      │
│ │  └─ Recharts ComposedChart                               │
│ │     ├─ Grid background                                    │
│ │     ├─ 4 Line layers                                      │
│ │     ├─ 1 Bar layer                                        │
│ │     └─ Interactive tooltip                                │
│ │                                                            │
│ └─ Footer Section                                           │
│    ├─ 24H High: $42,850.50                                  │
│    ├─ 24H Low: $42,300.25                                   │
│    ├─ Avg Volume: 125.50M                                   │
│    └─ Data Points: 24                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ User Interaction (Mouse Hover)                              │
│ ├─ Hover over chart point                                   │
│ └─ Custom Tooltip Shows:                                    │
│    ├─ Symbol: BTCUSDT                                       │
│    ├─ Timestamp                                             │
│    ├─ OHLCV values with color coding                        │
│    └─ Volume in millions                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼ (After 60 seconds)
┌─────────────────────────────────────────────────────────────┐
│ Auto-Refetch (React Query)                                  │
│ Repeats API call automatically every 60 seconds            │
│ Updates chart with new data                                 │
│ Process repeats indefinitely...                            │
└─────────────────────────────────────────────────────────────┘
```

## Component Props Interface

```typescript
interface PriceChartProps {
  // Trading symbol (e.g., 'BTCUSDT', 'ETHUSDT')
  symbol: string = 'BTCUSDT'

  // Kline interval in minutes
  // Valid values: '1', '5', '15', '30', '60', '240', '1440'
  interval: string = '60'
}
```

## Hook Integration

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

## Chart Components Used (Recharts)

```
ComposedChart (Main container)
├── CartesianGrid (Background grid)
├── XAxis (Time labels at bottom)
│   ├── dataKey: 'time'
│   └── Rotated -45 degrees for readability
│
├── YAxis - Left (Price in USD)
│   ├── Label: 'Price (USD)'
│   └── Domain: [min-10, max+10]
│
├── YAxis - Right (Volume scale)
│   ├── Label: 'Volume'
│   └── Orientation: right
│
├── Tooltip (Custom)
│   └── Shows OHLCV on hover
│
├── Legend (Bottom)
│   └── Shows line/bar labels
│
├── Bar (Volume visualization)
│   ├── yAxisId: 'right'
│   ├── dataKey: 'volume'
│   ├── fill: '#d1d5db' (light gray)
│   └── fillOpacity: 0.3
│
└── Line × 4 (Price indicators)
    ├── Line 1: Close (Primary - Blue)
    │   ├── stroke: '#3b82f6'
    │   └── strokeWidth: 2.5
    │
    ├── Line 2: High (Light Purple)
    │   └── stroke: '#e0e7ff'
    │
    ├── Line 3: Low (Light Purple)
    │   └── stroke: '#e0e7ff'
    │
    └── Line 4: Open (Dashed Purple)
        ├── stroke: '#8b5cf6'
        └── strokeDasharray: '5 5'
```

## State Management Flow

```
┌─────────────────────┐
│   Component Mount   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐       ┌─────────────────────┐
│  isLoading = true   │──────▶│   Show Skeleton     │
│  error = null       │       │   Loader            │
│  data = undefined   │       └─────────────────────┘
└──────────┬──────────┘
           │
        (API Call)
           │
           ▼
    ┌──────────────┐
    │ API Response │
    └──────┬───────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
  Success     Error
     │           │
     ▼           ▼
┌────────────┐ ┌──────────────────┐
│Data Loaded │ │ error = new Error│
│isLoading   │ │ Show Error       │
│= false     │ │ Message          │
└────┬───────┘ └────────┬─────────┘
     │                  │
     ▼                  │
┌─────────────────┐    │
│ chartData       │    │
│ (useMemo)       │    │
└────┬────────────┘    │
     │                 │
     ▼                 ▼
┌──────────────────────────────┐
│    Render Chart OR Error     │
│    State                     │
└──────────────────────────────┘
     │
     └─── Auto-refetch after 60s
```

## Color Scheme

```
Primary Colors:
  - Close Price Line: #3b82f6 (Blue) - Tailwind blue-500
  - Open Price Line: #8b5cf6 (Purple) - Tailwind purple-500
  - High/Low Bands: #e0e7ff (Light Purple) - Tailwind indigo-100
  - Volume Bars: #d1d5db (Gray) - Tailwind gray-300

Text Colors:
  - Headers: #1f2937 (Dark Gray) - gray-900
  - Labels: #6b7280 (Medium Gray) - gray-500
  - Values: #1f2937 (Dark Gray) - gray-800

Positive/Negative:
  - Gains: #22c55e (Green) - green-500
  - Losses: #dc2626 (Red) - red-600

Background:
  - Cards: #ffffff (White)
  - Container: #f3f4f6 (Light Gray) - gray-100
```

## Responsive Breakpoints

```
Mobile (<768px):
├── 2 column grid for stats
├── Full-width chart (height: 400px)
└── Stacked layout

Tablet (768px-1024px):
├── 4 column grid for stats
├── Full-width chart (height: 400px)
└── Side-by-side layout

Desktop (>1024px):
├── 4 column grid for stats
├── Full-width chart (height: 400px)
└── Integrated dashboard layout
```

## Error Handling Strategy

```
Error Type 1: API Connection Error
├── Cause: Backend not running
├── Message: "Error Loading Price Chart"
└── Recovery: Show error and debugging info

Error Type 2: Invalid Data Format
├── Cause: API returns unexpected format
├── Handler: Graceful fallback in data transform
└── Recovery: Show empty state

Error Type 3: Empty Data
├── Cause: No kline data available yet
├── Message: "No price data available"
└── Recovery: Show placeholder until data arrives
```

## Performance Optimization

```
Optimizations Applied:
├── useMemo for data transformation
│   └── Prevents unnecessary recalculations
│
├── useMemo for statistics calculation
│   └── Only recalculates when chartData changes
│
├── isAnimationActive={false}
│   └── Disables chart animations for performance
│
├── React Query caching
│   └── Prevents duplicate API calls
│
└── Recharts optimization
    └── Efficient rendering of 24 data points
```

---

This structure provides complete clarity on how the component works and integrates with the rest of the application.
