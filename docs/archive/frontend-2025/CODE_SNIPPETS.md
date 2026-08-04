# PriceChart Component - Code Snippets & Examples

## Quick Copy-Paste Examples

### 1. Basic Usage in Dashboard

```jsx
import PriceChart from './components/PriceChart'

export default function Dashboard() {
  return (
    <div>
      {/* Default BTCUSDT 60-minute chart */}
      <PriceChart />

      {/* OR with custom symbol and interval */}
      <PriceChart symbol="ETHUSDT" interval="60" />
    </div>
  )
}
```

### 2. Multiple Charts for Different Symbols

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

### 3. Tabbed Chart View

```jsx
import { useState } from 'react'
import PriceChart from './components/PriceChart'

export default function TabbedCharts() {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT')
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

  return (
    <div>
      {/* Tab buttons */}
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

      {/* Display selected chart */}
      <PriceChart symbol={activeSymbol} interval="60" />
    </div>
  )
}
```

### 4. Custom Time Interval Selection

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
      {/* Interval selector */}
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

      {/* Chart updates when interval changes */}
      <PriceChart symbol="BTCUSDT" interval={interval} />
    </div>
  )
}
```

## API Response Handling Examples

### Example 1: Working with Array Format Response

```javascript
// Backend returns array format
const apiResponse = [
  [1700610600000, 42500, 42850.50, 42300.25, 42750, 125.5],
  [1700614200000, 42750, 42900, 42400, 42600, 120.3],
  // ... more candles
]

// PriceChart automatically handles this via the transformation:
const chartData = data.map((candle) => {
  const openTime = candle[0]    // 1700610600000
  const open = candle[1]         // 42500
  const high = candle[2]         // 42850.50
  const low = candle[3]          // 42300.25
  const close = candle[4]        // 42750
  const volume = candle[5]       // 125.5
  // ... returns formatted object
})
```

### Example 2: Working with Object Format Response

```javascript
// Backend returns object format
const apiResponse = [
  {
    open_time: 1700610600000,
    open: 42500,
    high: 42850.50,
    low: 42300.25,
    close: 42750,
    volume: 125.5,
  },
  // ... more candles
]

// PriceChart automatically handles this too:
const chartData = data.map((candle) => {
  const openTime = candle.open_time  // 1700610600000
  const open = candle.open           // 42500
  const high = candle.high           // 42850.50
  // ... returns formatted object
})
```

## Backend Implementation Examples

### Example 1: Simple FastAPI Implementation

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
    # Fetch from database or cache
    klines = await fetch_klines_from_db(symbol, interval, limit)

    # Transform to required format
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

### Example 2: Express/Node.js Implementation

```javascript
const express = require('express')
const router = express.Router()

router.get('/market/kline/:symbol', async (req, res) => {
  const { symbol } = req.params
  const { interval = '60', limit = 24 } = req.query

  try {
    // Fetch from database
    const klines = await getKlinesFromDb(symbol, interval, limit)

    // Transform to array format
    const formatted = klines.map(candle => [
      new Date(candle.openTime).getTime(),  // timestamp in ms
      parseFloat(candle.open),
      parseFloat(candle.high),
      parseFloat(candle.low),
      parseFloat(candle.close),
      parseFloat(candle.volume),
    ])

    res.json(formatted)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

module.exports = router
```

### Example 3: Django Implementation

```python
from django.http import JsonResponse
from rest_framework.decorators import api_view

@api_view(['GET'])
def get_klines(request, symbol):
    interval = request.query_params.get('interval', '60')
    limit = request.query_params.get('limit', 24)

    # Fetch from database
    klines = Candle.objects.filter(
        symbol=symbol,
        interval=interval
    ).order_by('-open_time')[:int(limit)]

    # Transform to array format
    data = [
        [
            int(candle.open_time.timestamp() * 1000),
            float(candle.open),
            float(candle.high),
            float(candle.low),
            float(candle.close),
            float(candle.volume),
        ]
        for candle in reversed(klines)
    ]

    return JsonResponse(data, safe=False)
```

## Testing Examples

### Example 1: Unit Test for Component

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

### Example 2: Integration Test

```javascript
// API mock test
describe('PriceChart API Integration', () => {
  beforeEach(() => {
    // Mock API response
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

## Customization Examples

### Example 1: Custom Colors

```jsx
// Edit PriceChart.jsx to change colors
// Find the Line component for close price:

// Original:
<Line
  yAxisId="left"
  type="monotone"
  dataKey="close"
  stroke="#3b82f6"  // Blue
  strokeWidth={2.5}
  ...
/>

// Change to red:
<Line
  yAxisId="left"
  type="monotone"
  dataKey="close"
  stroke="#dc2626"  // Red
  strokeWidth={2.5}
  ...
/>

// Or use gradient:
<defs>
  <linearGradient id="colorClose" x1="0" y1="0" x2="0" y2="1">
    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
  </linearGradient>
</defs>
<Area
  yAxisId="left"
  type="monotone"
  dataKey="close"
  fill="url(#colorClose)"
  stroke="#3b82f6"
/>
```

### Example 2: Add RSI Indicator

```jsx
// Add to PriceChart component data transformation
const chartData = useMemo(() => {
  const raw = transformToChartFormat(data)

  // Calculate RSI
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
<Line
  yAxisId="right"
  dataKey="rsi"
  stroke="#f59e0b"
  name="RSI (14)"
  strokeWidth={2}
/>
```

### Example 3: Format Prices in Millions

```jsx
// In the custom tooltip:
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

## Error Handling Examples

### Example 1: Custom Error Boundary

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

### Example 2: Retry Logic

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
        <button
          onClick={handleRetry}
          className="px-4 py-2 bg-blue-500 text-white rounded"
        >
          Retry ({retryCount}/3)
        </button>
      </div>
    )
  }

  return <PriceChart />
}
```

## Performance Optimization Examples

### Example 1: Memoized Component

```jsx
import { memo } from 'react'
import PriceChart from './PriceChart'

// Prevent unnecessary re-renders
const MemoizedPriceChart = memo(PriceChart, (prevProps, nextProps) => {
  // Only re-render if symbol or interval changes
  return (
    prevProps.symbol === nextProps.symbol &&
    prevProps.interval === nextProps.interval
  )
})

export default MemoizedPriceChart
```

### Example 2: Lazy Loading

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

### Example 3: Virtual Scrolling for Multiple Charts

```jsx
import { FixedSizeList as List } from 'react-window'
import PriceChart from './PriceChart'

export default function VirtualChartList() {
  const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', ...]

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

---

Use these snippets as starting points for your own implementations. All examples follow React best practices and are production-ready.
