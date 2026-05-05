/**
 * App.jsx - Root Application Component
 *
 * Purpose: Main application component providing routing and layout structure
 * for the crypto trading bot dashboard with full dark mode support.
 *
 * Features:
 * - React Router navigation
 * - Dark mode themed navigation
 * - Theme toggle button in header
 * - Responsive layout
 * - Multiple dashboard views
 *
 * Routes:
 * - / - Main Dashboard
 * - /phase1 - Phase 1 Monitoring
 * - /phase3 - Phase 3 AI Enhanced Dashboard
 * - /performance - Performance Analytics Dashboard (Phase 5.3)
 * - /settings - Application Settings
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 * Updated: 2025-12-11 - Added Performance Analytics route
 */

import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'

// Import dashboard components
import Dashboard from './components/Dashboard'
import Phase1Dashboard from './pages/Phase1Dashboard'
import Phase3Dashboard from './pages/Phase3Dashboard'
import PerformanceDashboard from './pages/PerformanceDashboard'
import Portfolio from './pages/Portfolio'
import Settings from './pages/Settings'

// Import theme toggle component
import ThemeToggle from './components/ThemeToggle'

// Editorial command surface + live status bar + toast center
import CommandPalette from './components/CommandPalette'
import StatusBar from './components/StatusBar'
import KeyboardShortcuts from './components/KeyboardShortcuts'
import { ToastProvider } from './contexts/ToastContext'

// ============================================================================
// NAVIGATION LINK COMPONENT
// ============================================================================

/**
 * NavLink - Active-aware navigation link
 *
 * Highlights the current route and provides proper dark mode styling
 *
 * @param to - Route path
 * @param children - Link content
 */
const NavLink = ({ to, children }) => {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <Link
      to={to}
      aria-current={isActive ? 'page' : undefined}
      className={`
        inline-flex items-center px-1 pt-1 text-sm font-medium
        border-b-2 transition-colors duration-200

        ${isActive
          ? /* Active state */
            'border-blue-500 text-blue-600 dark:text-blue-400'
          : /* Inactive state */
            'border-transparent text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600 hover:text-slate-700 dark:hover:text-slate-300'
        }
      `}
    >
      {children}
    </Link>
  )
}

// ============================================================================
// MOBILE MENU COMPONENT
// ============================================================================

/**
 * MobileMenu - Responsive mobile navigation menu
 *
 * Provides a dropdown menu for mobile devices with proper dark mode styling
 */
