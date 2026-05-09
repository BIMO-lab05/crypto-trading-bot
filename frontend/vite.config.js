/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Vite Configuration for Crypto Trading Dashboard
 *
 * Features:
 * - React plugin for JSX/TSX support
 * - API proxy for backend gateway
 * - Cache control headers to prevent stale data issues
 * - Proper CORS and HMR configuration
 *
 * Fixed 2025-11-29: Added cache control to fix normal browsing mode issues
 *
 * --- DEV vs PROD ROUTING (read this before "fixing" the URL mismatch) ---
 *
 * In **production** (`frontend/nginx.conf`), nginx proxies `/api/`
 * unchanged to the api-gateway: `/api/<domain>/<resource>` →
 * `crypto-bot-api-gateway:8000/api/<domain>/<resource>`. The gateway
 * routes are `/api/<domain>/<resource>` (NO `v1` prefix — see CLAUDE.md
 * "Project rules"). One ingress, gateway middleware (auth, rate limit,
 * input validation, security headers) applies to everything.
 *
 * In **development** below, the proxy block instead **bypasses the
 * gateway** and rewrites `/api/<domain>/...` directly to the
 * individual service on its host port with a `/api/v1/<resource>`
 * shape (e.g. `/api/portfolio/...` → port 8003 with rewrite to
 * `/api/v1/portfolio/...`). That's a deliberate dev-only shortcut so
 * the gateway doesn't have to be running for the UI to work, but it
 * means **gateway middleware does not execute in dev** — auth checks,
 * rate limits, and the validation pipeline are silently skipped.
 *
 * The audit flagged this as a "dev/prod URL mismatch". It's not a
 * routing bug — both forms reach a working backend — but it is a
 * dev/prod parity issue: features added to gateway middleware (e.g.
 * the admin-auth requirement on /api/portfolio/emergency-stop) only
 * exercise in prod. Test gateway-mediated paths against a running
 * gateway (`docker compose up api-gateway` and proxy `/api` →
 * `localhost:8000`) before declaring a feature done.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    // Add cache control headers to prevent stale cached files
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    proxy: {
      // Direct proxy to market-data service (port 8002)
      '/api/market': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/market/, '/api/v1'),
      },
      // Trading signals (port 8005)
      '/api/trading/signals': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading\/signals/, '/api/v1/signals'),
      },
      // Trading positions - maps to /api/v1/positions (port 8005)
      '/api/trading/positions': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading\/positions/, '/api/v1/positions'),
      },
      // Trading performance - maps to /api/v1/performance (port 8005)
      '/api/trading/performance': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading\/performance/, '/api/v1/performance'),
      },
      // Trading trades history - maps to /api/v1/trades/history (port 8005)
      '/api/trading/trades': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading\/trades/, '/api/v1/trades'),
      },
      // Phase 1 metrics and monitoring - maps to /api/v1/phase1/* (port 8005)
      '/api/trading/phase1': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading\/phase1/, '/api/v1/phase1'),
      },
      // Trading status/start/stop - maps to /api/v1/trading/* (port 8005)
      '/api/trading': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading/, '/api/v1/trading'),
      },
      // Portfolio manager health (port 8003)
      '/api/portfolio/health': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        secure: false,
        timeout: 5000,
        rewrite: (path) => '/health',
      },
      // Portfolio manager (port 8003)
      '/api/portfolio': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/portfolio/, '/api/v1/portfolio'),
      },
      // ML prediction (port 8007)
      '/api/ml': {
        target: 'http://localhost:8007',
        changeOrigin: true,
        secure: false,
        timeout: 15000,
        rewrite: (path) => path.replace(/^\/api\/ml/, '/api/v1'),
      },
      // Sentiment analysis (port 8008)
      '/api/sentiment': {
        target: 'http://localhost:8008',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/sentiment/, '/api/v1'),
      },
      // Analysis endpoints to technical-analysis
      '/api/analysis': {
        target: 'http://localhost:8004',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/analysis/, '/api/v1'),
      },
      // Health endpoint - API gateway
      '/api/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        timeout: 5000,
      },
      // Fallback to API gateway
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        proxyTimeout: 10000,
      }
    },
    // Watch for file changes
    watch: {
      usePolling: true,
      interval: 1000,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Code splitting for smaller initial bundle (2025-12-01)
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        // Manual chunks for better code splitting
        manualChunks: {
          // React core - rarely changes
          'react-vendor': ['react', 'react-dom'],
          // Router - separate chunk
          'router': ['react-router-dom'],
          // Data fetching
          'query': ['@tanstack/react-query', 'axios'],
          // Charts - large, lazy loaded
          'charts': ['recharts'],
          // UI utilities
          'ui': ['lucide-react', 'date-fns'],
          // State management
          'state': ['zustand'],
        },
      },
    },
    // Increase chunk size warning limit
    chunkSizeWarningLimit: 500,
  },
  // Optimize dependency pre-bundling
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query', 'zustand'],
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.js'],
    css: false,
    exclude: ['node_modules', 'dist', '.idea', '.git'],
  },
})
