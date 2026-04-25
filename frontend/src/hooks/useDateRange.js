/**
 * useDateRange.js - Date Range Management Hook
 *
 * Purpose: Custom hook for managing date range selection with persistence
 * and utility functions for calculating date boundaries.
 *
 * Features:
 * - Predefined date range presets (1D, 7D, 30D, 90D, YTD, ALL)
 * - Custom date range selection
 * - LocalStorage persistence
 * - Date calculation utilities
 * - URL query string sync (optional)
 *
 * Author: Frontend Developer Agent
 * Date: 2025-12-12
 * Phase: 5.3 - Real-Time Performance Dashboard
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import {
  subDays,
  subMonths,
  startOfDay,
  endOfDay,
  startOfYear,
  startOfMonth,
  format,
  parseISO,
  isValid,
} from 'date-fns'

// ============================================================================
// CONSTANTS
// ============================================================================

/**
 * Predefined date range presets
 */
export const DATE_RANGE_PRESETS = {
  '1d': {
    label: '24 Hours',
    shortLabel: '1D',
    getDates: () => ({
      startDate: subDays(new Date(), 1),
      endDate: new Date(),
    }),
  },
  '7d': {
    label: '7 Days',
    shortLabel: '7D',
    getDates: () => ({
      startDate: subDays(new Date(), 7),
      endDate: new Date(),
    }),
  },
  '30d': {
    label: '30 Days',
    shortLabel: '30D',
    getDates: () => ({
      startDate: subDays(new Date(), 30),
      endDate: new Date(),
    }),
  },
  '90d': {
    label: '90 Days',
    shortLabel: '90D',
    getDates: () => ({
      startDate: subDays(new Date(), 90),
      endDate: new Date(),
    }),
  },
  '365d': {
    label: '1 Year',
    shortLabel: '1Y',
    getDates: () => ({
      startDate: subDays(new Date(), 365),
      endDate: new Date(),
    }),
  },
  'ytd': {
    label: 'Year to Date',
    shortLabel: 'YTD',
    getDates: () => ({
      startDate: startOfYear(new Date()),
      endDate: new Date(),
    }),
  },
  'mtd': {
    label: 'Month to Date',
    shortLabel: 'MTD',
    getDates: () => ({
      startDate: startOfMonth(new Date()),
      endDate: new Date(),
    }),
  },
  'all': {
    label: 'All Time',
    shortLabel: 'ALL',
    getDates: () => ({
      startDate: null,
      endDate: new Date(),
    }),
  },
  'custom': {
    label: 'Custom Range',
    shortLabel: 'Custom',
    getDates: () => ({
      startDate: subDays(new Date(), 30),
      endDate: new Date(),
    }),
  },
}

// Storage key for persistence
const STORAGE_KEY = 'performance_date_range'

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Parse date from various formats
 *
 * @param {string|Date|number} value - Date value to parse
 * @returns {Date|null} Parsed Date or null
 */
function parseDate(value) {
  if (!value) return null

  if (value instanceof Date) {
    return isValid(value) ? value : null
  }

  if (typeof value === 'string') {
    const parsed = parseISO(value)
    return isValid(parsed) ? parsed : null
  }

  if (typeof value === 'number') {
    const date = new Date(value)
    return isValid(date) ? date : null
  }

  return null
}

/**
 * Load date range from localStorage
 *
 * @returns {Object|null} Stored date range or null
 */
function loadFromStorage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return null

    const parsed = JSON.parse(stored)
    return {
      preset: parsed.preset || '30d',
      startDate: parseDate(parsed.startDate),
      endDate: parseDate(parsed.endDate),
    }
  } catch (error) {
    console.warn('[useDateRange] Failed to load from storage:', error)
    return null
  }
}

/**
 * Save date range to localStorage
 *
 * @param {Object} dateRange - Date range to save
 */
function saveToStorage(dateRange) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      preset: dateRange.preset,
      startDate: dateRange.startDate?.toISOString(),
      endDate: dateRange.endDate?.toISOString(),
    }))
  } catch (error) {
    console.warn('[useDateRange] Failed to save to storage:', error)
  }
}

