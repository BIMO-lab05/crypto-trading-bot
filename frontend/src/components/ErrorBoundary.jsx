/**
 * ErrorBoundary.jsx - Top-Level Error Boundary
 *
 * Purpose: Catch render-time errors anywhere in the component tree so a
 * single throwing component degrades to a fallback screen instead of
 * blanking the whole app.
 *
 * Features:
 * - Class component (error boundaries require class lifecycle methods)
 * - componentDidCatch logs the error + component stack to the console
 * - Fallback UI matching the app's dark mode styling with a reload button
 *
 * Author: Frontend Developer Agent
 * Date: 2026-08-20
 */

import React from 'react'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    // Switch to the fallback UI on the next render
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    // Log for diagnosis — there is no remote error reporting in this app
    console.error('[ErrorBoundary] Render error caught:', error, errorInfo?.componentStack)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 transition-colors duration-200 px-4">
          <div className="max-w-md w-full text-center bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-sm dark:shadow-slate-900/50 p-8">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">
              Something went wrong
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
              The dashboard hit an unexpected error and could not render.
              Reloading usually fixes it.
            </p>
            <button
              type="button"
              onClick={this.handleReload}
              className="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors duration-200"
            >
              Reload page
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
