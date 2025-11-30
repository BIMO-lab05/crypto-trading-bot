/**
 * Settings.jsx - Application Settings Page
 *
 * Purpose: Provides a comprehensive settings page for the crypto trading bot
 * with full dark mode support. Allows users to configure trading parameters,
 * notifications, theme preferences, and account settings.
 *
 * Features:
 * - Theme selection (Dark/Light/System)
 * - Trading configuration settings
 * - Notification preferences
 * - Risk management settings
 * - API configuration
 * - Full dark mode support with smooth transitions
 *
 * Author: Frontend Developer Agent
 * Date: 2025-11-28
 */

import React, { useState, useCallback } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { ThemeSelector, ThemeToggleSwitch } from '../components/ThemeToggle';

// ============================================================================
// TYPE DEFINITIONS (JSDoc for JavaScript)
// ============================================================================

/**
 * @typedef {Object} TradingSettings
 * @property {number} maxPositionSize - Maximum position size percentage
 * @property {number} stopLossPercent - Default stop loss percentage
 * @property {number} takeProfitPercent - Default take profit percentage
 * @property {boolean} enablePaperTrading - Whether paper trading is enabled
 * @property {string} defaultTimeframe - Default chart timeframe
 */

/**
 * @typedef {Object} NotificationSettings
 * @property {boolean} emailNotifications - Enable email notifications
 * @property {boolean} pushNotifications - Enable push notifications
 * @property {boolean} tradeAlerts - Alert on trade execution
 * @property {boolean} priceAlerts - Alert on price movements
 * @property {boolean} systemAlerts - Alert on system events
 */

// ============================================================================
// CONSTANTS
// ============================================================================

// Default trading settings values
const DEFAULT_TRADING_SETTINGS = {
  maxPositionSize: 2,
  stopLossPercent: 2,
  takeProfitPercent: 4,
  enablePaperTrading: true,
  defaultTimeframe: '1h',
};

// Default notification settings values
const DEFAULT_NOTIFICATION_SETTINGS = {
  emailNotifications: true,
  pushNotifications: false,
  tradeAlerts: true,
  priceAlerts: true,
  systemAlerts: true,
};

// Available timeframe options
const TIMEFRAME_OPTIONS = [
  { value: '1m', label: '1 Minute' },
  { value: '5m', label: '5 Minutes' },
  { value: '15m', label: '15 Minutes' },
  { value: '30m', label: '30 Minutes' },
  { value: '1h', label: '1 Hour' },
  { value: '4h', label: '4 Hours' },
  { value: '1d', label: '1 Day' },
];

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/**
 * SettingsSection - Reusable section container for settings groups
 *
 * @param {Object} props - Component props
 * @param {string} props.title - Section title
 * @param {string} props.description - Section description
 * @param {React.ReactNode} props.children - Section content
 * @param {React.ReactNode} props.icon - Optional icon component
 */
const SettingsSection = ({ title, description, icon, children }) => {
  return (
    <div className="card mb-6 transition-colors duration-200">
      {/* Section Header */}
      <div className="card-header">
        <div className="flex items-center gap-3">
          {/* Optional Icon */}
          {icon && (
            <div className="flex-shrink-0 p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 transition-colors duration-200">
              {icon}
            </div>
          )}

          {/* Title and Description */}
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 transition-colors duration-200">
              {title}
            </h3>
            {description && (
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5 transition-colors duration-200">
                {description}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Section Content */}
      <div className="card-body">{children}</div>
    </div>
  );
};

/**
 * SettingsRow - Individual setting row with label and control
 *
 * @param {Object} props - Component props
 * @param {string} props.label - Setting label
 * @param {string} props.description - Setting description
 * @param {React.ReactNode} props.children - Setting control
 */
const SettingsRow = ({ label, description, children }) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between py-4 border-b border-slate-200 dark:border-slate-700 last:border-b-0 transition-colors duration-200">
      {/* Label and Description */}
      <div className="mb-2 sm:mb-0 sm:pr-4">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-200 transition-colors duration-200">
          {label}
        </label>
        {description && (
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 transition-colors duration-200">
            {description}
          </p>
        )}
      </div>

      {/* Control */}
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
};

