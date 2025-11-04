# Crypto Trading Bot - Frontend Dashboard

Real-time React dashboard for monitoring and controlling the automated crypto trading bot.

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

Dashboard will be available at `http://localhost:3000`

## 📦 Project Structure

```
frontend/
├── package.json          # Dependencies & scripts
├── vite.config.js        # Vite configuration + API proxy
├── tailwind.config.js    # TailwindCSS styling
├── postcss.config.js     # PostCSS configuration
├── index.html            # HTML entry point
└── src/
    ├── main.jsx          # React entry point
    ├── App.jsx           # Main app component
    ├── index.css         # Global styles
    ├── components/       # UI components
    ├── services/         # API client
    ├── hooks/            # Custom React hooks
    └── utils/            # Helper functions
```

## 🎨 Features

### ✅ Implemented Configuration
- React 18 + Vite
- TailwindCSS for styling
- Axios for API calls
- React Query for data fetching
- Recharts for data visualization

### ⏳ To Implement
1. **Dashboard Layout** - Main container with sidebar navigation
2. **Portfolio Card** - Real-time balance and P&L display
3. **Price Tickers** - Live BTC/ETH/BNB prices
4. **Performance Chart** - Historical P&L visualization
5. **Trade History Table** - Recent trades with filters
6. **Emergency Stop Button** - Immediate trading halt
7. **Config Panel** - Adjust risk parameters

## 🔌 API Endpoints

All API calls are proxied through Vite to `http://localhost:8000/api`:

### Portfolio
- `GET /api/portfolio` - Current portfolio state
- `GET /api/portfolio/performance` - Performance metrics
- `POST /api/portfolio/buy` - Execute buy order
- `POST /api/portfolio/sell` - Execute sell order

### Market Data
- `GET /api/market/ticker/{symbol}` - Real-time price
- `GET /api/market/kline/{symbol}` - Historical candles

### Trading
- `GET /api/trading/signals/{symbol}` - Trading signal
- `POST /api/trading/execute` - Execute trade

## 🛠️ Development Guide

### Step 1: Install Dependencies

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/frontend
npm install
```

### Step 2: Create `index.html`

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Crypto Trading Bot Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

### Step 3: Create `src/index.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
  @apply bg-gray-50;
}
```

### Step 4: Create `src/main.jsx`

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 5000,
      staleTime: 3000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
```

### Step 5: Create `src/App.jsx`

```jsx
import React from 'react'
import Dashboard from './components/Dashboard'

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Dashboard />
    </div>
  )
}

export default App
```

### Step 6: Create API Service (`src/services/api.js`)

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

export const portfolioAPI = {
  getPortfolio: () => api.get('/portfolio'),
  getPerformance: () => api.get('/portfolio/performance'),
};

export const marketAPI = {
  getTicker: (symbol) => api.get(`/market/ticker/${symbol}`),
};

export const tradingAPI = {
  getSignal: (symbol, interval = 60) =>
    api.get(`/trading/signals/${symbol}`, { params: { interval } }),
};

export default api;
```

### Step 7: Create Custom Hooks

#### `src/hooks/usePortfolio.js`
```javascript
import { useQuery } from '@tanstack/react-query';
import { portfolioAPI } from '../services/api';

export const usePortfolio = () => {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: async () => {
      const response = await portfolioAPI.getPortfolio();
      return response.data.portfolio;
    },
    refetchInterval: 5000,
  });
};
```

#### `src/hooks/useTicker.js`
```javascript
import { useQuery } from '@tanstack/react-query';
import { marketAPI } from '../services/api';

export const useTicker = (symbol) => {
  return useQuery({
    queryKey: ['ticker', symbol],
    queryFn: async () => {
      const response = await marketAPI.getTicker(symbol);
      return response.data.ticker;
    },
    enabled: !!symbol,
    refetchInterval: 2000,
  });
};
```

### Step 8: Create Dashboard Component

#### `src/components/Dashboard.jsx`
```jsx
import React from 'react'
import { usePortfolio } from '../hooks/usePortfolio'
import PortfolioCard from './PortfolioCard'
import PriceTickerGrid from './PriceTickerGrid'
import PerformanceChart from './PerformanceChart'
import EmergencyStop from './EmergencyStop'

function Dashboard() {
  const { data: portfolio, isLoading } = usePortfolio()

  if (isLoading) {
    return <div className="p-8">Loading...</div>
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <h1 className="text-2xl font-bold text-gray-900">
            Crypto Trading Bot Dashboard
          </h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Portfolio Card */}
          <div className="lg:col-span-2">
            <PortfolioCard portfolio={portfolio} />
          </div>

          {/* Emergency Stop */}
          <div>
            <EmergencyStop />
          </div>

          {/* Price Tickers */}
          <div className="lg:col-span-3">
            <PriceTickerGrid />
          </div>

          {/* Performance Chart */}
          <div className="lg:col-span-3">
            <PerformanceChart />
          </div>
        </div>
      </main>
    </div>
  )
}

export default Dashboard
```

### Step 9: Create Portfolio Card Component

#### `src/components/PortfolioCard.jsx`
```jsx
import React from 'react'

