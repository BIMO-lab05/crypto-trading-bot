import React from 'react'

export default function Test() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center p-8">
      <div className="bg-white rounded-2xl shadow-2xl p-12 max-w-2xl">
        <h1 className="text-5xl font-bold text-gray-800 mb-6">
          🎉 Frontend is Working!
        </h1>

        <div className="space-y-4">
          <div className="bg-green-100 border-l-4 border-green-500 p-4 rounded">
            <p className="text-green-800 font-semibold">✅ React is rendering correctly</p>
          </div>

          <div className="bg-blue-100 border-l-4 border-blue-500 p-4 rounded">
            <p className="text-blue-800 font-semibold">✅ TailwindCSS is working</p>
          </div>

          <div className="bg-purple-100 border-l-4 border-purple-500 p-4 rounded">
            <p className="text-purple-800 font-semibold">✅ Vite dev server is running</p>
          </div>

          <div className="mt-8 p-6 bg-gray-50 rounded-lg">
            <p className="text-gray-700 mb-4">
              <strong>If you can see this page with colors and styling,</strong> your frontend is working perfectly!
            </p>
            <p className="text-gray-600 text-sm">
              The issue was likely a browser cache problem. Press <strong>Ctrl+Shift+R</strong> (or <strong>Cmd+Shift+R</strong> on Mac) to hard refresh.
            </p>
          </div>

          <button
            onClick={() => window.location.href = '/'}
            className="w-full mt-6 px-6 py-4 bg-gradient-to-r from-green-500 to-blue-500 text-white font-bold rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105"
          >
            Go to Dashboard →
          </button>
        </div>
      </div>
    </div>
  )
}
