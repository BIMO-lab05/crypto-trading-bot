# Account-size flip: $100 → $10,000 (research scale)

- **Date:** 2026-08-25
- **Status:** approved (operator, 2026-08-25)
- **Branch:** `feature/account-10k`
- **Supersedes:** the $100 campaign's *value* (commit `a690164` et seq.), NOT its architecture. `shared/account.py` remains the declaration of record; the no-literal rule survives unchanged.

## Decisions (operator-locked)

| Question | Decision |
|---|---|
| Purpose | Research scale, paper only. Removes $5 min-notional distortion; lets percent sizing execute at realistic scale. |
| Risk caps | **Keep** `MAX_RISK_PER_TRADE=0.10` (fraction), `MAX_DAILY_LOSS_PCT=12.0`, `MAX_POSITION_SIZE_PCT=10.0`, `ensemble_min_position_pct=0.05`. All percent knobs unchanged — only the dollar base moves. Rationale recorded in ADR-029 (operator choice: aggressive paper sizing), replacing ADR-010's dead min-notional rationale. |
| Paper DB state | Fresh reset: reseed portfolios row + cash ledger at $10,000; archive old trades/positions. Backup first. |
| Deploy timing | Code/tests/backtests immediately (host-side). Service redeploy + DB reset **after the 2026-08-27 isolation-run harvest**. Never bare compose-up mid-window. |

## Non-negotiables preserved

- `LIVE_MAX_RISK_PER_TRADE = 0.02` untouched, not operator-tunable.
- LIVE remains blocked by the four deliberate flags. **The old "LIVE is mechanically impossible at this size" arithmetic backstop disappears at $10,000 (2% = $200 clears every venue floor). Docs must replace the arithmetic argument with the flag gate explicitly.**
- Reject-below-min-notional, never clamp up.
- No account-size literal anywhere; route through `shared/account.py` (host) / `Settings` (container). **A bare `10000` literal is still a defect even though it is now numerically correct** — "accidentally correct" is the primary hazard class of this flip.

## Mechanical consequences at $10,000 (reason from these)

- Per-trade cap 10% = **$1,000**. Ensemble floor 5% = **$500**. Daily breaker 12% = **$1,200** (one full-cap loss ≈ trips it next loss — same coherence ADR-028 blessed; re-affirmed in ADR-029).
- BTC/ETH become tradeable (BTC min ≈ $77 « $1,000). FUNNEL_REPORT's SOL/BNB/ADA-only conclusion is void; re-derive.
- Fees are bps of notional → **edge does not improve with size**. Negative-Sharpe strategies stay negative. The validation battery re-measures honestly; it does not promise profit.
- edge_lab `NOTIONAL_PER_TRADE` pins to equity → $10,000/trade. Bps math scale-free; absolute-USD outputs inflate 100×. Accepted.

## Work plan (commit sequence)

1. **Declaration + enforcement (atomic).** `shared/account.py` DEFAULTS → 10000.0 + docstring; trading-engine `config.py` `paper_initial_balance` default → 10000.0 (keep `ge=100.0` floor) + cap-rationale text; `tests/test_shared_account.py`; `tests/test_account_size_invariant.py` reworked so 100.0 becomes the policed anti-value and the new declared value does NOT excuse bare literals (pattern: `tests/test_phase1_runner_capital.py`); `scripts/check_capital_literals.py` premise inverted. `test_account_config_sync.py` forces this commit to be atomic — by design.
2. **Runtime channels.** Compose unified (`PAPER_INITIAL_BALANCE`, `INITIAL_CAPITAL` hardcoded literals) + headless fallback + k8s configmaps/deployment (+ add missing `INITIAL_CAPITAL` — boot-gap fix); kill the `RISK_BUDGET_INITIAL` parallel channel (`dynamic_risk_budget.py` reads Settings); mirror constants `backtester.py:261`, `kill_switch.py:47`; orchestration `100000.0` defaults (`allocation.py`, `risk_coordinator.py`, `models.py`, `dynamic_budget.py`) → Settings-resolved; risk-metrics `Decimal("100")` ×2; `.env` cleanup (dead `BACKTEST_INITIAL_CAPITAL`); `.env.example` comments; docstring examples de-literalized.
3. **Tests.** Red-fix + semantic rework per inventory: min-notional tightness tests keep a pinned small-balance fixture (coverage must not go vacuous at $10k); ledger/risk-manager/cap-05 arithmetic re-derived from fixtures; env-override tests use sentinel 12345.0; leftover-10000 fixtures routed through config (`conftest.py`, e2e mocks, integration constants).
4. **Frontend.** `utils/balance.js` `PAPER_DEFAULT_BALANCE` → 10000; ~8 comment rewrites (several assert "$10,000 was wrong"); MetricsGrid/MetricsCard dollar thresholds derived as percent-of-balance; DailyPnLChart empty-domain; test fixtures parameterized on the constant.
5. **Docs + ADR-029.** CLAUDE.md §1/§2/§5, `.claude/rules/money.md` + `testing.md` + `docker-env.md`, agents (`capital-auditor`, `quant-skeptic`, `verifier`) inverted to "any literal bypassing declared config is the defect regardless of numeric agreement"; `trading-strategy-dev` SKILL.md; wiki `hot.md`; new `wiki/decisions/ADR-029-account-size-10k-research-scale.md`; supersede notes on ADR-010/015/017/028; FUNNEL_REPORT / FINDINGS / PIPELINE_MAP / FUNNEL_ROOT_CAUSE dollar math; edge-search-v2 spec assumption 4 re-secured by flags; new dated `progress.md` entry voiding $100 feasibility conclusions; `E2E_TESTING_GUIDE.md` example. Archived docs: banner note only.
6. **Validation.** Full suites: root pytest (`--no-cov`), trading-engine (from `services/trading-engine`, `--no-cov`), frontend vitest + build. Backtest battery at $10k, slippage ON: `run_phase1_backtest` (BTC ETH SOL BNB ADA), `run_walk_forward` + ensemble, DSR/CPCV metrics, indicator killtests/replay stack. Results table replaces CLAUDE.md §2 figures, labeled net-of-cost.

## Deploy-day runbook (after 2026-08-27 harvest — NOT before)

1. `pg_dump` backup of postgres app DB.
2. Stop auto-trader (`POST /api/trading/auto/stop`).
3. Archive `trades`/`positions` rows; reseed `portfolios.initial_balance=10000`, cash ledger $10,000.
4. `docker compose -f docker-compose.unified.yml up -d --force-recreate` (new env literals; per-service `--no-deps` where the WSL bind-mount race bites).
5. Verify per CLAUDE.md §7: SELECT pasted, mainnet URL in logs, restart confirmed, frontend shows $10,000.
6. api-gateway in-container test run.

## Out of scope

- Any LIVE-mode change. Any strategy-logic change. XRP/DOGE re-add. RabbitMQ wiring.
- Editing `docs/archive/**` per-file (banner note only).