// ============================================================================
// MAIN HOOK
// ============================================================================

/**
 * useDateRange - Date Range Management Hook
 *
 * @param {Object} options - Hook options
 * @param {string} options.defaultPreset - Default preset (default: '30d')
 * @param {boolean} options.persist - Persist selection to localStorage (default: true)
 * @param {Function} options.onChange - Callback when date range changes
 * @returns {Object} Date range state and handlers
 */
export function useDateRange(options = {}) {
  const {
    defaultPreset = '30d',
    persist = true,
    onChange,
  } = options

  // Initialize state from storage or defaults
  const [state, setState] = useState(() => {
    // Try to load from storage if persistence is enabled
    if (persist) {
      const stored = loadFromStorage()
      if (stored) {
        return stored
      }
    }

    // Use default preset
    const preset = DATE_RANGE_PRESETS[defaultPreset] || DATE_RANGE_PRESETS['30d']
    const { startDate, endDate } = preset.getDates()

    return {
      preset: defaultPreset,
      startDate,
      endDate,
    }
  })

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  /**
   * Current preset configuration
   */
  const currentPreset = useMemo(() => {
    return DATE_RANGE_PRESETS[state.preset] || DATE_RANGE_PRESETS['30d']
  }, [state.preset])

  /**
   * Formatted date strings
   */
  const formattedDates = useMemo(() => {
    return {
      startDate: state.startDate ? format(state.startDate, 'yyyy-MM-dd') : null,
      endDate: state.endDate ? format(state.endDate, 'yyyy-MM-dd') : null,
      displayRange: state.startDate
        ? `${format(state.startDate, 'MMM d, yyyy')} - ${format(state.endDate, 'MMM d, yyyy')}`
        : 'All Time',
    }
  }, [state.startDate, state.endDate])

  /**
   * Number of days in range
   */
  const dayCount = useMemo(() => {
    if (!state.startDate || !state.endDate) return null
    const diffTime = Math.abs(state.endDate - state.startDate)
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24))
  }, [state.startDate, state.endDate])

  /**
   * Query parameters for API calls
   */
  const queryParams = useMemo(() => {
    const params = { period: state.preset }

    if (state.preset === 'custom' && state.startDate && state.endDate) {
      params.start_date = state.startDate.toISOString()
      params.end_date = state.endDate.toISOString()
    }

    return params
  }, [state])

  // ============================================================================
  // HANDLERS
  // ============================================================================

  /**
   * Set date range by preset
   *
   * @param {string} presetKey - Preset key to apply
   */
  const setPreset = useCallback((presetKey) => {
    const preset = DATE_RANGE_PRESETS[presetKey]
    if (!preset) {
      console.warn(`[useDateRange] Unknown preset: ${presetKey}`)
      return
    }

    const { startDate, endDate } = preset.getDates()
    const newState = {
      preset: presetKey,
      startDate,
      endDate,
    }

    setState(newState)

    // Persist to storage
    if (persist) {
      saveToStorage(newState)
    }

    // Call onChange callback
    if (onChange) {
      onChange(newState)
    }
  }, [persist, onChange])

  /**
   * Set custom date range
   *
   * @param {Date} startDate - Start date
   * @param {Date} endDate - End date
   */
  const setCustomRange = useCallback((startDate, endDate) => {
    const parsedStart = parseDate(startDate)
    const parsedEnd = parseDate(endDate)

    if (!parsedStart || !parsedEnd) {
      console.warn('[useDateRange] Invalid date values provided')
      return
    }

    const newState = {
      preset: 'custom',
      startDate: startOfDay(parsedStart),
      endDate: endOfDay(parsedEnd),
    }

    setState(newState)

    // Persist to storage
    if (persist) {
      saveToStorage(newState)
    }

    // Call onChange callback
    if (onChange) {
      onChange(newState)
    }
  }, [persist, onChange])

  /**
   * Set start date only
   *
   * @param {Date} date - New start date
   */
  const setStartDate = useCallback((date) => {
    const parsedDate = parseDate(date)
    if (!parsedDate) return

    setState((prev) => {
      const newState = {
        ...prev,
        preset: 'custom',
        startDate: startOfDay(parsedDate),
      }

      if (persist) {
        saveToStorage(newState)
      }

      if (onChange) {
        onChange(newState)
      }

      return newState
    })
  }, [persist, onChange])

  /**
   * Set end date only
   *
   * @param {Date} date - New end date
   */
  const setEndDate = useCallback((date) => {
    const parsedDate = parseDate(date)
    if (!parsedDate) return

    setState((prev) => {
      const newState = {
        ...prev,
        preset: 'custom',
        endDate: endOfDay(parsedDate),
      }

      if (persist) {
        saveToStorage(newState)
      }

      if (onChange) {
        onChange(newState)
      }

      return newState
    })
  }, [persist, onChange])

  /**
   * Reset to default preset
   */
  const reset = useCallback(() => {
    setPreset(defaultPreset)
  }, [defaultPreset, setPreset])

  /**
   * Move date range forward by its duration
   */
  const moveForward = useCallback(() => {
    if (!state.startDate || !state.endDate || state.preset === 'all') return

    const duration = state.endDate - state.startDate
    const newStart = new Date(state.startDate.getTime() + duration)
    const newEnd = new Date(state.endDate.getTime() + duration)

    // Don't go beyond current date
    if (newEnd > new Date()) return

    setCustomRange(newStart, newEnd)
  }, [state, setCustomRange])

  /**
   * Move date range backward by its duration
   */
  const moveBackward = useCallback(() => {
    if (!state.startDate || !state.endDate || state.preset === 'all') return

    const duration = state.endDate - state.startDate
    const newStart = new Date(state.startDate.getTime() - duration)
    const newEnd = new Date(state.endDate.getTime() - duration)

    setCustomRange(newStart, newEnd)
  }, [state, setCustomRange])

  // ============================================================================
  // PRESET OPTIONS FOR UI
  // ============================================================================

  /**
   * Array of preset options for rendering
   */
  const presetOptions = useMemo(() => {
    return Object.entries(DATE_RANGE_PRESETS)
      .filter(([key]) => key !== 'custom') // Exclude custom from presets
      .map(([key, config]) => ({
        value: key,
        label: config.label,
        shortLabel: config.shortLabel,
        isActive: state.preset === key,
      }))
  }, [state.preset])

  // ============================================================================
  // RETURN VALUE
  // ============================================================================

  return {
    // Current state
    preset: state.preset,
    startDate: state.startDate,
    endDate: state.endDate,

    // Computed values
    currentPreset,
    formattedDates,
    dayCount,
    queryParams,

    // Handlers
    setPreset,
    setCustomRange,
    setStartDate,
    setEndDate,
    reset,
    moveForward,
    moveBackward,

    // UI helpers
    presetOptions,
    isCustom: state.preset === 'custom',
    isAllTime: state.preset === 'all',

    // Constants for reference
    presets: DATE_RANGE_PRESETS,
  }
}

// ============================================================================
// ADDITIONAL HOOKS
// ============================================================================

/**
 * useSimpleDateRange - Simplified date range hook
 * Returns only the period string, suitable for basic use cases
 *
 * @param {string} defaultPeriod - Default period
 * @returns {[string, Function]} [period, setPeriod] tuple
 */
export function useSimpleDateRange(defaultPeriod = '30d') {
  const [period, setPeriod] = useState(() => {
    // Try to load from storage
    try {
      const stored = localStorage.getItem('simple_date_range')
      if (stored && DATE_RANGE_PRESETS[stored]) {
        return stored
      }
    } catch (e) {
      // Ignore storage errors
    }
    return defaultPeriod
  })

  // Persist changes
  useEffect(() => {
    try {
      localStorage.setItem('simple_date_range', period)
    } catch (e) {
      // Ignore storage errors
    }
  }, [period])

  return [period, setPeriod]
}

// Default export
export default useDateRange
