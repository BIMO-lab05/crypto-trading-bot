import React, { useState } from 'react'
import { useEmergencyStop } from '../hooks/usePortfolio'

/**
 * EmergencyStop component provides critical trading halt functionality
 * Allows user to immediately stop all trading operations
 */
export default function EmergencyStop() {
  const [showConfirm, setShowConfirm] = useState(false)
  const emergencyStop = useEmergencyStop()

  const handleEmergencyStop = async () => {
    try {
      await emergencyStop.mutateAsync()
      alert('Emergency stop activated! All trading halted.')
      setShowConfirm(false)
    } catch (error) {
      alert(`Failed to activate emergency stop: ${error.message}`)
    }
  }

  if (showConfirm) {
    return (
      <div className="bg-rose-500/10 border-2 border-rose-500/50 backdrop-blur-sm rounded-lg p-6">
        <div className="text-center">
          <div className="mb-4">
            <svg
              className="mx-auto h-12 w-12 text-rose-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>

          <h3 className="text-xl font-bold text-rose-300 mb-2">
            Confirm Emergency Stop
          </h3>

          <p className="text-rose-200 mb-6">
            This will immediately halt all trading operations. Open positions will remain, but no new trades will be executed. Are you sure you want to continue?
          </p>

          <div className="flex gap-3 justify-center">
            <button
              onClick={() => setShowConfirm(false)}
              className="px-6 py-2 bg-slate-700 text-slate-100 rounded-lg font-semibold hover:bg-slate-600 transition-colors"
              disabled={emergencyStop.isPending}
            >
              Cancel
            </button>

            <button
              onClick={handleEmergencyStop}
              disabled={emergencyStop.isPending}
              className="px-6 py-2 bg-rose-600 text-white rounded-lg font-semibold hover:bg-rose-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {emergencyStop.isPending ? 'Stopping...' : 'Confirm Stop'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/50 rounded-lg border-2 border-rose-500/30 backdrop-blur-sm p-6">
      <div className="flex items-start space-x-4">
        <div className="flex-shrink-0">
          <svg
            className="h-8 w-8 text-rose-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>

        <div className="flex-grow">
          <h3 className="text-lg font-bold text-slate-100 mb-2">
            Emergency Stop
          </h3>

          <p className="text-slate-300 mb-4 text-sm">
            Use this button to immediately halt all trading operations. This is a safety feature for unexpected market conditions or system issues.
          </p>

          <button
            onClick={() => setShowConfirm(true)}
            className="w-full md:w-auto px-6 py-3 bg-rose-600 text-white rounded-lg font-bold hover:bg-rose-700 active:bg-rose-800 transition-colors shadow-md hover:shadow-lg transform hover:scale-105"
          >
            <div className="flex items-center justify-center space-x-2">
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"
                />
              </svg>
              <span>EMERGENCY STOP</span>
            </div>
          </button>
        </div>
      </div>

      <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 backdrop-blur-sm rounded-md">
        <p className="text-xs text-amber-300">
          <strong>Note:</strong> This will stop the trading bot from executing new trades. Existing open positions will not be automatically closed.
        </p>
      </div>
    </div>
  )
}
