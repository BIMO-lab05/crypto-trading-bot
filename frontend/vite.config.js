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
      // Direct proxy to trading-engine signals (port 8005)
      '/api/trading/signals': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading\/signals/, '/api/v1/signals'),
      },
      // Direct proxy to trading-engine (port 8005)
      '/api/trading': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        timeout: 10000,
        rewrite: (path) => path.replace(/^\/api\/trading/, '/api/v1'),
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
    // Add hash to output files for cache busting
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
  // Optimize dependency pre-bundling
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query', 'zustand'],
  },
})
