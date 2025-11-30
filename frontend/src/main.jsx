/**
 * main.jsx - Application Entry Point
 *
 * Purpose: Bootstrap the React application with all necessary providers
 * including React Query for data fetching and ThemeProvider for dark mode.
 *
 * Provider Hierarchy:
 * 1. React.StrictMode - Development mode checks
 * 2. ThemeProvider - Dark/Light mode theming
 * 3. QueryClientProvider - React Query data management
 * 4. App - Main application component
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Theme Provider for dark mode support
import { ThemeProvider } from './contexts/ThemeContext'

// Main application component
import App from './App'

// Global styles with Tailwind CSS
import './index.css'

// ============================================================================
// REACT QUERY CONFIGURATION
// ============================================================================

/**
 * React Query Client Configuration
 *
 * UPDATED 2025-11-30: Fixed aggressive polling causing timeouts
 * - Removed global refetchInterval (each hook controls its own)
 * - Increased staleTime to reduce unnecessary refetches
 * - Disabled refetchOnWindowFocus to prevent request spikes
 *
 * Individual hooks now control their own refresh intervals:
 * - usePositions: 10s
 * - usePerformance: 10s
 * - useTradingStatus: 15s
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // NO global refetchInterval - each hook sets its own
      // This prevents queries without explicit intervals from auto-refreshing

      // Don't refetch on window focus (prevents request spikes when switching tabs)
      refetchOnWindowFocus: false,

      // Data considered stale after 10 seconds
      staleTime: 10000,

      // Two retries on failure with delay
      retry: 2,
      retryDelay: 1000,

      // Don't refetch on mount if data is fresh
      refetchOnMount: true,

      // Note: keepPreviousData was deprecated in v5, use placeholderData instead
      // placeholderData is set per-query now, not globally
    },
    mutations: {
      // Retry mutations once on failure
      retry: 1,
    },
  },
})

// ============================================================================
// APPLICATION RENDER
// ============================================================================

/**
 * Mount the React application to the DOM
 *
 * The application is wrapped with:
 * 1. StrictMode - Enables development warnings and checks
 * 2. ThemeProvider - Provides dark mode context (defaults to dark)
 * 3. QueryClientProvider - Provides React Query data management
 */
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* Theme Provider - Dark mode by default */}
    <ThemeProvider defaultTheme="dark">
      {/* React Query Provider - Data fetching and caching */}
      <QueryClientProvider client={queryClient}>
        {/* Main Application */}
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>,
)
