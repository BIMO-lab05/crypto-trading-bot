/**
 * ThemeContext.tsx - Dark Mode Theme System
 *
 * Purpose: Provides a comprehensive theme context for managing dark/light mode
 * across the React application. Persists user preference to localStorage and
 * defaults to dark mode.
 *
 * Features:
 * - Theme state management (dark/light)
 * - LocalStorage persistence
 * - System preference detection
 * - Dark mode as default
 * - Smooth theme transitions
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  ReactNode,
} from 'react';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

/**
 * Theme type - represents available theme options
 * 'dark' - Dark mode theme (default)
 * 'light' - Light mode theme
 */
export type Theme = 'dark' | 'light';

/**
 * ThemeContextValue - interface for the theme context value
 * Contains the current theme and functions to manipulate it
 */
interface ThemeContextValue {
  // Current active theme ('dark' or 'light')
  theme: Theme;

  // Boolean flag indicating if dark mode is active
  isDarkMode: boolean;

  // Function to toggle between dark and light mode
  toggleTheme: () => void;

  // Function to set a specific theme
  setTheme: (theme: Theme) => void;

  // Function to set theme based on system preference
  useSystemTheme: () => void;
}

/**
 * ThemeProviderProps - props for the ThemeProvider component
 */
interface ThemeProviderProps {
  // Child components to be wrapped by the provider
  children: ReactNode;

  // Optional default theme (defaults to 'dark')
  defaultTheme?: Theme;

  // Optional localStorage key for persistence
  storageKey?: string;
}

// ============================================================================
// CONSTANTS
// ============================================================================

// Default localStorage key for theme persistence
const THEME_STORAGE_KEY = 'crypto-trading-bot-theme';

// Version key for cache invalidation (must match index.html)
const APP_VERSION_KEY = 'crypto-trading-bot-version';

// Current app version (bump to force cache clear)
const CURRENT_VERSION = '1.1.0';

// Default theme when no preference is found
const DEFAULT_THEME: Theme = 'dark';

// CSS class name for dark mode
const DARK_MODE_CLASS = 'dark';

// ============================================================================
// CONTEXT CREATION
// ============================================================================

/**
 * ThemeContext - React context for theme management
 * Initially undefined, must be used within ThemeProvider
 */
const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

// Display name for React DevTools
ThemeContext.displayName = 'ThemeContext';

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Clear corrupted localStorage data
 * Called when version mismatch or invalid data detected
 */
const clearCorruptedStorage = (): void => {
  if (typeof window === 'undefined') return;

  try {
    localStorage.removeItem(THEME_STORAGE_KEY);
    localStorage.removeItem(APP_VERSION_KEY);
    localStorage.removeItem('crypto-trading-bot-query-cache');
    console.info('[ThemeContext] Cleared corrupted storage data');
  } catch (error) {
    console.warn('[ThemeContext] Failed to clear storage:', error);
  }
};

/**
 * Check and update app version, clear storage if outdated
 */
const checkAndUpdateVersion = (): void => {
  if (typeof window === 'undefined') return;

  try {
    const storedVersion = localStorage.getItem(APP_VERSION_KEY);
    if (storedVersion !== CURRENT_VERSION) {
      clearCorruptedStorage();
      localStorage.setItem(APP_VERSION_KEY, CURRENT_VERSION);
    }
  } catch (error) {
    console.warn('[ThemeContext] Version check failed:', error);
  }
};

/**
 * Retrieves the stored theme from localStorage
 * @returns The stored theme or null if not found
 */
const getStoredTheme = (storageKey: string): Theme | null => {
  // Check if we're in a browser environment
  if (typeof window === 'undefined') {
    return null;
  }

  // Check version first
  checkAndUpdateVersion();

  try {
    // Attempt to retrieve the theme from localStorage
    const storedValue = localStorage.getItem(storageKey);

    // Validate the stored value is a valid theme
    if (storedValue === 'dark' || storedValue === 'light') {
      return storedValue as Theme;
    }

    // Invalid value found - clear it
    if (storedValue !== null) {
      console.warn('[ThemeContext] Invalid stored theme:', storedValue);
      clearCorruptedStorage();
    }

    return null;
  } catch (error) {
    // Handle localStorage access errors (e.g., in incognito mode)
    console.warn('[ThemeContext] Failed to access localStorage:', error);
    return null;
  }
};

/**
 * Stores the theme preference in localStorage
 * @param theme - The theme to store
 * @param storageKey - The localStorage key
 */
const storeTheme = (theme: Theme, storageKey: string): void => {
  // Check if we're in a browser environment
  if (typeof window === 'undefined') {
    return;
  }

  try {
    localStorage.setItem(storageKey, theme);
  } catch (error) {
    // Handle localStorage access errors
    console.warn('Failed to store theme in localStorage:', error);
  }
};

/**
 * Detects the user's system color scheme preference
 * @returns 'dark' if system prefers dark mode, 'light' otherwise
 */
const getSystemTheme = (): Theme => {
  // Check if we're in a browser environment
  if (typeof window === 'undefined') {
    return DEFAULT_THEME;
  }

  // Check for system dark mode preference using media query
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

  return prefersDark ? 'dark' : 'light';
};

/**
 * Applies the theme to the document root element
 * Adds or removes the 'dark' class from the HTML element
 * @param theme - The theme to apply
 */
