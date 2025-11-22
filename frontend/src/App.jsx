import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import Dashboard from './components/Dashboard'
import Phase1Dashboard from './pages/Phase1Dashboard'
import Phase3Dashboard from './pages/Phase3Dashboard'

/**
 * App component - Root component of the application
 * Provides routing between main dashboard, Phase 1 monitoring, and Phase 3 AI dashboard
 */
function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
        {/* Navigation */}
        <nav className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex">
                <div className="flex-shrink-0 flex items-center">
                  <h1 className="text-xl font-bold text-gray-900">🤖 Trading Bot</h1>
                </div>
                <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                  <Link
                    to="/"
                    className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                  >
                    Main Dashboard
                  </Link>
                  <Link
                    to="/phase1"
                    className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                  >
                    Phase 1 Monitoring
                  </Link>
                  <Link
                    to="/phase3"
                    className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                  >
                    🤖 Phase 3: AI Enhanced
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </nav>

        {/* Routes */}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/phase1" element={<Phase1Dashboard />} />
          <Route path="/phase3" element={<Phase3Dashboard />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
