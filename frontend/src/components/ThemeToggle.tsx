/**
 * ThemeToggle.tsx - Dark/Light Mode Toggle Component
 *
 * Purpose: Provides a beautiful, accessible toggle button for switching
 * between dark and light modes. Features smooth animations and visual
 * feedback for the current theme state.
 *
 * Features:
 * - Animated sun/moon icons for visual feedback
 * - Accessible keyboard navigation
 * - ARIA labels for screen readers
 * - Smooth transition animations
 * - Multiple size variants
 * - Optional label display
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

import React, { memo } from 'react';
import { useTheme } from '../contexts/ThemeContext';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

/**
 * Size variants for the toggle button
 * 'sm' - Small (24x24)
 * 'md' - Medium (32x32) - Default
 * 'lg' - Large (40x40)
 */
type ToggleSize = 'sm' | 'md' | 'lg';

/**
 * Props for the ThemeToggle component
 */
interface ThemeToggleProps {
  // Size variant of the toggle button
  size?: ToggleSize;

  // Whether to show the theme label (Dark/Light)
  showLabel?: boolean;

  // Additional CSS classes
  className?: string;

  // Custom aria-label for accessibility
  ariaLabel?: string;
}

// ============================================================================
// SIZE CONFIGURATION
// ============================================================================

/**
 * Size configurations for different toggle variants
 * Maps size names to pixel dimensions and styling classes
 */
const sizeConfig: Record<ToggleSize, {
  button: string;
  icon: string;
  label: string;
}> = {
  sm: {
    button: 'w-8 h-8',
    icon: 'w-4 h-4',
    label: 'text-xs',
  },
  md: {
    button: 'w-10 h-10',
    icon: 'w-5 h-5',
    label: 'text-sm',
  },
  lg: {
    button: 'w-12 h-12',
    icon: 'w-6 h-6',
    label: 'text-base',
  },
};

// ============================================================================
// ICON COMPONENTS
// ============================================================================

/**
 * SunIcon - SVG icon representing light mode
 * Features animated rays for visual appeal
 */
const SunIcon: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    {/* Center circle - the sun */}
    <circle cx="12" cy="12" r="4" />
    {/* Sun rays - positioned around the center */}
    <path d="M12 2v2" />  {/* Top ray */}
    <path d="M12 20v2" /> {/* Bottom ray */}
    <path d="m4.93 4.93 1.41 1.41" />   {/* Top-left ray */}
    <path d="m17.66 17.66 1.41 1.41" /> {/* Bottom-right ray */}
    <path d="M2 12h2" />  {/* Left ray */}
    <path d="M20 12h2" /> {/* Right ray */}
    <path d="m6.34 17.66-1.41 1.41" />  {/* Bottom-left ray */}
    <path d="m19.07 4.93-1.41 1.41" />  {/* Top-right ray */}
  </svg>
);

/**
 * MoonIcon - SVG icon representing dark mode
 * Features a crescent moon shape
 */
const MoonIcon: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    {/* Crescent moon shape */}
    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
  </svg>
);

/**
 * MonitorIcon - SVG icon representing system theme
 * Used when following system preference
 */
const MonitorIcon: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    {/* Monitor frame */}
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
    {/* Monitor stand */}
    <line x1="8" y1="21" x2="16" y2="21" />
    <line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * ThemeToggle - Dark/Light mode toggle button component
 *
 * Renders an accessible button that toggles between dark and light themes.
 * Uses the useTheme hook to access and modify the current theme state.
 *
 * @param size - Size variant ('sm', 'md', 'lg')
 * @param showLabel - Whether to show the theme label
 * @param className - Additional CSS classes
 * @param ariaLabel - Custom aria-label for accessibility
 *
 * @example
 * ```tsx
 * // Basic usage
 * <ThemeToggle />
 *
 * // With label
 * <ThemeToggle showLabel size="lg" />
 *
 * // Custom styling
 * <ThemeToggle className="ml-4" size="sm" />
 * ```
 */
const ThemeToggle: React.FC<ThemeToggleProps> = memo(({
  size = 'md',
  showLabel = false,
  className = '',
  ariaLabel,
}) => {
  // -------------------------------------------------------------------------
  // HOOKS
  // -------------------------------------------------------------------------

  // Get theme context values and functions
  const { theme, isDarkMode, toggleTheme } = useTheme();

  // -------------------------------------------------------------------------
  // DERIVED VALUES
  // -------------------------------------------------------------------------

  // Get size-specific styles
  const sizes = sizeConfig[size];

  // Determine the label text based on current theme
  const labelText = isDarkMode ? 'Dark' : 'Light';

  // Determine the aria-label for accessibility
  const accessibilityLabel = ariaLabel ||
    `Switch to ${isDarkMode ? 'light' : 'dark'} mode. Current theme: ${theme}`;

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Theme Toggle Button */}
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={accessibilityLabel}
        aria-pressed={isDarkMode}
        className={`
          ${sizes.button}
          relative
          flex items-center justify-center
          rounded-lg
          transition-all duration-200 ease-in-out
          focus:outline-none focus:ring-2 focus:ring-offset-2

          /* Light mode styles */
          bg-slate-100 text-slate-600
          hover:bg-slate-200 hover:text-slate-900
          focus:ring-slate-400 focus:ring-offset-white

          /* Dark mode styles */
          dark:bg-slate-700 dark:text-slate-300
          dark:hover:bg-slate-600 dark:hover:text-slate-100
          dark:focus:ring-slate-500 dark:focus:ring-offset-slate-900
        `}
      >
        {/* Icon Container with Animation */}
        <span
          className={`
            relative
            transition-transform duration-300 ease-out
            ${isDarkMode ? 'rotate-0' : 'rotate-180'}
          `}
        >
          {/* Sun Icon - Visible in Light Mode */}
          <span
            className={`
              absolute inset-0
              flex items-center justify-center
              transition-all duration-300
              ${isDarkMode
                ? 'opacity-0 scale-0 rotate-90'
                : 'opacity-100 scale-100 rotate-0'
              }
            `}
          >
            <SunIcon className={`${sizes.icon} text-amber-500`} />
          </span>

          {/* Moon Icon - Visible in Dark Mode */}
          <span
            className={`
              flex items-center justify-center
              transition-all duration-300
              ${isDarkMode
                ? 'opacity-100 scale-100 rotate-0'
                : 'opacity-0 scale-0 -rotate-90'
              }
            `}
          >
            <MoonIcon className={`${sizes.icon} text-blue-400`} />
          </span>
        </span>
      </button>

      {/* Optional Label */}
      {showLabel && (
        <span
          className={`
            ${sizes.label}
            font-medium
            text-slate-600 dark:text-slate-300
            select-none
            transition-colors duration-200
          `}
        >
          {labelText}
        </span>
      )}
    </div>
  );
});

