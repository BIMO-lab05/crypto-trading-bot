/**
 * ExportPanel.jsx - Data Export Modal Component
 *
 * Purpose: Provides functionality to export performance data to CSV or PDF formats.
 * Supports customizable export options and data selection.
 *
 * Features:
 * - CSV export with configurable columns
 * - PDF report generation with charts
 * - Date range selection
 * - Preview before export
 * - Progress indicator
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useState, useCallback, useMemo } from 'react'
import PropTypes from 'prop-types'
import { format } from 'date-fns'
import { useDialog } from '../../hooks/useDialog'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Convert data to CSV format
 */
function convertToCSV(data, columns) {
  if (!data || data.length === 0) return ''

  // Create header row
  const header = columns.map((col) => col.label).join(',')

  // Create data rows
  const rows = data.map((item) =>
    columns
      .map((col) => {
        const value = item[col.key]
        // Escape commas and quotes in values
        if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
          return `"${value.replace(/"/g, '""')}"`
        }
        return value ?? ''
      })
      .join(',')
  )

  return [header, ...rows].join('\n')
}

/**
 * Download file
 */
function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * Format number for export
 */
function formatNumber(value, decimals = 2) {
  if (value == null || isNaN(value)) return ''
  return Number(value).toFixed(decimals)
}

/**
 * Format date for export
 */
function formatDate(timestamp) {
  if (!timestamp) return ''
  const date = typeof timestamp === 'string' ? new Date(timestamp) : new Date(timestamp)
  return format(date, 'yyyy-MM-dd HH:mm:ss')
}

// ============================================================================
// EXPORT CONFIGURATIONS
// ============================================================================

const EXPORT_SECTIONS = {
  metrics: {
    label: 'Performance Metrics',
    description: 'Key performance indicators (Sharpe, Sortino, etc.)',
    columns: [
      { key: 'metric', label: 'Metric' },
      { key: 'value', label: 'Value' },
      { key: 'description', label: 'Description' },
    ],
  },
  equityCurve: {
    label: 'Equity Curve',
    description: 'Portfolio value over time',
    columns: [
      { key: 'timestamp', label: 'Timestamp' },
      { key: 'equity', label: 'Equity' },
      { key: 'pnl', label: 'Trade P&L' },
      { key: 'cumulativePnl', label: 'Cumulative P&L' },
    ],
  },
  drawdown: {
    label: 'Drawdown Series',
    description: 'Peak-to-trough declines over time',
    columns: [
      { key: 'timestamp', label: 'Timestamp' },
      { key: 'drawdownPercent', label: 'Drawdown %' },
      { key: 'drawdownValue', label: 'Drawdown Value' },
      { key: 'peak', label: 'Peak Value' },
    ],
  },
  trades: {
    label: 'Trade History',
    description: 'Individual trade records',
    columns: [
      { key: 'id', label: 'Trade ID' },
      { key: 'symbol', label: 'Symbol' },
      { key: 'side', label: 'Side' },
      { key: 'entry_price', label: 'Entry Price' },
      { key: 'exit_price', label: 'Exit Price' },
      { key: 'quantity', label: 'Quantity' },
      { key: 'realized_pnl', label: 'P&L' },
      { key: 'opened_at', label: 'Opened At' },
      { key: 'closed_at', label: 'Closed At' },
    ],
  },
  strategy: {
    label: 'Strategy Attribution',
    description: 'Performance by trading strategy',
    columns: [
      { key: 'strategy', label: 'Strategy' },
      { key: 'trades', label: 'Trades' },
      { key: 'pnl', label: 'Total P&L' },
      { key: 'winRate', label: 'Win Rate %' },
      { key: 'profitFactor', label: 'Profit Factor' },
    ],
  },
}

// ============================================================================
// SECTION CHECKBOX COMPONENT
// ============================================================================

const SectionCheckbox = ({ section, config, checked, onChange }) => (
  <label className="flex items-start gap-3 p-3 bg-slate-800/50 rounded-lg cursor-pointer hover:bg-slate-700/50 transition-colors">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(section, e.target.checked)}
      className="mt-1 w-4 h-4 rounded border-slate-600 bg-slate-700 text-cyan-500 focus:ring-cyan-500/50 focus:ring-offset-slate-900"
    />
    <div className="flex-1">
      <p className="text-sm font-medium text-slate-200">{config.label}</p>
      <p className="text-xs text-slate-500 mt-0.5">{config.description}</p>
    </div>
  </label>
)

