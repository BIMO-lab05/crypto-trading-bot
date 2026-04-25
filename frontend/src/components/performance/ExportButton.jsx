/**
 * ExportButton.jsx - Export Button with Dropdown Component
 *
 * Purpose: Compact export button for the dashboard toolbar that triggers
 * the export modal or provides quick export options.
 *
 * Features:
 * - Dropdown menu with export format options
 * - Quick export to CSV/PDF
 * - Opens detailed export modal
 * - Loading state during export
 * - Keyboard accessible
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState, useRef, useEffect } from 'react'
import PropTypes from 'prop-types'

// ============================================================================
// ICONS
// ============================================================================

const DownloadIcon = ({ className = '' }) => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
    />
  </svg>
)

const CsvIcon = ({ className = '' }) => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
    />
  </svg>
)

const PdfIcon = ({ className = '' }) => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
    />
  </svg>
)

const ChevronDownIcon = ({ className = '' }) => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 9l-7 7-7-7"
    />
  </svg>
)

const SettingsIcon = ({ className = '' }) => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
    />
  </svg>
)

const LoadingSpinner = ({ className = '' }) => (
  <svg
    className={`animate-spin ${className}`}
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
)

// ============================================================================
// DROPDOWN MENU ITEM
// ============================================================================

const MenuItem = ({ icon: Icon, label, description, onClick, disabled }) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors ${
      disabled
        ? 'opacity-50 cursor-not-allowed'
        : 'hover:bg-slate-700/50'
    }`}
  >
    <Icon className="w-5 h-5 text-slate-400 mt-0.5" />
    <div className="flex-1">
      <p className="text-sm font-medium text-slate-200">{label}</p>
      {description && (
        <p className="text-xs text-slate-500 mt-0.5">{description}</p>
      )}
    </div>
  </button>
)

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * ExportButton - Export Button with Dropdown
 *
 * @param {Object} props - Component props
 * @param {Function} props.onExportCSV - Quick CSV export handler
 * @param {Function} props.onExportPDF - Quick PDF export handler
 * @param {Function} props.onOpenModal - Open detailed export modal
 * @param {boolean} props.isExporting - Export in progress
 * @param {boolean} props.disabled - Disable button
 * @param {string} props.variant - Button variant ('default', 'compact', 'icon')
 * @param {string} props.className - Additional CSS classes
 */
function ExportButton({
  onExportCSV,
  onExportPDF,
  onOpenModal,
  isExporting = false,
  disabled = false,
  variant = 'default',
  className = '',
}) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close dropdown on escape key
  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  const handleQuickCSV = () => {
    setIsOpen(false)
    if (onExportCSV) {
      onExportCSV()
    }
  }

  const handleQuickPDF = () => {
    setIsOpen(false)
    if (onExportPDF) {
      onExportPDF()
    }
  }

  const handleOpenModal = () => {
    setIsOpen(false)
    if (onOpenModal) {
      onOpenModal()
    }
  }

  // Icon-only variant
  if (variant === 'icon') {
    return (
      <button
        onClick={handleOpenModal}
        disabled={disabled || isExporting}
        className={`p-2 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 hover:border-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        title="Export Data"
      >
        {isExporting ? (
          <LoadingSpinner className="w-5 h-5 text-cyan-400" />
        ) : (
          <DownloadIcon className="w-5 h-5 text-slate-300" />
        )}
      </button>
    )
  }

  // Compact variant (no dropdown)
  if (variant === 'compact') {
    return (
      <button
        onClick={handleOpenModal}
        disabled={disabled || isExporting}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 hover:border-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      >
        {isExporting ? (
          <LoadingSpinner className="w-4 h-4 text-cyan-400" />
        ) : (
          <DownloadIcon className="w-4 h-4 text-slate-300" />
        )}
        <span className="text-sm font-medium text-slate-200">Export</span>
      </button>
    )
  }

  // Default variant with dropdown
  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Main Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled || isExporting}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-cyan-500/20"
      >
        {isExporting ? (
          <LoadingSpinner className="w-4 h-4 text-white" />
        ) : (
          <DownloadIcon className="w-4 h-4 text-white" />
        )}
        <span className="text-sm font-medium text-white">Export</span>
        <ChevronDownIcon className={`w-4 h-4 text-white/80 transition-transform ${
          isOpen ? 'rotate-180' : ''
        }`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-64 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
          {/* Quick Export Options */}
          <div className="border-b border-slate-700">
            <p className="px-4 py-2 text-xs font-medium text-slate-400 uppercase tracking-wide">
              Quick Export
            </p>
            <MenuItem
              icon={CsvIcon}
              label="Export to CSV"
              description="Spreadsheet-compatible format"
              onClick={handleQuickCSV}
              disabled={!onExportCSV}
            />
            <MenuItem
              icon={PdfIcon}
              label="Export to PDF"
              description="Printable report format"
              onClick={handleQuickPDF}
              disabled={!onExportPDF}
            />
          </div>

          {/* Advanced Export */}
          <div>
            <MenuItem
              icon={SettingsIcon}
              label="Advanced Export..."
              description="Choose data sections and options"
              onClick={handleOpenModal}
              disabled={!onOpenModal}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// PropTypes
ExportButton.propTypes = {
  onExportCSV: PropTypes.func,
  onExportPDF: PropTypes.func,
  onOpenModal: PropTypes.func,
  isExporting: PropTypes.bool,
  disabled: PropTypes.bool,
  variant: PropTypes.oneOf(['default', 'compact', 'icon']),
  className: PropTypes.string,
}

export default ExportButton
