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
})
