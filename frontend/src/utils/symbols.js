/**
 * Symbol catalogues for UI display.
 *
 * IMPORTANT: This is *display-only* metadata for the ticker grid and chart
 * selector. The list of symbols actually being traded lives in the backend
 * (trading-engine/app/config.py: trading_symbols) — read it via the
 * /api/trading/status endpoint and the useTradingStatus hook. Don't infer
 * "what we trade" from this list.
 *
 * Per CLAUDE.md: this display list shows 11 symbols; the trading-engine
 * restricts position-taking to the 5 validated symbols (BTC/ETH/SOL/BNB/ADA).
 * Expanding this UI list does NOT expand what's traded.
 */

export const DISPLAY_SYMBOLS = [
  'BTCUSDT',   // Bitcoin - Most liquid
  'ETHUSDT',   // Ethereum - 2nd most liquid
  'SOLUSDT',   // Solana - Top performer
  'BNBUSDT',   // Binance Coin - Top performer
  'ADAUSDT',   // Cardano - Top performer
  'AVAXUSDT',  // Avalanche
  'LINKUSDT',  // Chainlink
  'DOTUSDT',   // Polkadot
  'MATICUSDT', // Polygon
  'ARBUSDT',   // Arbitrum - L2
  'OPUSDT',    // Optimism - L2
]

export const symbolDisplayName = (sym) => sym.replace(/USDT$/, '')
