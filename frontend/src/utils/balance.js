/**
 * balance.js — single source of truth for paper-account balance parsing.
 *
 * Why this exists: the dashboard previously used `parseFloat(x) || N` in four
 * places with two different values for N. Two consequences:
 *
 *   1. `||` is falsy-triggered, so a legitimate balance of exactly 0 — a fully
 *      drawn-down paper account, the one moment the number matters most —
 *      rendered as the fallback instead of zero.
 *   2. `PortfolioCard` and `KeyMetricsStrip` fell back to values 100x apart
 *      for the *same field from the same query*, so the landing page could
 *      show two wildly different balances.
 *
 * The backend paper account is $10,000 per ADR-029 (2026-08-25), declared by
 * `PAPER_INITIAL_BALANCE` in trading-engine `config.py` (host-side mirror:
 * `shared/account.py`). Do not hardcode the figure anywhere else in the
 * frontend — import this constant. Prefer the server-sent `initial_balance`
 * over this constant wherever it is available — the constant is a last
 * resort, not a default.
 */

/** Matches trading-engine `paper_initial_balance` (config.py, ADR-029). */
export const PAPER_DEFAULT_BALANCE = 10000

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