const applyThemeToDocument = (theme: Theme): void => {
  // Check if we're in a browser environment
  if (typeof window === 'undefined') {
    return;
  }

  // Get the root HTML element
  const root = document.documentElement;

  if (theme === 'dark') {
    // Add dark class to enable dark mode styles
    root.classList.add(DARK_MODE_CLASS);
  } else {
    // Remove dark class for light mode
    root.classList.remove(DARK_MODE_CLASS);
  }

  // Also update the color-scheme meta for browser UI elements
  root.style.colorScheme = theme;
};

// ============================================================================
// THEME PROVIDER COMPONENT
// ============================================================================

/**
 * ThemeProvider - Context provider component for theme management
 *
 * Wraps the application and provides theme context to all children.
 * Manages theme state, localStorage persistence, and DOM updates.
 *
 * @param children - React children to be wrapped
 * @param defaultTheme - Optional default theme (defaults to 'dark')
 * @param storageKey - Optional localStorage key for persistence
 *
 * @example
 * ```tsx
 * <ThemeProvider defaultTheme="dark">
 *   <App />
 * </ThemeProvider>
 * ```
 */
export const ThemeProvider: React.FC<ThemeProviderProps> = ({
  children,
  defaultTheme = DEFAULT_THEME,
  storageKey = THEME_STORAGE_KEY,
}) => {
  // -------------------------------------------------------------------------
  // STATE INITIALIZATION
  // -------------------------------------------------------------------------

  /**
   * Initialize theme state with the following priority:
   * 1. Stored theme from localStorage (if exists)
   * 2. Default theme provided via props (defaults to 'dark')
   */
  const [theme, setThemeState] = useState<Theme>(() => {
    // Attempt to get stored theme preference
    const storedTheme = getStoredTheme(storageKey);

    // Return stored theme if valid, otherwise use default
    return storedTheme || defaultTheme;
  });

  // -------------------------------------------------------------------------
  // EFFECTS
  // -------------------------------------------------------------------------

  /**
   * Effect: Apply theme to document when theme state changes
   * Also stores the preference in localStorage
   */
  useEffect(() => {
    // Apply the theme class to the document root
    applyThemeToDocument(theme);

    // Persist the theme preference to localStorage
    storeTheme(theme, storageKey);
  }, [theme, storageKey]);

  /**
   * Effect: Listen for system theme preference changes
   * Updates theme when user changes system preference (if using system theme)
   */
  useEffect(() => {
    // Check if we're in a browser environment
    if (typeof window === 'undefined') {
      return;
    }

    // Create media query listener for system preference changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    // Handler for system theme changes
    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      // Only update if no explicit preference is stored
      const storedTheme = getStoredTheme(storageKey);
      if (!storedTheme) {
        setThemeState(event.matches ? 'dark' : 'light');
      }
    };

    // Add event listener for system preference changes
    mediaQuery.addEventListener('change', handleSystemThemeChange);

    // Cleanup listener on unmount
    return () => {
      mediaQuery.removeEventListener('change', handleSystemThemeChange);
    };
  }, [storageKey]);

  /**
   * Effect: Apply initial theme on mount
   * Ensures dark mode is active immediately on page load
   */
  useEffect(() => {
    applyThemeToDocument(theme);
  }, []);

  // -------------------------------------------------------------------------
  // CALLBACKS
  // -------------------------------------------------------------------------

  /**
   * Toggles between dark and light mode
   * Flips the current theme to its opposite
   */
  const toggleTheme = useCallback(() => {
    setThemeState((prevTheme) => {
      const newTheme = prevTheme === 'dark' ? 'light' : 'dark';
      return newTheme;
    });
  }, []);

  /**
   * Sets a specific theme
   * @param newTheme - The theme to set ('dark' or 'light')
   */
  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
  }, []);

  /**
   * Resets to system theme preference
   * Clears stored preference and uses system setting
   */
  const useSystemTheme = useCallback(() => {
    // Remove stored preference
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(storageKey);
      } catch (error) {
        console.warn('Failed to remove theme from localStorage:', error);
      }
    }

    // Set theme based on system preference
    setThemeState(getSystemTheme());
  }, [storageKey]);

  // -------------------------------------------------------------------------
  // CONTEXT VALUE
  // -------------------------------------------------------------------------

  /**
   * Memoized context value to prevent unnecessary re-renders
   * Only updates when theme changes
   */
  const contextValue = useMemo<ThemeContextValue>(
    () => ({
      theme,
      isDarkMode: theme === 'dark',
      toggleTheme,
      setTheme,
      useSystemTheme,
    }),
    [theme, toggleTheme, setTheme, useSystemTheme]
  );

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------

  return (
    <ThemeContext.Provider value={contextValue}>
      {children}
    </ThemeContext.Provider>
  );
};

// ============================================================================
// CUSTOM HOOK
// ============================================================================

/**
 * useTheme - Custom hook to access theme context
 *
 * Provides access to the current theme and theme manipulation functions.
 * Must be used within a ThemeProvider component.
 *
 * @returns ThemeContextValue containing theme state and functions
 * @throws Error if used outside of ThemeProvider
 *
 * @example
 * ```tsx
 * const { theme, isDarkMode, toggleTheme } = useTheme();
 *
 * return (
 *   <button onClick={toggleTheme}>
 *     Current theme: {theme}
 *   </button>
 * );
 * ```
 */
export const useTheme = (): ThemeContextValue => {
  // Get the context value
  const context = useContext(ThemeContext);

  // Throw error if used outside of provider
  if (context === undefined) {
    throw new Error(
      'useTheme must be used within a ThemeProvider. ' +
      'Wrap your application with <ThemeProvider> component.'
    );
  }

  return context;
};

// ============================================================================
// EXPORTS
// ============================================================================

export default ThemeProvider;