// Display name for React DevTools
ThemeToggle.displayName = 'ThemeToggle';

// ============================================================================
// ADDITIONAL COMPONENTS
// ============================================================================

/**
 * ThemeToggleSwitch - Alternative switch-style toggle
 *
 * A more prominent switch-style toggle with sliding animation.
 * Better suited for settings pages or prominent placement.
 */
export const ThemeToggleSwitch: React.FC<{
  className?: string;
  showIcons?: boolean;
}> = memo(({ className = '', showIcons = true }) => {
  const { isDarkMode, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDarkMode}
      aria-label={`Toggle ${isDarkMode ? 'light' : 'dark'} mode`}
      onClick={toggleTheme}
      className={`
        relative inline-flex h-7 w-14
        shrink-0 cursor-pointer rounded-full
        border-2 border-transparent
        transition-colors duration-200 ease-in-out
        focus:outline-none focus:ring-2 focus:ring-offset-2

        /* Background colors */
        ${isDarkMode
          ? 'bg-blue-600 focus:ring-blue-500 dark:focus:ring-offset-slate-900'
          : 'bg-slate-200 focus:ring-slate-400 focus:ring-offset-white'
        }

        ${className}
      `}
    >
      {/* Sliding Knob */}
      <span
        aria-hidden="true"
        className={`
          pointer-events-none inline-block h-6 w-6
          transform rounded-full
          bg-white shadow-lg ring-0
          transition duration-200 ease-in-out

          /* Position based on theme */
          ${isDarkMode ? 'translate-x-7' : 'translate-x-0'}
        `}
      >
        {/* Icons inside the knob */}
        {showIcons && (
          <span className="absolute inset-0 flex items-center justify-center">
            {isDarkMode ? (
              <MoonIcon className="w-3.5 h-3.5 text-blue-600" />
            ) : (
              <SunIcon className="w-3.5 h-3.5 text-amber-500" />
            )}
          </span>
        )}
      </span>
    </button>
  );
});

ThemeToggleSwitch.displayName = 'ThemeToggleSwitch';

/**
 * ThemeSelector - Dropdown-style theme selector
 *
 * Provides options for Dark, Light, and System themes.
 * Useful for settings pages with full theme control.
 */
export const ThemeSelector: React.FC<{
  className?: string;
}> = memo(({ className = '' }) => {
  const { theme, setTheme, useSystemTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="Theme selection"
      className={`flex items-center gap-2 ${className}`}
    >
      {/* Dark Mode Button */}
      <button
        type="button"
        onClick={() => setTheme('dark')}
        aria-pressed={theme === 'dark'}
        aria-label="Dark theme"
        className={`
          flex items-center gap-2 px-3 py-2 rounded-lg
          transition-all duration-200
          ${theme === 'dark'
            ? 'bg-blue-600 text-white'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600'
          }
        `}
      >
        <MoonIcon className="w-4 h-4" />
        <span className="text-sm font-medium">Dark</span>
      </button>

      {/* Light Mode Button */}
      <button
        type="button"
        onClick={() => setTheme('light')}
        aria-pressed={theme === 'light'}
        aria-label="Light theme"
        className={`
          flex items-center gap-2 px-3 py-2 rounded-lg
          transition-all duration-200
          ${theme === 'light'
            ? 'bg-blue-600 text-white'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600'
          }
        `}
      >
        <SunIcon className="w-4 h-4" />
        <span className="text-sm font-medium">Light</span>
      </button>

      {/* System Theme Button */}
      <button
        type="button"
        onClick={useSystemTheme}
        aria-label="Use system theme"
        className={`
          flex items-center gap-2 px-3 py-2 rounded-lg
          transition-all duration-200
          bg-slate-100 text-slate-600 hover:bg-slate-200
          dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600
        `}
      >
        <MonitorIcon className="w-4 h-4" />
        <span className="text-sm font-medium">System</span>
      </button>
    </div>
  );
});

ThemeSelector.displayName = 'ThemeSelector';

// ============================================================================
// EXPORTS
// ============================================================================

export default ThemeToggle;
