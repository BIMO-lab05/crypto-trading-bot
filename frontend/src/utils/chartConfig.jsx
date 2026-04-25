/**
 * chartConfig.js - Chart Configuration and Theme Settings
 *
 * Purpose: Provides consistent chart configurations, colors, and themes
 * for Recharts components across the performance dashboard.
 *
 * Features:
 * - Dark mode optimized color palette
 * - Common chart configurations
 * - Axis styling presets
 * - Tooltip and legend styling
 * - Responsive breakpoint configurations
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

// ============================================================================
// COLOR PALETTE
// ============================================================================

/**
 * Primary color palette for charts
 * Optimized for dark mode visibility
 */
export const colors = {
  // Primary chart colors
  primary: '#0ea5e9',      // sky-500
  secondary: '#8b5cf6',    // violet-500
  tertiary: '#f59e0b',     // amber-500

  // P&L colors
  profit: '#10b981',       // emerald-500
  profitLight: '#34d399',  // emerald-400
  profitBg: '#10b98133',   // emerald-500/20

  loss: '#f43f5e',         // rose-500
  lossLight: '#fb7185',    // rose-400
  lossBg: '#f43f5e33',     // rose-500/20

  // Neutral colors
  neutral: '#64748b',      // slate-500
  neutralLight: '#94a3b8', // slate-400
  neutralDark: '#475569',  // slate-600

  // Background colors
  background: '#0f172a',   // slate-900
  surface: '#1e293b',      // slate-800
  surfaceLight: '#334155', // slate-700

  // Grid and axis
  grid: '#334155',         // slate-700
  axis: '#475569',         // slate-600
  axisText: '#94a3b8',     // slate-400

  // Special purpose
  reference: '#6366f1',    // indigo-500
  highlight: '#22d3ee',    // cyan-400
  warning: '#f59e0b',      // amber-500
  info: '#3b82f6',         // blue-500
}

/**
 * Color series for multi-line/area charts
 */
export const colorSeries = [
  '#0ea5e9', // sky-500
  '#8b5cf6', // violet-500
  '#f59e0b', // amber-500
  '#10b981', // emerald-500
  '#f43f5e', // rose-500
  '#06b6d4', // cyan-500
  '#ec4899', // pink-500
  '#84cc16', // lime-500
  '#f97316', // orange-500
  '#14b8a6', // teal-500
]

/**
 * Get color from series by index (cycles through)
 *
 * @param {number} index - Index in series
 * @returns {string} Color hex code
 */
export function getSeriesColor(index) {
  return colorSeries[index % colorSeries.length]
}

// ============================================================================
// CHART CONFIGURATIONS
// ============================================================================

/**
 * Common chart margin configuration
 */
export const chartMargins = {
  default: { top: 10, right: 30, left: 0, bottom: 0 },
  withLabel: { top: 20, right: 30, left: 20, bottom: 20 },
  compact: { top: 5, right: 20, left: 0, bottom: 5 },
  large: { top: 20, right: 40, left: 40, bottom: 30 },
}

/**
 * Common axis configuration
 */
export const axisConfig = {
  // X-axis default configuration
  xAxis: {
    stroke: colors.axis,
    tick: {
      fill: colors.axisText,
      fontSize: 11,
    },
    axisLine: {
      stroke: colors.axis,
    },
    tickLine: {
      stroke: colors.axis,
    },
  },

  // Y-axis default configuration
  yAxis: {
    stroke: colors.axis,
    tick: {
      fill: colors.axisText,
      fontSize: 11,
    },
    axisLine: {
      stroke: colors.axis,
    },
    tickLine: {
      stroke: colors.axis,
    },
    width: 60,
  },
}

/**
 * Grid configuration
 */
export const gridConfig = {
  default: {
    strokeDasharray: '3 3',
    stroke: colors.grid,
  },
  solid: {
    stroke: colors.grid,
    strokeOpacity: 0.5,
  },
  horizontal: {
    strokeDasharray: '3 3',
    stroke: colors.grid,
    vertical: false,
  },
}

/**
 * Tooltip configuration
 */
export const tooltipConfig = {
  default: {
    contentStyle: {
      backgroundColor: colors.background,
      border: `1px solid ${colors.surfaceLight}`,
      borderRadius: '8px',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
    },
    labelStyle: {
      color: colors.axisText,
      fontWeight: 600,
      marginBottom: '4px',
    },
    itemStyle: {
      color: '#e2e8f0', // slate-200
    },
  },
  dark: {
    contentStyle: {
      backgroundColor: '#0f172a',
      border: '1px solid #334155',
      borderRadius: '8px',
    },
  },
}

/**
 * Legend configuration
 */
export const legendConfig = {
  default: {
    wrapperStyle: {
      paddingTop: '10px',
    },
    iconType: 'circle',
    iconSize: 8,
    formatter: (value) => (
      `<span style="color: #94a3b8; font-size: 12px;">${value}</span>`
    ),
  },
  bottom: {
    verticalAlign: 'bottom',
    align: 'center',
    wrapperStyle: {
      paddingTop: '20px',
    },
  },
}

// ============================================================================
// GRADIENT DEFINITIONS
// ============================================================================

/**
 * Create gradient definition for area charts
 *
 * @param {string} id - Gradient ID
 * @param {string} color - Base color
 * @param {number} startOpacity - Start opacity (default: 0.3)
 * @param {number} endOpacity - End opacity (default: 0)
 * @returns {Object} Gradient configuration object
 */
export function createGradient(id, color, startOpacity = 0.3, endOpacity = 0) {
  return {
    id,
    color,
    startOpacity,
    endOpacity,
  }
}

/**
 * Predefined gradients for common use cases
 */
