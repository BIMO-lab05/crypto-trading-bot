/**
 * contexts/index.ts - Context Exports
 *
 * Purpose: Central export point for all React contexts used in the application.
 * Provides easy access to theme context and hooks.
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

// ============================================================================
// THEME CONTEXT EXPORTS
// ============================================================================

/**
 * ThemeProvider - Provider component for theme context
 * Wrap your application with this to enable theme support
 *
 * @example
 * ```tsx
 * import { ThemeProvider } from './contexts';
 *
 * <ThemeProvider defaultTheme="dark">
 *   <App />
 * </ThemeProvider>
 * ```
 */
export { ThemeProvider } from './ThemeContext';

/**
 * useTheme - Hook to access theme context
 * Provides current theme and theme manipulation functions
 *
 * @example
 * ```tsx
 * import { useTheme } from './contexts';
 *
 * const { theme, isDarkMode, toggleTheme } = useTheme();
 * ```
 */
export { useTheme } from './ThemeContext';

/**
 * Theme type - Available theme options
 * 'dark' | 'light'
 */
export type { Theme } from './ThemeContext';

// ============================================================================
// DEFAULT EXPORT
// ============================================================================

/**
 * Default export provides ThemeProvider as the main context component
 */
export { default } from './ThemeContext';