/**
 * Toggle - Custom toggle switch component
 *
 * @param {Object} props - Component props
 * @param {boolean} props.checked - Toggle state
 * @param {Function} props.onChange - Change handler
 * @param {string} props.id - Input ID for accessibility
 */
const Toggle = ({ checked, onChange, id }) => {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`
        relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full
        border-2 border-transparent transition-colors duration-200 ease-in-out
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
        dark:focus:ring-blue-400 dark:focus:ring-offset-slate-800
        ${checked ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'}
      `}
    >
      <span className="sr-only">Toggle setting</span>
      <span
        aria-hidden="true"
        className={`
          pointer-events-none inline-block h-5 w-5 transform rounded-full
          bg-white shadow ring-0 transition duration-200 ease-in-out
          ${checked ? 'translate-x-5' : 'translate-x-0'}
        `}
      />
    </button>
  );
};

/**
 * TextInput - Styled text input component
 *
 * @param {Object} props - Component props
 * @param {string} props.value - Input value
 * @param {Function} props.onChange - Change handler
 * @param {string} props.type - Input type
 * @param {string} props.placeholder - Placeholder text
 * @param {string} props.id - Input ID
 */
const TextInput = ({ value, onChange, type = 'text', placeholder, id, ...props }) => {
  return (
    <input
      type={type}
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="
        w-full sm:w-48 px-3 py-2 rounded-lg
        bg-white dark:bg-slate-700
        border border-slate-300 dark:border-slate-600
        text-slate-900 dark:text-slate-100
        placeholder-slate-400 dark:placeholder-slate-500
        focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400
        focus:border-transparent
        transition-colors duration-200
      "
      {...props}
    />
  );
};

/**
 * SelectInput - Styled select dropdown component
 *
 * @param {Object} props - Component props
 * @param {string} props.value - Selected value
 * @param {Function} props.onChange - Change handler
 * @param {Array} props.options - Array of {value, label} options
 * @param {string} props.id - Input ID
 */
const SelectInput = ({ value, onChange, options, id }) => {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="
        w-full sm:w-48 px-3 py-2 rounded-lg
        bg-white dark:bg-slate-700
        border border-slate-300 dark:border-slate-600
        text-slate-900 dark:text-slate-100
        focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400
        focus:border-transparent
        transition-colors duration-200
        cursor-pointer
      "
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
};

/**
 * NumberInput - Styled number input with unit suffix
 *
 * @param {Object} props - Component props
 * @param {number} props.value - Input value
 * @param {Function} props.onChange - Change handler
 * @param {string} props.unit - Unit suffix (e.g., '%', 'USD')
 * @param {number} props.min - Minimum value
 * @param {number} props.max - Maximum value
 * @param {number} props.step - Step increment
 * @param {string} props.id - Input ID
 */
const NumberInput = ({ value, onChange, unit, min, max, step = 1, id }) => {
  return (
    <div className="relative w-full sm:w-32">
      <input
        type="number"
        id={id}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        min={min}
        max={max}
        step={step}
        className="
          w-full px-3 py-2 pr-8 rounded-lg
          bg-white dark:bg-slate-700
          border border-slate-300 dark:border-slate-600
          text-slate-900 dark:text-slate-100
          focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400
          focus:border-transparent
          transition-colors duration-200
          [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none
        "
      />
      {unit && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 dark:text-slate-400 text-sm pointer-events-none transition-colors duration-200">
          {unit}
        </span>
      )}
    </div>
  );
};

// ============================================================================
// ICON COMPONENTS
// ============================================================================

/**
 * PaletteIcon - Icon for theme settings
 */
const PaletteIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="13.5" cy="6.5" r=".5" />
    <circle cx="17.5" cy="10.5" r=".5" />
    <circle cx="8.5" cy="7.5" r=".5" />
    <circle cx="6.5" cy="12.5" r=".5" />
    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.555C21.965 6.012 17.461 2 12 2z" />
  </svg>
);

/**
 * ChartIcon - Icon for trading settings
 */
const ChartIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 3v18h18" />
    <path d="m19 9-5 5-4-4-3 3" />
  </svg>
);

