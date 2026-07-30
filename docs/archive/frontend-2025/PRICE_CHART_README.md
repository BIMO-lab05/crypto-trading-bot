# Price Chart Component - Quick Reference

## What Was Added

A professional price chart component that displays 24-hour cryptocurrency price history with interactive visualization.

## Files

| File | Type | Purpose |
|------|------|---------|
| `src/components/PriceChart.jsx` | New Component | Main price chart with recharts |
| `src/components/Dashboard.jsx` | Modified | Added PriceChart to dashboard layout |

## Quick Start

### View the Chart
```bash
npm run dev
# Open http://localhost:5173
# Chart appears under "Price Tickers" section
```

### Customize Symbol
Edit Dashboard.jsx:
```jsx
// Change from BTCUSDT to another symbol
<PriceChart symbol="ETHUSDT" interval="60" />
```

### Customize Timeframe
```jsx
// 5-minute candles
<PriceChart symbol="BTCUSDT" interval="5" />

// 4-hour candles
<PriceChart symbol="BTCUSDT" interval="240" />
```

## Component Features

- **Interactive Chart**: Hover to see price details
- **Multiple Indicators**: Open, High, Low, Close prices
- **Volume Visualization**: Bar chart overlay
- **Statistics**: 24H High/Low, Average Volume
- **Loading State**: Skeleton loader while fetching
- **Error Handling**: User-friendly error messages
- **Real-time Updates**: Refreshes every minute

## API Integration

**Endpoint Used:**
```
GET /api/market/kline/{symbol}
Query Params:
  - interval: "60" (minutes)
  - limit: 24 (number of candles)
```

**Expected Data Format:**
```javascript
[
  [openTime, open, high, low, close, volume],
  // ... more candles
]
```

## Component Props

```jsx
<PriceChart
  symbol="BTCUSDT"  // Trading pair (default: BTCUSDT)
  interval="60"     // Candle size in minutes (default: 60)
/>
```

## Key Components Inside

1. **Data Fetching**: useKlines hook with React Query
2. **Data Transform**: useMemo for chart data formatting
3. **Chart**: Recharts ComposedChart with multiple lines and bars
4. **Styling**: Tailwind CSS for UI elements

## Customization Examples

### Change Chart Colors
In PriceChart.jsx, find line definitions:
```jsx
// Close price line - change stroke color
<Line dataKey="close" stroke="#3b82f6" ... />
// Change to: stroke="#ff0000" for red
```

### Show Different Number of Hours
In Dashboard.jsx:
```jsx
// Change limit from 24 to show more/fewer candles
const { data, isLoading, error } = useKlines(symbol, interval, { limit: 48 })
```

### Adjust Refresh Rate
In PriceChart.jsx, find useKlines call and modify refetchInterval:
```jsx
// Change from 60000ms (1 minute) to 30000ms (30 seconds)
refetchInterval: 30000
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Chart is blank | Check backend API is running on port 8000 |
| "No data" message | Ensure `/api/market/kline/BTCUSDT` endpoint exists |
| Chart doesn't update | Check browser console for API errors |
| Tooltip doesn't appear | Try moving mouse over chart area |

## Chart Breakdown

### Top Section
- **Symbol & Timeframe**: BTCUSDT, Last 24 hours
- **Current Price**: Real-time price display
- **24H Change**: Price change in dollars and percentage

### Main Chart
- **Blue Line**: Closing price (main trend)
- **Purple Dashed Line**: Opening price
- **Light Purple Bands**: High/Low price range
- **Gray Bars**: Trading volume (background)
- **Grid**: Reference lines for easy reading

### Bottom Section
- **24H High**: Highest price in period
- **24H Low**: Lowest price in period
- **Avg Volume**: Average trading volume
- **Data Points**: Number of candles shown

## Backend Requirements

The backend API must provide:

```python
# Example endpoint structure
GET /api/market/kline/BTCUSDT?interval=60&limit=24
Response: [
    [timestamp, open, high, low, close, volume],
    ...
]
```

See `PRICE_CHART_INTEGRATION.md` for full documentation.

## Performance Notes

- Component uses React Query for efficient caching
- Updates every 60 seconds by default
- Animations disabled for better performance
- Recharts handles rendering optimization

## Browser Support

- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support (14+)

## Next Steps

1. **Test with real data**: Run backend with market data service
2. **Add more symbols**: Create tabs for ETHUSDT, BNBUSDT, etc.
3. **Add indicators**: RSI, MACD, Bollinger Bands
4. **Enable WebSocket**: Replace polling with real-time updates
5. **Add time picker**: Allow custom date ranges

## Files Reference

Full documentation: `../PRICE_CHART_INTEGRATION.md`

Component source: `src/components/PriceChart.jsx` (280 lines, fully commented)

Dashboard integration: `src/components/Dashboard.jsx` (lines 1-100)

---

Questions? Check the full documentation or review the commented code in PriceChart.jsx.