function PortfolioCard({ portfolio }) {
  const { cash_balance, total_value, total_pnl, positions } = portfolio || {}

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Portfolio Overview
      </h2>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-sm text-gray-500">Cash Balance</p>
          <p className="text-2xl font-bold text-gray-900">
            ${cash_balance?.toFixed(2)}
          </p>
        </div>

        <div>
          <p className="text-sm text-gray-500">Total Value</p>
          <p className="text-2xl font-bold text-gray-900">
            ${total_value?.toFixed(2)}
          </p>
        </div>

        <div>
          <p className="text-sm text-gray-500">Total P&L</p>
          <p className={`text-2xl font-bold ${
            total_pnl >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            ${total_pnl?.toFixed(2)}
          </p>
        </div>

        <div>
          <p className="text-sm text-gray-500">Open Positions</p>
          <p className="text-2xl font-bold text-gray-900">
            {Object.keys(positions || {}).length}
          </p>
        </div>
      </div>
    </div>
  )
}

export default PortfolioCard
```

### Step 10: Create Price Ticker Grid

#### `src/components/PriceTickerGrid.jsx`
```jsx
import React from 'react'
import { useTicker } from '../hooks/useTicker'

function PriceTicker({ symbol }) {
  const { data: ticker } = useTicker(symbol)

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex justify-between items-center">
        <div>
          <p className="text-sm font-medium text-gray-500">{symbol}</p>
          <p className="text-2xl font-bold text-gray-900">
            ${parseFloat(ticker?.last_price || 0).toFixed(2)}
          </p>
        </div>
        <div className={`text-right ${
          parseFloat(ticker?.price_24h_pcnt || 0) >= 0
            ? 'text-green-600'
            : 'text-red-600'
        }`}>
          <p className="text-sm font-medium">24h Change</p>
          <p className="text-lg font-semibold">
            {(parseFloat(ticker?.price_24h_pcnt || 0) * 100).toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  )
}

function PriceTickerGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <PriceTicker symbol="BTCUSDT" />
      <PriceTicker symbol="ETHUSDT" />
      <PriceTicker symbol="BNBUSDT" />
    </div>
  )
}

export default PriceTickerGrid
```

### Step 11: Create Emergency Stop Button

#### `src/components/EmergencyStop.jsx`
```jsx
import React, { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

function EmergencyStop() {
  const [isConfirming, setIsConfirming] = useState(false)

  const handleStop = () => {
    if (!isConfirming) {
      setIsConfirming(true)
      return
    }

    // TODO: Call API to stop trading
    console.log('Emergency stop triggered!')
    setIsConfirming(false)
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center mb-4">
        <AlertTriangle className="w-5 h-5 text-red-600 mr-2" />
        <h2 className="text-lg font-semibold text-gray-900">
          Emergency Controls
        </h2>
      </div>

      <button
        onClick={handleStop}
        className={`w-full py-3 px-4 rounded-lg font-semibold text-white ${
          isConfirming
            ? 'bg-red-700 hover:bg-red-800'
            : 'bg-red-600 hover:bg-red-700'
        }`}
      >
        {isConfirming ? 'Click Again to Confirm' : 'STOP ALL TRADING'}
      </button>

      {isConfirming && (
        <button
          onClick={() => setIsConfirming(false)}
          className="w-full mt-2 py-2 px-4 rounded-lg font-medium text-gray-700 bg-gray-200 hover:bg-gray-300"
        >
          Cancel
        </button>
      )}
    </div>
  )
}

export default EmergencyStop
```

## 🏃 Running the Dashboard

### 1. Start Backend Services (if not running)

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# API Gateway must be running on port 8000
cd services/api-gateway && PYTHONPATH=. python3 -m uvicorn app.main:app --port 8000
```

### 2. Start Frontend Development Server

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/frontend
npm run dev
```

### 3. Access Dashboard

Open browser to `http://localhost:3000`

## 🔧 Environment Configuration

The Vite proxy automatically forwards `/api/*` requests to `http://localhost:8000/api/*`.

No additional environment variables required for development.

## 📝 Next Steps

To complete the dashboard, implement:

1. **Performance Chart** (`src/components/PerformanceChart.jsx`)
   - Use Recharts to visualize P&L over time
   - Fetch historical performance data

2. **Trade History Table** (`src/components/TradeHistory.jsx`)
   - Display recent trades
   - Add filtering and pagination

3. **Config Panel** (`src/components/ConfigPanel.jsx`)
   - Allow adjusting risk parameters
   - Max position size, stop loss, take profit

4. **Signal Indicators** (`src/components/SignalIndicators.jsx`)
   - Display current trading signals
   - RSI, MACD, Bollinger Bands values

5. **WebSocket Integration** (optional)
   - Real-time price updates without polling
   - Live trade notifications

## 🐛 Troubleshooting

### API Connection Issues
- Verify API Gateway is running: `curl http://localhost:8000/health`
- Check browser console for CORS errors
- Ensure Vite proxy is configured correctly in `vite.config.js`

### Build Errors
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Port Already in Use
```bash
# Change port in vite.config.js
server: {
  port: 3001,  // Use different port
}
```

## 📚 Additional Resources

- [React Documentation](https://react.dev)
- [Vite Guide](https://vitejs.dev/guide/)
- [TailwindCSS Docs](https://tailwindcss.com/docs)
- [React Query Docs](https://tanstack.com/query/latest)
- [Recharts Examples](https://recharts.org/en-US/examples)

---

**Status**: Configuration Complete, Components Need Implementation
**Last Updated**: 2025-10-31
