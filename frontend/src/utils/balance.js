/**
 * balance.js — single source of truth for paper-account balance parsing.
 *
 * Why this exists: the dashboard previously used `parseFloat(x) || N` in four
 * places with two different values for N (10000 and 100). Two consequences:
 *
 *   1. `||` is falsy-triggered, so a legitimate balance of exactly 0 — a fully
 *      drawn-down paper account, the one moment the number matters most —
 *      rendered as the fallback instead of zero.
 *   2. `PortfolioCard` fell back to 10000 while `KeyMetricsStrip` fell back to
 *      100 for the *same field from the same query*, so the landing page could
 *      show two balances 100x apart.
 *
 * The backend paper account is $100 (`PAPER_INITIAL_BALANCE`, trading-engine
 * `config.py`). Prefer the server-sent `initial_balance` over this constant
 * wherever it is available — the constant is a last resort, not a default.
 */

/** Matches trading-engine `paper_initial_balance` (config.py). */
export const PAPER_DEFAULT_BALANCE = 100

/**
 * Parse an API-sent numeric field, falling back only when it is genuinely
 * unusable. Unlike `parseFloat(x) || fallback`, a real `0` is preserved.
 *
 * @param {unknown} value    raw field (the API sends Decimals as strings)
 * @param {number}  fallback used only for null/undefined/NaN/non-numeric
 * @returns {number}
 */
export function toFiniteNumber(value, fallback) {
  const parsed = typeof value === 'string' ? parseFloat(value) : value
  return Number.isFinite(parsed) ? parsed : fallback
}