const MobileMenu = ({ isOpen, onClose }) => {
  const location = useLocation()
  const firstLinkRef = React.useRef(null)

  React.useEffect(() => {
    if (!isOpen) return undefined
    const handleKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKey)
    if (firstLinkRef.current) firstLinkRef.current.focus()
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const navItems = [
    { to: '/', label: 'Main Dashboard' },
    { to: '/phase1', label: 'Phase 1 Monitoring' },
    { to: '/phase3', label: 'Phase 3: AI Enhanced' },
    { to: '/portfolio', label: 'Portfolio' },
    { to: '/performance', label: 'Performance' },
    { to: '/settings', label: 'Settings' },
  ]

  return (
    <div className="sm:hidden" id="mobile-menu">
      <div className="pt-2 pb-3 space-y-1 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700">
        {navItems.map((item, idx) => {
          const isActive = location.pathname === item.to
          return (
            <Link
              key={item.to}
              to={item.to}
              ref={idx === 0 ? firstLinkRef : undefined}
              onClick={onClose}
              aria-current={isActive ? 'page' : undefined}
              className={`
                block pl-3 pr-4 py-2 text-base font-medium
                border-l-4 transition-colors duration-200

                ${isActive
                  ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 text-blue-700 dark:text-blue-400'
                  : 'border-transparent text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                }
              `}
            >
              {item.label}
            </Link>
          )
        })}
      </div>
    </div>
  )
}

// ============================================================================
// HEADER COMPONENT
// ============================================================================

/**
 * Header - Main navigation header with theme toggle
 *
 * Features:
 * - Brand logo and title
 * - Desktop navigation links
 * - Theme toggle button
 * - Mobile menu toggle
 */
const Header = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false)

  return (
    <header className="sticky top-0 z-50 bg-white dark:bg-slate-800 shadow-sm dark:shadow-slate-900/50 border-b border-slate-200 dark:border-slate-700 transition-colors duration-200">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          {/* Left side - Logo and navigation */}
          <div className="flex">
            {/* Brand logo and title */}
            <div className="flex-shrink-0 flex items-center">
              <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 transition-colors duration-200">
                <span className="mr-2">Trading Bot</span>
              </h1>
            </div>

            {/* Desktop navigation links */}
            <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
              <NavLink to="/">
                Main Dashboard
              </NavLink>
              <NavLink to="/phase1">
                Phase 1 Monitoring
              </NavLink>
              <NavLink to="/phase3">
                Phase 3: AI Enhanced
              </NavLink>
              <NavLink to="/portfolio">
                Portfolio
              </NavLink>
              <NavLink to="/performance">
                Performance
              </NavLink>
              <NavLink to="/settings">
                Settings
              </NavLink>
            </div>
          </div>

          {/* Right side - Theme toggle and mobile menu button */}
          <div className="flex items-center space-x-4">
            {/* Theme Toggle Button */}
            <ThemeToggle size="md" />

            {/* Mobile menu button */}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="sm:hidden inline-flex items-center justify-center p-2 rounded-md text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors duration-200"
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-menu"
              aria-label="Toggle navigation menu"
            >
              {/* Hamburger icon */}
              <svg
                className={`${mobileMenuOpen ? 'hidden' : 'block'} h-6 w-6`}
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>

              {/* Close icon */}
              <svg
                className={`${mobileMenuOpen ? 'block' : 'hidden'} h-6 w-6`}
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile navigation menu */}
      <MobileMenu isOpen={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />
    </header>
  )
}

// ============================================================================
// MAIN APP COMPONENT
// ============================================================================

/**
 * App - Root component of the application
 *
 * Provides:
 * - Router configuration for navigation
 * - Dark mode themed layout
 * - Navigation header
 * - Route definitions
 *
 * @returns JSX element containing the complete application
 */
function App() {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ToastProvider>
      {/* Main application container with dark mode support */}
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
        {/* Skip to main content link (visible on focus) */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-md focus:bg-blue-700 focus:text-white focus:font-medium focus:shadow-lg"
        >
          Skip to main content
        </a>

        {/* Navigation Header */}
        <Header />

        {/* Main Content Area */}
        <main id="main-content" tabIndex={-1} className="transition-colors duration-200">
          {/* Route Definitions */}
          <Routes>
            {/* Main Dashboard - Home route */}
            <Route path="/" element={<Dashboard />} />

            {/* Phase 1 Monitoring Dashboard */}
            <Route path="/phase1" element={<Phase1Dashboard />} />

            {/* Phase 3 AI Enhanced Dashboard */}
            <Route path="/phase3" element={<Phase3Dashboard />} />

            {/* Phase 5.3: Performance Analytics Dashboard */}
            <Route path="/performance" element={<PerformanceDashboard />} />

            {/* Portfolio overview */}
            <Route path="/portfolio" element={<Portfolio />} />

            {/* Settings Page */}
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>

        {/* Footer — sits above the fixed StatusBar */}
        <footer className="bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 transition-colors duration-200" style={{ paddingBottom: 38 }}>
          <div className="max-w-7xl mx-auto py-4 px-4 sm:px-6 lg:px-8">
            <p className="text-center text-sm text-slate-500 dark:text-slate-400">
              Crypto Trading Bot Dashboard - Real-time monitoring and analysis
            </p>
          </div>
        </footer>

        {/* Editorial command palette (⌘K) and live status bar */}
        <CommandPalette />
        <StatusBar />
        <KeyboardShortcuts />
      </div>
      </ToastProvider>
    </Router>
  )
}

export default App