/**
 * BellIcon - Icon for notification settings
 */
const BellIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </svg>
);

/**
 * ShieldIcon - Icon for risk management settings
 */
const ShieldIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
);

/**
 * KeyIcon - Icon for API settings
 */
const KeyIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="7.5" cy="15.5" r="5.5" />
    <path d="m21 2-9.6 9.6" />
    <path d="m15.5 7.5 3 3L22 7l-3-3" />
  </svg>
);

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * Settings - Main settings page component
 *
 * Provides a comprehensive settings interface with:
 * - Theme customization
 * - Trading parameters
 * - Notification preferences
 * - Risk management
 * - API configuration
 *
 * @returns {JSX.Element} The settings page
 */
const Settings = () => {
  // -------------------------------------------------------------------------
  // HOOKS
  // -------------------------------------------------------------------------

  // Get theme context for displaying current theme
  const { theme, isDarkMode } = useTheme();

  // -------------------------------------------------------------------------
  // STATE
  // -------------------------------------------------------------------------

  // Trading settings state
  const [tradingSettings, setTradingSettings] = useState(DEFAULT_TRADING_SETTINGS);

  // Notification settings state
  const [notificationSettings, setNotificationSettings] = useState(DEFAULT_NOTIFICATION_SETTINGS);

  // API key state (masked for display)
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');

  // Form submission state
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // -------------------------------------------------------------------------
  // HANDLERS
  // -------------------------------------------------------------------------

  /**
   * Updates a trading setting value
   */
  const updateTradingSetting = useCallback((key, value) => {
    setTradingSettings((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  /**
   * Updates a notification setting value
   */
  const updateNotificationSetting = useCallback((key, value) => {
    setNotificationSettings((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  /**
   * Handles form submission
   */
  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setSaveSuccess(false);

    try {
      // Simulate API call
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // In a real app, you would save to backend here
      console.log('Saving settings:', {
        tradingSettings,
        notificationSettings,
        apiKey: apiKey ? '***' : '',
      });

      setSaveSuccess(true);

      // Reset success message after 3 seconds
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      console.error('Error saving settings:', error);
    } finally {
      setIsSaving(false);
    }
  }, [tradingSettings, notificationSettings, apiKey]);

  /**
   * Resets all settings to defaults
   */
  const handleReset = useCallback(() => {
    setTradingSettings(DEFAULT_TRADING_SETTINGS);
    setNotificationSettings(DEFAULT_NOTIFICATION_SETTINGS);
    setApiKey('');
    setApiSecret('');
  }, []);

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      {/* Page Container */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 transition-colors duration-200">
            Settings
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 transition-colors duration-200">
            Configure your trading bot preferences and account settings
          </p>
        </div>

        {/* ================================================================
            THEME SETTINGS SECTION
            ================================================================ */}
        <SettingsSection
          title="Appearance"
          description="Customize the look and feel of your dashboard"
          icon={<PaletteIcon />}
        >
          {/* Current Theme Display */}
          <SettingsRow
            label="Current Theme"
            description="Your current theme preference"
          >
            <div className="flex items-center gap-2">
              <span className={`
                inline-flex items-center px-3 py-1 rounded-full text-sm font-medium
                ${isDarkMode
                  ? 'bg-slate-700 text-slate-200'
                  : 'bg-slate-200 text-slate-700'
                }
                transition-colors duration-200
              `}>
                {isDarkMode ? 'Dark Mode' : 'Light Mode'}
              </span>
            </div>
          </SettingsRow>

          {/* Theme Toggle Switch */}
          <SettingsRow
            label="Dark Mode"
            description="Toggle between dark and light mode"
          >
            <ThemeToggleSwitch />
          </SettingsRow>

          {/* Theme Selector */}
          <SettingsRow
            label="Theme Selection"
            description="Choose your preferred theme or follow system settings"
          >
            <ThemeSelector />
          </SettingsRow>
        </SettingsSection>

        {/* ================================================================
            TRADING SETTINGS SECTION
            ================================================================ */}
        <SettingsSection
          title="Trading Settings"
          description="Configure your default trading parameters"
          icon={<ChartIcon />}
        >
          {/* Paper Trading Toggle */}
          <SettingsRow
            label="Paper Trading Mode"
            description="Trade with virtual funds for testing strategies"
          >
            <Toggle
              id="paper-trading"
              checked={tradingSettings.enablePaperTrading}
              onChange={(value) => updateTradingSetting('enablePaperTrading', value)}
            />
          </SettingsRow>

          {/* Default Timeframe */}
          <SettingsRow
            label="Default Timeframe"
            description="Default chart timeframe for analysis"
          >
            <SelectInput
              id="default-timeframe"
              value={tradingSettings.defaultTimeframe}
              onChange={(value) => updateTradingSetting('defaultTimeframe', value)}
              options={TIMEFRAME_OPTIONS}
            />
          </SettingsRow>

          {/* Max Position Size */}
          <SettingsRow
            label="Max Position Size"
            description="Maximum percentage of portfolio per trade"
          >
            <NumberInput
              id="max-position-size"
              value={tradingSettings.maxPositionSize}
              onChange={(value) => updateTradingSetting('maxPositionSize', value)}
              unit="%"
              min={0.1}
              max={100}
              step={0.1}
            />
          </SettingsRow>
        </SettingsSection>

        {/* ================================================================
            RISK MANAGEMENT SECTION
            ================================================================ */}
        <SettingsSection
          title="Risk Management"
          description="Configure stop loss and take profit defaults"
          icon={<ShieldIcon />}
        >
          {/* Default Stop Loss */}
          <SettingsRow
            label="Default Stop Loss"
            description="Automatic stop loss percentage for new positions"
          >
            <NumberInput
              id="stop-loss"
              value={tradingSettings.stopLossPercent}
              onChange={(value) => updateTradingSetting('stopLossPercent', value)}
              unit="%"
              min={0.1}
              max={50}
              step={0.1}
            />
          </SettingsRow>

          {/* Default Take Profit */}
          <SettingsRow
            label="Default Take Profit"
            description="Automatic take profit percentage for new positions"
          >
            <NumberInput
              id="take-profit"
              value={tradingSettings.takeProfitPercent}
              onChange={(value) => updateTradingSetting('takeProfitPercent', value)}
              unit="%"
              min={0.1}
              max={100}
              step={0.1}
            />
          </SettingsRow>
        </SettingsSection>

        {/* ================================================================
            NOTIFICATION SETTINGS SECTION
            ================================================================ */}
        <SettingsSection
          title="Notifications"
          description="Manage your notification preferences"
          icon={<BellIcon />}
        >
          {/* Email Notifications */}
          <SettingsRow
            label="Email Notifications"
            description="Receive important updates via email"
          >
            <Toggle
              id="email-notifications"
              checked={notificationSettings.emailNotifications}
              onChange={(value) => updateNotificationSetting('emailNotifications', value)}
            />
          </SettingsRow>

          {/* Push Notifications */}
          <SettingsRow
            label="Push Notifications"
            description="Receive real-time push notifications"
          >
            <Toggle
              id="push-notifications"
              checked={notificationSettings.pushNotifications}
              onChange={(value) => updateNotificationSetting('pushNotifications', value)}
            />
          </SettingsRow>

          {/* Trade Alerts */}
          <SettingsRow
            label="Trade Alerts"
            description="Get notified when trades are executed"
          >
            <Toggle
              id="trade-alerts"
              checked={notificationSettings.tradeAlerts}
              onChange={(value) => updateNotificationSetting('tradeAlerts', value)}
            />
          </SettingsRow>

          {/* Price Alerts */}
          <SettingsRow
            label="Price Alerts"
            description="Get notified on significant price movements"
          >
            <Toggle
              id="price-alerts"
              checked={notificationSettings.priceAlerts}
              onChange={(value) => updateNotificationSetting('priceAlerts', value)}
            />
          </SettingsRow>

          {/* System Alerts */}
          <SettingsRow
            label="System Alerts"
            description="Get notified about system status changes"
          >
            <Toggle
              id="system-alerts"
              checked={notificationSettings.systemAlerts}
              onChange={(value) => updateNotificationSetting('systemAlerts', value)}
            />
          </SettingsRow>
        </SettingsSection>

        {/* ================================================================
            API CONFIGURATION SECTION
            ================================================================ */}
        <SettingsSection
          title="API Configuration"
          description="Configure your exchange API credentials"
          icon={<KeyIcon />}
        >
          {/* Warning Message */}
          <div className="mb-4 p-4 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 transition-colors duration-200">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-amber-500 dark:text-amber-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-amber-800 dark:text-amber-200 transition-colors duration-200">
                  Security Notice
                </h3>
                <p className="mt-1 text-sm text-amber-700 dark:text-amber-300 transition-colors duration-200">
                  API keys are stored securely and encrypted. Never share your API secret with anyone.
                </p>
              </div>
            </div>
          </div>

          {/* API Key Input */}
          <SettingsRow
            label="API Key"
            description="Your Bybit API key for trading"
          >
            <TextInput
              id="api-key"
              type="password"
              value={apiKey}
              onChange={setApiKey}
              placeholder="Enter API key"
            />
          </SettingsRow>

          {/* API Secret Input */}
          <SettingsRow
            label="API Secret"
            description="Your Bybit API secret (never shared)"
          >
            <TextInput
              id="api-secret"
              type="password"
              value={apiSecret}
              onChange={setApiSecret}
              placeholder="Enter API secret"
            />
          </SettingsRow>
        </SettingsSection>

        {/* ================================================================
            ACTION BUTTONS
            ================================================================ */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-6 border-t border-slate-200 dark:border-slate-700 transition-colors duration-200">
          {/* Left side - Reset Button */}
          <button
            type="button"
            onClick={handleReset}
            className="
              w-full sm:w-auto
              px-4 py-2 rounded-lg font-medium
              bg-slate-200 dark:bg-slate-700
              text-slate-700 dark:text-slate-300
              hover:bg-slate-300 dark:hover:bg-slate-600
              focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2
              dark:focus:ring-offset-slate-900
              transition-colors duration-200
            "
          >
            Reset to Defaults
          </button>

          {/* Right side - Save Button and Status */}
          <div className="flex items-center gap-4 w-full sm:w-auto">
            {/* Success Message */}
            {saveSuccess && (
              <span className="text-sm text-emerald-600 dark:text-emerald-400 font-medium transition-colors duration-200">
                Settings saved successfully!
              </span>
            )}

            {/* Save Button */}
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="
                w-full sm:w-auto
                px-6 py-2 rounded-lg font-medium
                bg-blue-600 text-white
                hover:bg-blue-700
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                dark:focus:ring-offset-slate-900
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors duration-200
                flex items-center justify-center gap-2
              "
            >
              {isSaving ? (
                <>
                  {/* Loading Spinner */}
                  <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Saving...
                </>
              ) : (
                'Save Settings'
              )}
            </button>
          </div>
        </div>

        {/* ================================================================
            DANGER ZONE
            ================================================================ */}
        <div className="mt-8 pt-8 border-t border-slate-200 dark:border-slate-700 transition-colors duration-200">
          <h3 className="text-lg font-semibold text-red-600 dark:text-red-400 mb-4 transition-colors duration-200">
            Danger Zone
          </h3>

          <div className="p-4 rounded-lg border-2 border-red-200 dark:border-red-800/50 bg-red-50 dark:bg-red-900/10 transition-colors duration-200">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <h4 className="text-sm font-medium text-red-800 dark:text-red-200 transition-colors duration-200">
                  Delete All Trading Data
                </h4>
                <p className="text-sm text-red-600 dark:text-red-400 mt-1 transition-colors duration-200">
                  This action cannot be undone. All your trading history and configurations will be permanently deleted.
                </p>
              </div>
              <button
                type="button"
                className="
                  flex-shrink-0
                  px-4 py-2 rounded-lg font-medium
                  bg-red-600 text-white
                  hover:bg-red-700
                  focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2
                  dark:focus:ring-offset-slate-900
                  transition-colors duration-200
                "
              >
                Delete Data
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// EXPORTS
// ============================================================================

export default Settings;
