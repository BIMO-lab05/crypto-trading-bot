/**
 * CorrelationHeatmap.jsx - Asset Correlation Matrix Visualization
 *
 * Purpose: Displays correlation coefficients between traded assets as a heatmap.
 * Helps identify diversification opportunities and correlated pairs.
 *
 * Features:
 * - Color-coded correlation matrix
 * - Hover tooltips with detailed info
 * - Correlation strength indicator
 * - Symbol axis labels
 * - Dark mode optimized
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-11
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import React, { useMemo } from 'react'
import PropTypes from 'prop-types'
import ChartFigure from '../a11y/ChartFigure'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Get color for correlation value
 * Green = negative (diversification), Blue = neutral, Red = positive (correlation)
 *
 * @param {number} value - Correlation coefficient (-1 to 1)
 * @returns {string} HSL color string
 */
function getCorrelationColor(value) {
  if (value == null || isNaN(value)) return 'hsl(220, 15%, 30%)'

  // Clamp value between -1 and 1
  const clamped = Math.max(-1, Math.min(1, value))

  // Map correlation to color
  // -1 (negative correlation) = Green (120)
  // 0 (no correlation) = Blue (220)
  // 1 (positive correlation) = Red (0)
  const hue = clamped >= 0
    ? 220 - (clamped * 220) // Blue to Red
    : 220 + (Math.abs(clamped) * 100) // Blue to Green

  // Saturation based on strength
  const saturation = Math.abs(clamped) * 60 + 20

  // Lightness - darker for stronger correlations
  const lightness = 50 - Math.abs(clamped) * 15

  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

/**
 * Get correlation strength label
 */
function getCorrelationStrength(value) {
  if (value == null) return { label: 'N/A', color: 'text-slate-400' }

  const abs = Math.abs(value)

  if (abs >= 0.8) return { label: 'Very Strong', color: value > 0 ? 'text-rose-400' : 'text-emerald-400' }
  if (abs >= 0.6) return { label: 'Strong', color: value > 0 ? 'text-orange-400' : 'text-green-400' }
  if (abs >= 0.4) return { label: 'Moderate', color: 'text-amber-400' }
  if (abs >= 0.2) return { label: 'Weak', color: 'text-blue-400' }
  return { label: 'Very Weak', color: 'text-slate-400' }
}

/**
 * Generate mock correlation data for demo/fallback
 */
function generateMockCorrelation(symbols) {
  const matrix = []

  for (let i = 0; i < symbols.length; i++) {
    const row = []
    for (let j = 0; j < symbols.length; j++) {
      if (i === j) {
        row.push(1.0) // Perfect self-correlation
      } else if (j > i) {
        // Generate realistic crypto correlation (typically 0.5-0.9 for major pairs)
        const baseCorr = 0.5 + Math.random() * 0.4
        // BTC-ETH tends to have higher correlation
        const isBtcEth = (symbols[i].includes('BTC') && symbols[j].includes('ETH')) ||
                        (symbols[i].includes('ETH') && symbols[j].includes('BTC'))
        row.push(isBtcEth ? 0.85 + Math.random() * 0.1 : baseCorr)
      } else {
        // Mirror from upper triangle
        row.push(matrix[j][i])
      }
    }
    matrix.push(row)
  }

  return { matrix, symbols, timestamp: Date.now() }
}

// ============================================================================
// CORRELATION CELL COMPONENT
// ============================================================================

/**
 * CorrelationCell - Individual cell in the heatmap
 */
const CorrelationCell = ({ value, rowSymbol, colSymbol, size = 'default', isSelected, onClick }) => {
  const bgColor = getCorrelationColor(value)
  const strength = getCorrelationStrength(value)
  const isDiagonal = rowSymbol === colSymbol

  const sizeClasses = {
    small: 'w-10 h-10 text-[10px]',
    default: 'w-14 h-14 text-xs',
    large: 'w-20 h-20 text-sm',
  }

  return (
    <div
      className={`
        ${sizeClasses[size]}
        flex items-center justify-center
        font-semibold rounded
        cursor-pointer transition-all duration-200
        ${isDiagonal ? 'ring-2 ring-slate-500' : ''}
        ${isSelected ? 'ring-2 ring-cyan-400 scale-105 z-10' : 'hover:scale-105 hover:z-10'}
      `}
      style={{ backgroundColor: bgColor }}
      onClick={() => onClick && onClick({ value, rowSymbol, colSymbol })}
      title={`${rowSymbol} vs ${colSymbol}: ${value?.toFixed(3) || 'N/A'}`}
    >
      <span className={isDiagonal ? 'text-slate-400' : 'text-white'}>
        {value != null ? value.toFixed(2) : '-'}
      </span>
    </div>
  )
}

// ============================================================================
// LOADING SKELETON
// ============================================================================

const CorrelationHeatmapSkeleton = () => (
  <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 animate-pulse">
    <div className="flex items-center justify-between mb-4">
      <div className="h-6 bg-slate-700 rounded w-1/3"></div>
      <div className="h-6 bg-slate-700 rounded w-1/6"></div>
    </div>
    <div className="grid grid-cols-5 gap-1">
      {Array(25).fill(0).map((_, i) => (
        <div key={i} className="h-12 bg-slate-700 rounded"></div>
      ))}
    </div>
  </div>
)

// ============================================================================
// DETAIL PANEL COMPONENT
// ============================================================================

const CorrelationDetailPanel = ({ selection }) => {
  if (!selection) {
    return (
      <div className="bg-slate-900/50 rounded-lg p-4 text-center">
        <p className="text-sm text-slate-400">
          Click a cell to view correlation details
        </p>
      </div>
    )
  }

  const { value, rowSymbol, colSymbol } = selection
  const strength = getCorrelationStrength(value)
  const isDiagonal = rowSymbol === colSymbol

  if (isDiagonal) {
    return (
      <div className="bg-slate-900/50 rounded-lg p-4 text-center">
        <p className="text-sm text-slate-400">
          Self-correlation is always 1.0
        </p>
      </div>
    )
  }

  return (
    <div className="bg-slate-900/50 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-slate-200">
          {rowSymbol.replace('USDT', '')} vs {colSymbol.replace('USDT', '')}
        </h4>
        <span className={`text-lg font-bold ${value >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
          {value?.toFixed(3)}
        </span>
      </div>

      <div className="space-y-2">
        {/* Strength */}
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400">Strength</span>
          <span className={`text-sm font-medium ${strength.color}`}>{strength.label}</span>
        </div>

        {/* Direction */}
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-400">Direction</span>
          <span className={`text-sm ${value >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {value >= 0 ? 'Positive (moves together)' : 'Negative (moves opposite)'}
          </span>
        </div>

        {/* Implication */}
        <div className="pt-2 border-t border-slate-700/50">
          <p className="text-xs text-slate-500">
            {value > 0.7
              ? 'High correlation - limited diversification benefit'
              : value > 0.3
              ? 'Moderate correlation - some diversification benefit'
              : value >= 0
              ? 'Low correlation - good diversification potential'
              : 'Negative correlation - excellent for hedging'}
          </p>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * CorrelationHeatmap - Asset Correlation Matrix Visualization
 *
 * @param {Object} props - Component props
 * @param {Array<Array<number>>} props.matrix - Correlation matrix data
 * @param {Array<string>} props.symbols - Symbol labels for axes
 * @param {boolean} props.loading - Loading state
 * @param {string} props.cellSize - Cell size ('small', 'default', 'large')
 * @param {boolean} props.useMockData - Use mock data if no data provided
 * @param {string} props.className - Additional CSS classes
 */
function CorrelationHeatmap({
  matrix = [],
  symbols = [],
  loading = false,
  cellSize = 'default',
  useMockData = true,
  className = '',
}) {
  // State for selected cell
  const [selection, setSelection] = React.useState(null)

  // Use mock data if no data provided
  const effectiveData = useMemo(() => {
    if (matrix.length > 0 && symbols.length > 0) {
      return { matrix, symbols }
    }

    if (useMockData) {
      const defaultSymbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']
      return generateMockCorrelation(defaultSymbols)
    }

    return { matrix: [], symbols: [] }
  }, [matrix, symbols, useMockData])

  // Calculate average correlation (excluding diagonal)
  const avgCorrelation = useMemo(() => {
    const { matrix } = effectiveData
    if (matrix.length === 0) return 0

    let sum = 0
    let count = 0

    for (let i = 0; i < matrix.length; i++) {
      for (let j = 0; j < matrix[i].length; j++) {
        if (i !== j) {
          sum += matrix[i][j]
          count++
        }
      }
    }

    return count > 0 ? sum / count : 0
  }, [effectiveData])

  // Handle cell click
  const handleCellClick = (cellData) => {
    setSelection(cellData)
  }

  if (loading) {
    return <CorrelationHeatmapSkeleton />
  }

  const { matrix: dataMatrix, symbols: dataSymbols } = effectiveData

  if (dataMatrix.length === 0) {
    return (
      <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 p-5 ${className}`}>
        <h3 className="text-base font-semibold text-slate-100 mb-4">
          Asset Correlation Matrix
        </h3>
        <div className="flex items-center justify-center h-[200px] text-slate-400">
          <div className="text-center">
            <p className="text-lg mb-2">No correlation data available</p>
            <p className="text-sm text-slate-500">
              Correlation matrix requires historical price data
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-100">
              Asset Correlation Matrix
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Correlation coefficients between traded pairs
            </p>
          </div>

          {/* Average Correlation Badge */}
          <div className="px-3 py-1.5 rounded-lg bg-slate-900/50 border border-slate-700/50">
            <p className="text-[10px] text-slate-400 uppercase">Avg Correlation</p>
            <p className={`text-sm font-bold ${avgCorrelation > 0.6 ? 'text-rose-400' : avgCorrelation > 0.3 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {avgCorrelation.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        <ChartFigure
          summary={`Asset correlation matrix for ${dataSymbols.length} symbols: ${dataSymbols.map((s) => s.replace('USDT', '')).join(', ')}. Average pairwise correlation ${avgCorrelation.toFixed(2)}.`}
          tableCaption="Pairwise correlation coefficients"
          columns={[
            { key: 'pair', label: 'Pair' },
            { key: 'value', label: 'Correlation' },
          ]}
          rows={(() => {
            const out = []
            for (let i = 0; i < dataSymbols.length; i++) {
              for (let j = i + 1; j < dataSymbols.length; j++) {
                out.push({
                  pair: `${dataSymbols[i].replace('USDT', '')} / ${dataSymbols[j].replace('USDT', '')}`,
                  value: dataMatrix[i]?.[j]?.toFixed(2) ?? '',
                })
              }
            }
            return out
          })()}
        >
        <div className="flex gap-4">
          {/* Heatmap Grid */}
          <div className="flex-shrink-0 overflow-x-auto">
            {/* Column Headers */}
            <div className="flex mb-1">
              {/* Empty corner cell */}
              <div className={`${cellSize === 'small' ? 'w-16' : cellSize === 'large' ? 'w-20' : 'w-16'}`}></div>
              {/* Column labels */}
              {dataSymbols.map((symbol, idx) => (
                <div
                  key={`col-${idx}`}
                  className={`${cellSize === 'small' ? 'w-10' : cellSize === 'large' ? 'w-20' : 'w-14'} text-center`}
                >
                  <span className="text-[10px] font-medium text-slate-400 transform -rotate-45 inline-block origin-center">
                    {symbol.replace('USDT', '')}
                  </span>
                </div>
              ))}
            </div>

            {/* Matrix Rows */}
            {dataMatrix.map((row, rowIdx) => (
              <div key={`row-${rowIdx}`} className="flex items-center mb-1">
                {/* Row label */}
                <div className={`${cellSize === 'small' ? 'w-16' : cellSize === 'large' ? 'w-20' : 'w-16'} pr-2 text-right`}>
                  <span className="text-[10px] font-medium text-slate-400">
                    {dataSymbols[rowIdx]?.replace('USDT', '')}
                  </span>
                </div>

                {/* Row cells */}
                <div className="flex gap-1">
                  {row.map((value, colIdx) => (
                    <CorrelationCell
                      key={`cell-${rowIdx}-${colIdx}`}
                      value={value}
                      rowSymbol={dataSymbols[rowIdx]}
                      colSymbol={dataSymbols[colIdx]}
                      size={cellSize}
                      isSelected={
                        selection?.rowSymbol === dataSymbols[rowIdx] &&
                        selection?.colSymbol === dataSymbols[colIdx]
                      }
                      onClick={handleCellClick}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Detail Panel */}
          <div className="flex-1 min-w-[200px]">
            <CorrelationDetailPanel selection={selection} />
          </div>
        </div>
        </ChartFigure>
      </div>

      {/* Footer - Color Legend */}
      <div className="px-5 py-3 bg-slate-800/30 border-t border-slate-700/50">
        <div className="flex items-center justify-between">
          {/* Color Scale Legend */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500">Correlation:</span>
            <div className="flex items-center gap-1">
              <div className="w-4 h-3 rounded" style={{ backgroundColor: getCorrelationColor(-1) }}></div>
              <span className="text-[10px] text-slate-500">-1</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-4 h-3 rounded" style={{ backgroundColor: getCorrelationColor(0) }}></div>
              <span className="text-[10px] text-slate-500">0</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-4 h-3 rounded" style={{ backgroundColor: getCorrelationColor(1) }}></div>
              <span className="text-[10px] text-slate-500">+1</span>
            </div>
          </div>

          {/* Interpretation */}
          <div className="flex items-center gap-3 text-[10px] text-slate-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              Negative = Diversify
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-rose-500"></span>
              Positive = Correlated
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// PropTypes
CorrelationHeatmap.propTypes = {
  matrix: PropTypes.arrayOf(PropTypes.arrayOf(PropTypes.number)),
  symbols: PropTypes.arrayOf(PropTypes.string),
  loading: PropTypes.bool,
  cellSize: PropTypes.oneOf(['small', 'default', 'large']),
  useMockData: PropTypes.bool,
  className: PropTypes.string,
}

export default CorrelationHeatmap
