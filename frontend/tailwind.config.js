/**
 * Tailwind CSS Configuration - Dark Mode Theme System
 *
 * Purpose: Configures Tailwind CSS for the crypto trading bot dashboard
 * with comprehensive dark mode support using the 'class' strategy.
 *
 * Dark Mode Strategy: 'class'
 * - Dark mode is activated by adding 'dark' class to the HTML element
 * - Allows programmatic theme switching via JavaScript
 * - Persists user preference across sessions
 *
 * Color Palette (Dark Theme):
 * - Background: slate-900 (#0f172a)
 * - Card background: slate-800 (#1e293b)
 * - Text primary: slate-100 (#f1f5f9)
 * - Text secondary: slate-400 (#94a3b8)
 * - Accent/primary: blue-500 (#3b82f6)
 * - Success: emerald-500 (#10b981)
 * - Warning: amber-500 (#f59e0b)
 * - Error: red-500 (#ef4444)
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

/** @type {import('tailwindcss').Config} */
export default {
  // ============================================================================
  // CONTENT CONFIGURATION
  // ============================================================================

  /**
   * Content paths - tells Tailwind where to look for class names
   * Includes HTML, JavaScript, TypeScript, and JSX/TSX files
   */
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],

  // ============================================================================
  // DARK MODE CONFIGURATION
  // ============================================================================

  /**
   * Dark mode strategy: 'class'
   *
   * Options:
   * - 'media': Uses system preference (prefers-color-scheme)
   * - 'class': Uses 'dark' class on HTML element (SELECTED)
   * - 'selector': Uses custom CSS selector
   *
   * Using 'class' strategy allows:
   * 1. Manual theme toggling via JavaScript
   * 2. User preference persistence in localStorage
   * 3. Override of system preference when desired
   */
  darkMode: 'class',

  // ============================================================================
  // THEME CONFIGURATION
  // ============================================================================

  theme: {
    extend: {
      // -----------------------------------------------------------------------
      // COLOR PALETTE
      // -----------------------------------------------------------------------

      colors: {
        // ---------------------------------------------------------------------
        // PRIMARY BRAND COLORS
        // Main accent color used for interactive elements
        // ---------------------------------------------------------------------
        primary: {
          50: '#f0f9ff',   // Lightest - backgrounds
          100: '#e0f2fe',  // Light - hover states
          200: '#bae6fd',  // Light - borders
          300: '#7dd3fc',  // Medium-light
          400: '#38bdf8',  // Medium
          500: '#0ea5e9',  // DEFAULT - main accent
          600: '#0284c7',  // Dark - hover states
          700: '#0369a1',  // Darker
          800: '#075985',  // Very dark
          900: '#0c4a6e',  // Darkest
          950: '#082f49',  // Ultra dark
        },

        // ---------------------------------------------------------------------
        // SUCCESS COLORS
        // Used for positive states, completed actions, profit indicators
        // ---------------------------------------------------------------------
        success: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#10b981',  // DEFAULT - emerald-500
          600: '#059669',  // Darker variant
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#022c22',
        },

        // ---------------------------------------------------------------------
        // DANGER/ERROR COLORS
        // Used for errors, warnings, loss indicators, emergency actions
        // ---------------------------------------------------------------------
        danger: {
          50: '#fef2f2',
          100: '#fee2e2',
          200: '#fecaca',
          300: '#fca5a5',
          400: '#f87171',
          500: '#ef4444',  // DEFAULT - red-500
          600: '#dc2626',  // Darker variant
          700: '#b91c1c',
          800: '#991b1b',
          900: '#7f1d1d',
          950: '#450a0a',
        },

        // ---------------------------------------------------------------------
        // WARNING COLORS
        // Used for caution states, pending actions, neutral indicators
        // ---------------------------------------------------------------------
        warning: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',  // DEFAULT - amber-500
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
          950: '#451a03',
        },

        // ---------------------------------------------------------------------
        // DARK MODE SPECIFIC COLORS
        // Custom semantic colors for dark theme backgrounds and surfaces
        // ---------------------------------------------------------------------
        dark: {
          // Main background color
          bg: '#0f172a',           // slate-900
          // Card/container background
          card: '#1e293b',         // slate-800
          // Elevated card background
          elevated: '#334155',      // slate-700
          // Border color
          border: '#334155',        // slate-700
          // Hover states
          hover: '#475569',         // slate-600
          // Primary text
          text: '#f1f5f9',          // slate-100
          // Secondary text
          'text-secondary': '#94a3b8', // slate-400
          // Muted text
          'text-muted': '#64748b',     // slate-500
        },

        // ---------------------------------------------------------------------
        // LIGHT MODE SPECIFIC COLORS
        // Custom semantic colors for light theme backgrounds and surfaces
        // ---------------------------------------------------------------------
        light: {
          // Main background color
          bg: '#f8fafc',           // slate-50
          // Card/container background
          card: '#ffffff',         // white
          // Elevated card background
          elevated: '#f1f5f9',     // slate-100
          // Border color
          border: '#e2e8f0',       // slate-200
          // Hover states
          hover: '#e2e8f0',        // slate-200
          // Primary text
          text: '#0f172a',         // slate-900
          // Secondary text
          'text-secondary': '#475569', // slate-600
          // Muted text
          'text-muted': '#94a3b8',     // slate-400
        },
      },

      // -----------------------------------------------------------------------
      // BACKGROUND COLORS SHORTCUTS
      // -----------------------------------------------------------------------

      backgroundColor: {
        // Dark mode backgrounds
        'app-dark': '#0f172a',      // Main app background in dark mode
        'card-dark': '#1e293b',     // Card background in dark mode
        'surface-dark': '#334155',  // Elevated surface in dark mode

        // Light mode backgrounds
        'app-light': '#f8fafc',     // Main app background in light mode
        'card-light': '#ffffff',    // Card background in light mode
        'surface-light': '#f1f5f9', // Elevated surface in light mode
      },

      // -----------------------------------------------------------------------
      // TEXT COLORS SHORTCUTS
      // -----------------------------------------------------------------------

      textColor: {
        // Dark mode text
        'primary-dark': '#f1f5f9',   // Primary text in dark mode
        'secondary-dark': '#94a3b8', // Secondary text in dark mode
        'muted-dark': '#64748b',     // Muted text in dark mode

        // Light mode text
        'primary-light': '#0f172a',  // Primary text in light mode
        'secondary-light': '#475569',// Secondary text in light mode
        'muted-light': '#94a3b8',    // Muted text in light mode
      },

      // -----------------------------------------------------------------------
      // BORDER COLORS SHORTCUTS
      // -----------------------------------------------------------------------

      borderColor: {
        'dark': '#334155',   // Border color in dark mode
        'light': '#e2e8f0',  // Border color in light mode
      },

      // -----------------------------------------------------------------------
      // BOX SHADOW CUSTOMIZATION
      // -----------------------------------------------------------------------

      boxShadow: {
        // Dark mode shadows (more subtle)
        'dark-sm': '0 1px 2px 0 rgba(0, 0, 0, 0.3)',
        'dark': '0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px 0 rgba(0, 0, 0, 0.3)',
        'dark-md': '0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -1px rgba(0, 0, 0, 0.3)',
        'dark-lg': '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3)',
        'dark-xl': '0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.3)',

        // Premium glow effects for dark mode
        'glow-primary': '0 0 20px rgba(6, 182, 212, 0.4)',
        'glow-cyan': '0 0 25px rgba(6, 182, 212, 0.5)',
        'glow-success': '0 0 20px rgba(16, 185, 129, 0.4)',
        'glow-emerald': '0 0 25px rgba(16, 185, 129, 0.5)',
        'glow-danger': '0 0 20px rgba(244, 63, 94, 0.4)',
        'glow-rose': '0 0 25px rgba(244, 63, 94, 0.5)',
        'glow-warning': '0 0 20px rgba(245, 158, 11, 0.4)',
        'glow-amber': '0 0 25px rgba(245, 158, 11, 0.5)',
        'glow-violet': '0 0 25px rgba(139, 92, 246, 0.5)',

        // Card shadows with subtle glow
        'card-dark': '0 4px 20px -2px rgba(0, 0, 0, 0.4), 0 0 30px -10px rgba(6, 182, 212, 0.1)',
        'card-hover': '0 10px 30px -5px rgba(0, 0, 0, 0.5), 0 0 40px -10px rgba(6, 182, 212, 0.2)',
      },

      // -----------------------------------------------------------------------
      // RING COLORS FOR FOCUS STATES
      // -----------------------------------------------------------------------

      ringColor: {
        'dark-primary': 'rgba(59, 130, 246, 0.5)',   // Blue focus ring
        'dark-success': 'rgba(16, 185, 129, 0.5)',   // Green focus ring
        'dark-danger': 'rgba(239, 68, 68, 0.5)',     // Red focus ring
      },

      // -----------------------------------------------------------------------
      // ANIMATION CUSTOMIZATION
      // -----------------------------------------------------------------------

      animation: {
        // Smooth pulse for loading states
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        // Fade in animation
        'fade-in': 'fadeIn 0.3s ease-in-out',
        // Slide in from bottom
        'slide-up': 'slideUp 0.3s ease-out',
        // Glow animation for important elements
        'glow': 'glow 2s ease-in-out infinite alternate',
      },

      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(59, 130, 246, 0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(59, 130, 246, 0.6)' },
        },
      },

      // -----------------------------------------------------------------------
      // TRANSITION CUSTOMIZATION
      // -----------------------------------------------------------------------

      transitionProperty: {
        // Theme transition - includes colors and backgrounds
        'theme': 'background-color, border-color, color, fill, stroke, box-shadow',
      },

      transitionDuration: {
        // Standard theme transition duration
        'theme': '200ms',
      },

      // -----------------------------------------------------------------------
      // SPACING CUSTOMIZATION
      // -----------------------------------------------------------------------

      spacing: {
        // Extra sizes for dashboard layouts
        '18': '4.5rem',
        '88': '22rem',
        '112': '28rem',
        '128': '32rem',
      },

      // -----------------------------------------------------------------------
      // TYPOGRAPHY
      // -----------------------------------------------------------------------

      fontFamily: {
        // Use system fonts for better performance
        'sans': [
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'Oxygen',
          'Ubuntu',
          'Cantarell',
          'Fira Sans',
          'Droid Sans',
          'Helvetica Neue',
          'sans-serif',
        ],
        // Monospace for code and numbers
        'mono': [
          'SF Mono',
          'Monaco',
          'Inconsolata',
          'Fira Code',
          'Droid Sans Mono',
          'Source Code Pro',
          'monospace',
        ],
      },

      // -----------------------------------------------------------------------
      // Z-INDEX SCALE
      // -----------------------------------------------------------------------

      zIndex: {
        '60': '60',
        '70': '70',
        '80': '80',
        '90': '90',
        '100': '100',
      },
    },
  },

  // ============================================================================
  // PLUGINS
  // ============================================================================

  plugins: [],
}