export const gradients = {
  profit: createGradient('profitGradient', colors.profit, 0.3, 0),
  loss: createGradient('lossGradient', colors.loss, 0.3, 0),
  primary: createGradient('primaryGradient', colors.primary, 0.3, 0),
  neutral: createGradient('neutralGradient', colors.neutral, 0.2, 0),
}

/**
 * Generate gradient JSX for SVG defs
 *
 * @param {string} id - Gradient ID
 * @param {string} color - Base color
 * @param {number} startOpacity - Start opacity
 * @param {number} endOpacity - End opacity
 * @returns {JSX.Element} LinearGradient element
 */
export function GradientDef({ id, color, startOpacity = 0.3, endOpacity = 0 }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="5%" stopColor={color} stopOpacity={startOpacity} />
      <stop offset="95%" stopColor={color} stopOpacity={endOpacity} />
    </linearGradient>
  )
}

// ============================================================================
// RESPONSIVE CONFIGURATIONS
// ============================================================================

/**
 * Responsive chart heights based on container width
 */
export const responsiveHeights = {
  small: { width: 400, height: 200 },
  medium: { width: 600, height: 300 },
  large: { width: 900, height: 400 },
  xlarge: { width: 1200, height: 500 },
}

/**
 * Get appropriate chart height based on width
 *
 * @param {number} width - Container width
 * @returns {number} Recommended height
 */
export function getResponsiveHeight(width) {
  if (width < 400) return 200
  if (width < 600) return 250
  if (width < 900) return 300
  if (width < 1200) return 350
  return 400
}

/**
 * Tick count recommendations based on width
 *
 * @param {number} width - Container width
 * @returns {number} Recommended tick count
 */
export function getTickCount(width) {
  if (width < 400) return 4
  if (width < 600) return 6
  if (width < 900) return 8
  return 10
}

// ============================================================================
// ANIMATION CONFIGURATIONS
// ============================================================================

/**
 * Animation duration presets
 */
export const animationDurations = {
  fast: 150,
  normal: 300,
  slow: 500,
  none: 0,
}

/**
 * Animation easing presets
 */
export const animationEasings = {
  linear: 'linear',
  ease: 'ease',
  easeIn: 'ease-in',
  easeOut: 'ease-out',
  easeInOut: 'ease-in-out',
}

// ============================================================================
// REFERENCE LINE CONFIGURATIONS
// ============================================================================

/**
 * Reference line presets
 */
export const referenceLineStyles = {
  // Zero line
  zero: {
    y: 0,
    stroke: colors.reference,
    strokeWidth: 2,
    strokeOpacity: 0.5,
  },

  // Threshold warning
  warning: {
    stroke: colors.warning,
    strokeDasharray: '5 5',
    strokeOpacity: 0.7,
  },

  // Average/Mean line
  average: {
    stroke: colors.highlight,
    strokeDasharray: '5 5',
    strokeOpacity: 0.8,
  },

  // Target line
  target: {
    stroke: colors.profit,
    strokeDasharray: '10 5',
    strokeOpacity: 0.6,
  },
}

// ============================================================================
// CHART TYPE SPECIFIC CONFIGS
// ============================================================================

/**
 * Area chart configuration
 */
export const areaChartConfig = {
  // Profit area
  profit: {
    type: 'monotone',
    stroke: colors.profitLight,
    strokeWidth: 2,
    fill: `url(#profitGradient)`,
  },

  // Loss area
  loss: {
    type: 'monotone',
    stroke: colors.lossLight,
    strokeWidth: 2,
    fill: `url(#lossGradient)`,
  },

  // Neutral area
  neutral: {
    type: 'monotone',
    stroke: colors.primary,
    strokeWidth: 2,
    fill: `url(#primaryGradient)`,
  },
}

/**
 * Bar chart configuration
 */
export const barChartConfig = {
  default: {
    radius: [4, 4, 0, 0],
    maxBarSize: 50,
  },
  stacked: {
    radius: [0, 0, 0, 0],
    maxBarSize: 60,
  },
  grouped: {
    radius: [4, 4, 0, 0],
    maxBarSize: 40,
    barGap: 2,
    barCategoryGap: '20%',
  },
}

/**
 * Line chart configuration
 */
export const lineChartConfig = {
  default: {
    type: 'monotone',
    strokeWidth: 2,
    dot: false,
    activeDot: { r: 6, strokeWidth: 2 },
  },
  dotted: {
    type: 'monotone',
    strokeWidth: 2,
    dot: { r: 4 },
    activeDot: { r: 6, strokeWidth: 2 },
  },
}

/**
 * Pie chart configuration
 */
export const pieChartConfig = {
  default: {
    innerRadius: 0,
    outerRadius: '80%',
    paddingAngle: 2,
    cornerRadius: 4,
  },
  donut: {
    innerRadius: '60%',
    outerRadius: '80%',
    paddingAngle: 2,
    cornerRadius: 4,
  },
}

// ============================================================================
// BRUSH CONFIGURATION
// ============================================================================

/**
 * Brush configuration for data range selection
 */
export const brushConfig = {
  default: {
    height: 30,
    stroke: colors.primary,
    fill: colors.surface,
    fillOpacity: 0.5,
    dataKey: 'timestamp',
  },
}

// ============================================================================
// EXPORTS
// ============================================================================

export default {
  colors,
  colorSeries,
  getSeriesColor,
  chartMargins,
  axisConfig,
  gridConfig,
  tooltipConfig,
  legendConfig,
  gradients,
  createGradient,
  GradientDef,
  responsiveHeights,
  getResponsiveHeight,
  getTickCount,
  animationDurations,
  animationEasings,
  referenceLineStyles,
  areaChartConfig,
  barChartConfig,
  lineChartConfig,
  pieChartConfig,
  brushConfig,
}