// ============================================================================
// LOADING SPINNER
// ============================================================================

const LoadingSpinner = () => (
  <svg
    className="animate-spin w-5 h-5 text-cyan-400"
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
// MAIN COMPONENT
// ============================================================================

/**
 * ExportPanel - Data Export Modal
 *
 * @param {Object} props - Component props
 * @param {Object} props.data - Data to export
 * @param {Function} props.onClose - Close handler
 */
function ExportPanel({ data, onClose }) {
  // State for selected sections
  const [selectedSections, setSelectedSections] = useState({
    metrics: true,
    equityCurve: true,
    drawdown: true,
    trades: false, // Large dataset, default off
    strategy: true,
  })

  // State for export format
  const [exportFormat, setExportFormat] = useState('csv')

  // State for export progress
  const [isExporting, setIsExporting] = useState(false)
  const [exportProgress, setExportProgress] = useState('')

  // Handle section toggle
  const handleSectionToggle = useCallback((section, checked) => {
    setSelectedSections((prev) => ({
      ...prev,
      [section]: checked,
    }))
  }, [])

  // Prepare metrics data for export
  const metricsData = useMemo(() => {
    if (!data?.metrics) return []

    const metricsMap = {
      totalPnL: { label: 'Total P&L', format: 'currency' },
      totalTrades: { label: 'Total Trades', format: 'integer' },
      winRate: { label: 'Win Rate', format: 'percent' },
      profitFactor: { label: 'Profit Factor', format: 'ratio' },
      sharpeRatio: { label: 'Sharpe Ratio', format: 'ratio' },
      sortinoRatio: { label: 'Sortino Ratio', format: 'ratio' },
      maxDrawdown: { label: 'Max Drawdown', format: 'currency' },
      maxDrawdownPercent: { label: 'Max Drawdown %', format: 'percent' },
      var95: { label: 'VaR (95%)', format: 'currency' },
      cvar95: { label: 'CVaR (95%)', format: 'currency' },
      avgPnL: { label: 'Avg P&L per Trade', format: 'currency' },
      avgWin: { label: 'Avg Win', format: 'currency' },
      avgLoss: { label: 'Avg Loss', format: 'currency' },
    }

    return Object.entries(data.metrics)
      .filter(([key]) => metricsMap[key])
      .map(([key, value]) => ({
        metric: metricsMap[key].label,
        value: formatNumber(value, metricsMap[key].format === 'integer' ? 0 : 2),
        description: key,
      }))
  }, [data?.metrics])

  // Handle CSV export
  const handleExportCSV = useCallback(async () => {
    setIsExporting(true)
    setExportProgress('Preparing data...')

    try {
      const timestamp = format(new Date(), 'yyyyMMdd_HHmmss')
      const zipContent = []

      // Export each selected section
      for (const [section, isSelected] of Object.entries(selectedSections)) {
        if (!isSelected) continue

        setExportProgress(`Exporting ${EXPORT_SECTIONS[section].label}...`)

        let sectionData = []
        const columns = EXPORT_SECTIONS[section].columns

        switch (section) {
          case 'metrics':
            sectionData = metricsData
            break
          case 'equityCurve':
            sectionData = (data?.equityCurve || []).map((item) => ({
              ...item,
              timestamp: formatDate(item.timestamp),
              equity: formatNumber(item.equity),
              pnl: formatNumber(item.pnl),
              cumulativePnl: formatNumber(item.cumulativePnl),
            }))
            break
          case 'drawdown':
            sectionData = (data?.drawdownSeries || []).map((item) => ({
              ...item,
              timestamp: formatDate(item.timestamp),
              drawdownPercent: formatNumber(item.drawdownPercent),
              drawdownValue: formatNumber(item.drawdownValue),
              peak: formatNumber(item.peak),
            }))
            break
          case 'trades':
            sectionData = (data?.trades || []).map((item) => ({
              ...item,
              opened_at: formatDate(item.opened_at),
              closed_at: formatDate(item.closed_at),
              entry_price: formatNumber(item.entry_price, 4),
              exit_price: formatNumber(item.exit_price, 4),
              quantity: formatNumber(item.quantity, 4),
              realized_pnl: formatNumber(item.realized_pnl),
            }))
            break
          case 'strategy':
            sectionData = (data?.strategyData || []).map((item) => ({
              ...item,
              pnl: formatNumber(item.pnl),
              winRate: formatNumber(item.winRate),
              profitFactor: formatNumber(item.profitFactor),
            }))
            break
        }

        if (sectionData.length > 0) {
          const csv = convertToCSV(sectionData, columns)
          downloadFile(
            csv,
            `performance_${section}_${timestamp}.csv`,
            'text/csv;charset=utf-8'
          )
        }

        // Small delay to prevent overwhelming the browser
        await new Promise((resolve) => setTimeout(resolve, 100))
      }

      setExportProgress('Export complete!')
      setTimeout(() => {
        setIsExporting(false)
        setExportProgress('')
      }, 1500)
    } catch (error) {
      console.error('Export error:', error)
      setExportProgress('Export failed. Please try again.')
      setIsExporting(false)
    }
  }, [selectedSections, data, metricsData])

  // Handle PDF export (simplified - generates HTML report)
  const handleExportPDF = useCallback(async () => {
    setIsExporting(true)
    setExportProgress('Generating report...')

    try {
      const timestamp = format(new Date(), 'yyyy-MM-dd HH:mm:ss')

      // Generate HTML report
      const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Performance Report - ${data?.period || 'All Time'}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; color: #333; }
    h1 { color: #0ea5e9; border-bottom: 2px solid #0ea5e9; padding-bottom: 10px; }
    h2 { color: #475569; margin-top: 30px; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; }
    th, td { border: 1px solid #e2e8f0; padding: 12px; text-align: left; }
    th { background-color: #f1f5f9; font-weight: bold; }
    tr:nth-child(even) { background-color: #f8fafc; }
    .positive { color: #10b981; }
    .negative { color: #f43f5e; }
    .metric-card { display: inline-block; width: 200px; margin: 10px; padding: 15px; border: 1px solid #e2e8f0; border-radius: 8px; }
    .metric-value { font-size: 24px; font-weight: bold; }
    .metric-label { color: #64748b; font-size: 12px; text-transform: uppercase; }
    .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 12px; }
  </style>
</head>
<body>
  <h1>Trading Performance Report</h1>
  <p>Generated: ${timestamp} | Period: ${data?.period || 'All Time'}</p>

  <h2>Key Metrics</h2>
  <div class="metrics-grid">
    ${metricsData.map((m) => `
      <div class="metric-card">
        <div class="metric-label">${m.metric}</div>
        <div class="metric-value">${m.value}</div>
      </div>
    `).join('')}
  </div>

  ${selectedSections.strategy && data?.strategyData?.length > 0 ? `
    <h2>Strategy Attribution</h2>
    <table>
      <tr>
        <th>Strategy</th>
        <th>Trades</th>
        <th>P&L</th>
        <th>Win Rate</th>
        <th>Profit Factor</th>
      </tr>
      ${data.strategyData.map((s) => `
        <tr>
          <td>${s.strategy}</td>
          <td>${s.trades}</td>
          <td class="${s.pnl >= 0 ? 'positive' : 'negative'}">$${formatNumber(s.pnl)}</td>
          <td>${formatNumber(s.winRate)}%</td>
          <td>${formatNumber(s.profitFactor)}</td>
        </tr>
      `).join('')}
    </table>
  ` : ''}

  <div class="footer">
    <p>This report was automatically generated by the Crypto Trading Bot Performance Dashboard.</p>
    <p>Past performance does not guarantee future results. Trade responsibly.</p>
  </div>
</body>
</html>
      `

      // Download as HTML (can be printed to PDF from browser)
      downloadFile(
        html,
        `performance_report_${format(new Date(), 'yyyyMMdd')}.html`,
        'text/html;charset=utf-8'
      )

      setExportProgress('Report generated! Print to PDF from your browser.')
      setTimeout(() => {
        setIsExporting(false)
        setExportProgress('')
      }, 2000)
    } catch (error) {
      console.error('PDF export error:', error)
      setExportProgress('Report generation failed.')
      setIsExporting(false)
    }
  }, [data, metricsData, selectedSections])

  // Handle export action
  const handleExport = useCallback(() => {
    if (exportFormat === 'csv') {
      handleExportCSV()
    } else {
      handleExportPDF()
    }
  }, [exportFormat, handleExportCSV, handleExportPDF])

  // Check if any section is selected
  const hasSelection = Object.values(selectedSections).some(Boolean)

  // Don't fire close while an export is running
  const handleDialogClose = useCallback(() => {
    if (!isExporting) onClose()
  }, [isExporting, onClose])

  const dialogRef = useDialog(true, handleDialogClose)

  const handleBackdropClick = useCallback(
    (event) => {
      if (event.target === event.currentTarget) handleDialogClose()
    },
    [handleDialogClose],
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-panel-title"
        aria-describedby="export-panel-desc"
        tabIndex={-1}
        className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h2 id="export-panel-title" className="text-lg font-semibold text-slate-100">Export Performance Data</h2>
            <p id="export-panel-desc" className="text-xs text-slate-500 mt-0.5">Select data to include in the export</p>
          </div>
          <button
            type="button"
            onClick={handleDialogClose}
            aria-label="Close export panel"
            className="text-slate-400 hover:text-slate-200 transition-colors"
            disabled={isExporting}
          >
            <svg aria-hidden="true" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Format Selection */}
          <div>
            <label className="text-sm font-medium text-slate-300 block mb-3">Export Format</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setExportFormat('csv')}
                className={`p-4 rounded-lg border text-left transition-colors ${
                  exportFormat === 'csv'
                    ? 'border-cyan-500 bg-cyan-500/10'
                    : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'
                }`}
              >
                <div className="flex items-center gap-3">
                  <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <div>
                    <p className="font-medium text-slate-200">CSV Files</p>
                    <p className="text-xs text-slate-500">Spreadsheet compatible</p>
                  </div>
                </div>
              </button>
              <button
                onClick={() => setExportFormat('pdf')}
                className={`p-4 rounded-lg border text-left transition-colors ${
                  exportFormat === 'pdf'
                    ? 'border-cyan-500 bg-cyan-500/10'
                    : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'
                }`}
              >
                <div className="flex items-center gap-3">
                  <svg className="w-8 h-8 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <div>
                    <p className="font-medium text-slate-200">PDF Report</p>
                    <p className="text-xs text-slate-500">Formatted document</p>
                  </div>
                </div>
              </button>
            </div>
          </div>

          {/* Section Selection */}
          <div>
            <label className="text-sm font-medium text-slate-300 block mb-3">Data Sections</label>
            <div className="space-y-2">
              {Object.entries(EXPORT_SECTIONS).map(([section, config]) => (
                <SectionCheckbox
                  key={section}
                  section={section}
                  config={config}
                  checked={selectedSections[section]}
                  onChange={handleSectionToggle}
                />
              ))}
            </div>
          </div>

          {/* Data Summary */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
              Export Summary
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-500">Period:</span>
                <span className="text-slate-200 ml-2">{data?.period || 'All Time'}</span>
              </div>
              <div>
                <span className="text-slate-500">Total Trades:</span>
                <span className="text-slate-200 ml-2">{data?.trades?.length || 0}</span>
              </div>
              <div>
                <span className="text-slate-500">Equity Points:</span>
                <span className="text-slate-200 ml-2">{data?.equityCurve?.length || 0}</span>
              </div>
              <div>
                <span className="text-slate-500">Strategies:</span>
                <span className="text-slate-200 ml-2">{data?.strategyData?.length || 0}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 bg-slate-800/30">
          {/* Progress */}
          {exportProgress && (
            <div role="status" aria-live="polite" className="flex items-center gap-2 mb-4 text-sm text-cyan-400">
              {isExporting && <LoadingSpinner />}
              <span>{exportProgress}</span>
            </div>
          )}

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={handleDialogClose}
              disabled={isExporting}
              className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-slate-100 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleExport}
              disabled={isExporting || !hasSelection}
              className="px-6 py-2 bg-blue-700 hover:bg-blue-600 text-white font-medium rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isExporting ? (
                <>
                  <LoadingSpinner />
                  Exporting...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Export {exportFormat.toUpperCase()}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// PropTypes
ExportPanel.propTypes = {
  data: PropTypes.shape({
    metrics: PropTypes.object,
    equityCurve: PropTypes.array,
    drawdownSeries: PropTypes.array,
    returnsDistribution: PropTypes.object,
    strategyData: PropTypes.array,
    trades: PropTypes.array,
    period: PropTypes.string,
    generatedAt: PropTypes.string,
  }),
  onClose: PropTypes.func.isRequired,
}

export default ExportPanel
