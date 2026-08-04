"""AUDIT-01 inventory source. Verbatim claim text for every Validated REQ in scope per CONTEXT D-05.

Each row is a tuple: (req_id, era, source, claim_text).

Claim text MUST be a direct quote from the source document. Where source uses a range bullet
(e.g. RISK-01..07), per-ID claim text is derived by parsing the parenthesized list in the bullet
OR by using the range bullet verbatim for every ID in the range (with a "per range bullet '...'"
annotation in claim_text). When in doubt, prefer the milestone-archive REQUIREMENTS.md text over
PROJECT.md (richer + closer to the originating plan) — per CONTEXT D-05.

Track allocation (per CONTEXT D-06 — sums to 81):
- Track A (17): RISK-01..07 + PREFLIGHT-01..04 + MLGATE-01..03 + OBS-01..02 + CLAUDE-PAPER-CAP-ADR010
- Track B (19): EXEC-03 + ML-01..05 + MLCL-01..04 + TOURN-01..07 + CLAUDE-LSTM-ARCHIVED + CLAUDE-SENTIMENT-REMOVED
- Track C1 (24): EXEC-01,02 + DATA-01,02 + UI-01 + TEST-01 + INFRA-01..06 + DASH-01..06 + DASHLIVE-01..04 + CLAUDE-VALIDATED-SYMBOLS + CLAUDE-EXEC-MAINNET-PRICES
- Track C2 (21): BC-01..07 + MOBILE-01..03 + TOOL-01..03 + LIVECLOSE-01..05 + CIRESTORE-01..03
"""

from __future__ import annotations

# ============================================================
# Era: pre-v1 (PROJECT.md ### Validated > **Pre-v1**)
# Source: .planning/PROJECT.md lines 65-75 (range bullets expanded per CONTEXT D-06)
# ============================================================
PRE_V1_ROWS = [
    ("EXEC-01", "pre-v1", "PROJECT.md", "15-container microservices stack — existing"),
    (
        "EXEC-02",
        "pre-v1",
        "PROJECT.md",
        "Bybit mainnet price feed; paper trading default — existing",
    ),
    (
        "EXEC-03",
        "pre-v1",
        "PROJECT.md",
        "9-indicator voting aggregator with TREND_FILTER + VOLUME_CONFIRMATION — existing",
    ),
    (
        "RISK-01",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: daily-loss (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30')",
    ),
    (
        "RISK-02",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: drawdown (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30')",
    ),
    (
        "RISK-03",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: consec-loss (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30')",
    ),
    (
        "RISK-04",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: per-trade (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30'). Per ADR-010: 2% in LIVE; 10% in paper.",
    ),
    (
        "RISK-05",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: vol parity (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30')",
    ),
    (
        "RISK-06",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: maker/post-only (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30')",
    ),
    (
        "RISK-07",
        "pre-v1",
        "PROJECT.md",
        "Risk cap: funding (per range bullet 'RISK-01..07: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30')",
    ),
    (
        "ML-01",
        "pre-v1",
        "PROJECT.md",
        "Honest returns metrics (per range bullet 'ML-01..05: Honest returns metrics; PSR/DSR; CPCV; live-reload; ML disabled by default until DSR>0.95 — 2026-04-30/05-01')",
    ),
    (
        "ML-02",
        "pre-v1",
        "PROJECT.md",
        "PSR/DSR computation (per range bullet 'ML-01..05: Honest returns metrics; PSR/DSR; CPCV; live-reload; ML disabled by default until DSR>0.95 — 2026-04-30/05-01')",
    ),
    (
        "ML-03",
        "pre-v1",
        "PROJECT.md",
        "CPCV (combinatorial purged cross-validation) (per range bullet 'ML-01..05: Honest returns metrics; PSR/DSR; CPCV; live-reload; ML disabled by default until DSR>0.95 — 2026-04-30/05-01')",
    ),
    (
        "ML-04",
        "pre-v1",
        "PROJECT.md",
        "Live-reload of model artifacts (per range bullet 'ML-01..05: Honest returns metrics; PSR/DSR; CPCV; live-reload; ML disabled by default until DSR>0.95 — 2026-04-30/05-01')",
    ),
    (
        "ML-05",
        "pre-v1",
        "PROJECT.md",
        "ML disabled by default until DSR>0.95 (per range bullet 'ML-01..05: Honest returns metrics; PSR/DSR; CPCV; live-reload; ML disabled by default until DSR>0.95 — 2026-04-30/05-01')",
    ),
    (
        "DATA-01",
        "pre-v1",
        "PROJECT.md",
        "`is_mainnet` column on klines/tickers (per bullet 'DATA-01, DATA-02: `is_mainnet` column + backtest filter; confidence sentinel chain cleaned — 2026-04 commits')",
    ),
    (
        "DATA-02",
        "pre-v1",
        "PROJECT.md",
        "Backtest filter on is_mainnet to avoid testnet-flip contamination (per bullet 'DATA-01, DATA-02: `is_mainnet` column + backtest filter; confidence sentinel chain cleaned — 2026-04 commits')",
    ),
    (
        "OBS-01",
        "pre-v1",
        "PROJECT.md",
        "Telegram redaction (per bullet 'OBS-01, OBS-02: Telegram redaction; honest sentiment 501/503 (not fabricated) — 2026-04 commits')",
    ),
    (
        "OBS-02",
        "pre-v1",
        "PROJECT.md",
        "Honest sentiment 501/503 (not fabricated) (per bullet 'OBS-01, OBS-02: Telegram redaction; honest sentiment 501/503 (not fabricated) — 2026-04 commits')",
    ),
    (
        "UI-01",
        "pre-v1",
        "PROJECT.md",
        "React dashboard with REST-polling (dead WS scaffolding stripped)",
    ),
    ("TEST-01", "pre-v1", "PROJECT.md", "~101 Tier-1 tests green"),
]

# ============================================================
# Era: v1.0 (.planning/milestones/v1.0-REQUIREMENTS.md, richer than PROJECT.md per D-05)
# Subtotal: 23 rows (INFRA-01..06 + TOURN-01..07 + MLCL-01..04 + DASH-01..06)
# ============================================================
V1_0_ROWS = [
    # Infra (test-driven rebuild)
    (
        "INFRA-01",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "pytest+testcontainers integration suite asserts full stack health from a fresh `git clone` into a tmp directory: services healthy, real exchange prices via recorded tape, ML models loaded if `ENABLE_ML_PREDICTIONS=true`, notifications delivered, paper trade end-to-end <60s",
    ),
    (
        "INFRA-02",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "`bootstrap.sh` provisions `.env` from a template, brings up the docker-compose stack, and idles waiting for the integration suite — no destructive `git clean -fdx` against the working tree. (DB migrations deferred to Phase 2 per Phase 1 CONTEXT.md `<deferred>`: compose-managed init scripts cover v1; revisit if Phase 2 integration suite hits schema drift.)",
    ),
    (
        "INFRA-03",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Recorded-tape exchange data fixtures + replay loader for deterministic test runs; one nightly live smoke test allowed to be flaky",
    ),
    (
        "INFRA-04",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        'Checkpointed iteration harness — fix one bug, run tests, present diff for review before next fix; no unattended "iterate until 3 green runs" loop',
    ),
    (
        "INFRA-05",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "RUNBOOK.md documents the WSL2 BuildKit hang (`DOCKER_BUILDKIT=0` workaround), docker context misconfig recovery, stale-model restart procedure, and bootstrap-test failure triage",
    ),
    (
        "INFRA-06",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Pre-existing concrete bugs investigated and either fixed or documented as out-of-scope: stale in-memory ML model needing service restart, hardcoded `confidence=0` paths still emitting signals, WSL2 BuildKit env workaround",
    ),
    # Tournament (ML evaluation harness)
    (
        "TOURN-01",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Docker+SQLite tournament orchestrator (Python or Bash, NOT LLM subagents) launches per-experiment containers with isolated memory and disk, captures train/eval logs, persists results to a shared SQLite leaderboard",
    ),
    (
        "TOURN-02",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Tournament leaderboard schema indexed by (architecture, symbol, horizon, target_mode, hyperparameters_hash, run_id) with columns for `r2_returns`, `dir_acc_corrected`, `oos_sharpe`, `psr`, `dsr`, `cpcv_dsr`, `train_seconds`, `git_sha`",
    ),
    (
        "TOURN-03",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Search-space config covering GRU/LSTM/Transformer/TCN × {SOL, BNB, ADA} × hyperparameter grid (units, depth, dropout, lr, batch, lookback, horizon, target_mode); deterministic seeds; explicit XRP/AVAX opt-in only when validation layer permits",
    ),
    (
        "TOURN-04",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Per-experiment early stopping based on validation `r2_returns` and `dir_acc_corrected`; persist failed runs to leaderboard with failure reason instead of dropping them",
    ),
    (
        "TOURN-05",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        'Top-3 ensemble construction (rank by DSR on OOS) with bootstrap significance test vs current production baseline (`ENABLE_ML_PREDICTIONS=false` baseline = persistence) on OOS Sharpe and corrected Dir.Acc, p<0.05 — drops the impossible "5% R²" criterion',
    ),
    (
        "TOURN-06",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Auto-open draft PR via `gh` CLI containing leaderboard markdown, ensemble config, significance test results, and a link to reproducer when ensemble wins; humans merge — no auto-merge",
    ),
    (
        "TOURN-07",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        'Tournament reuses existing `returns_metrics.py`, `sharpe_metrics.py`, `cpcv.py`; no parallel "alternative metrics" code path',
    ),
    # ML cleanup (post-V0)
    (
        "MLCL-01",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Forward-paper-test harness for the three Tier-1 opt-in features (vol parity, maker, funding) — runs each in isolation for ≥7 days against the baseline, compares PSR with bootstrap CI; per-feature default-on flip blocked until evidence",
    ),
    (
        "MLCL-02",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        'T0.1.x next-attempt experiment chosen and shipped through the tournament harness — picks one of {different horizon, classification head, XGBoost control, cross-sectional features, sentiment-as-filter}; result is allowed to be "no edge" and that\'s a valid outcome',
    ),
    (
        "MLCL-03",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "`scripts/monitoring/*` parked autonomous tier-2 system either removed or wired with a documented blast-radius bound (no `claude -p` PR-opening from CI without human review); decision committed",
    ),
    (
        "MLCL-04",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Backtest signal logic alignment — either rewrite `run_extended_backtest.py` to use live `CoreAggregator` (high-effort) or document the divergence permanently and freeze backtest claims; no silent drift",
    ),
    # Dashboard
    (
        "DASH-01",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        'End-to-end audit of every dashboard tile/route — for each, identify the backing endpoint, verify it returns the expected shape against a running stack, and either fix or label "stale"',
    ),
    (
        "DASH-02",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Hardcoded URLs replaced with config-driven values; gateway-mediated paths (auth, rate limit, validation) versus direct-service paths documented inline in `vite.config.js` and the relevant API client modules",
    ),
    (
        "DASH-03",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Safety-state header — prominent display of TRADING_MODE (PAPER/LIVE), `auto_trading_enabled`, kill-switch state, EMERGENCY_STOP file presence, and `ENABLE_ML_PREDICTIONS` so the operator sees current safety posture at a glance",
    ),
    (
        "DASH-04",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Tournament view — table of leaderboard rows from `TOURN-02`, filterable by symbol/architecture, with significance markers; depends on TOURN-02",
    ),
    (
        "DASH-05",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        'Empty/error states — every tile renders an explicit "no data" or "endpoint failed" message instead of silently showing empty arrays or stale numbers',
    ),
    (
        "DASH-06",
        "v1.0",
        "v1.0-REQUIREMENTS.md",
        "Smoke test for the dashboard — Playwright or equivalent that boots the stack, opens the dashboard, asserts each major tile renders non-empty against the recorded-tape stack from `INFRA-03`",
    ),
]

# ============================================================
# Era: v1.1 (.planning/milestones/v1.1-REQUIREMENTS.md)
# Subtotal: 19 rows (PREFLIGHT-01..04 + MLGATE-01..03 + DASHLIVE-01..04 + CIRESTORE-01..03 + LIVECLOSE-01..05)
# ============================================================
V1_1_ROWS = [
    # LIVECLOSE — Close v1.0 operator-blocked carry-ins
    (
        "LIVECLOSE-01",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "Operator executes INFRA-02 fresh-clone bootstrap checkpoint — runs `bash bootstrap.sh` against a fresh `git clone` into a tmp directory **twice**, captures `BYBIT_PRICE_SOURCE: mode=tape` log line + 15-service health snapshot per run, and commits the evidence under `.planning/evidence/LIVECLOSE-01/`. Harness: `scripts/closure/liveclose-01-fresh-clone.sh` (Phase 11.1-02).",
    ),
    (
        "LIVECLOSE-02",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "INFRA-01 live-stack ML-on nightly variant produces its first green CI run on GitHub Actions (after OP-04 billing recovery); CI URL + green-badge evidence linked in OP-04 close note. Harness: `scripts/closure/liveclose-02-record-ci.sh` (Phase 11.1-03). Wall-clock additionally blocked on OP-04.",
    ),
    (
        "LIVECLOSE-03",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "MLCL-01 forward-paper-test apparatus accrues ≥7 consecutive trading days of evidence with PSR-CI published per feature; evidence row visible in `leaderboard` table with `psr_ci_published=true`. Harness: `scripts/closure/liveclose-03-psr-evidence.py` (Phase 11.1-04). Wall-clock additionally bound to ≥7 trading days of accrual.",
    ),
    (
        "LIVECLOSE-04",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "MLCL-02 T0.1.x `different_horizon` sweep re-runs after OP-02 (migration 005) + OP-03 (reader password); verdict transitions from `INSUFFICIENT_DATA` to `PASS` or `FAIL` with bootstrap p-value persisted. Harness: `scripts/closure/liveclose-04-sweep-verdict.py` (Phase 11.1-05). Wall-clock additionally blocked on OP-02 + OP-03.",
    ),
    (
        "LIVECLOSE-05",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "DASH-03 LIVE-flip manual smoke — operator force-recreates api-gateway with `TRADING_MODE=LIVE`, captures screenshot showing rose viewport outline + red MODE pill + KILL-SWITCH state, reverts, and commits screenshot under `.planning/evidence/LIVECLOSE-05/`. Harness: `scripts/closure/liveclose-05-live-flip-smoke.sh` + `docs/runbooks/LIVECLOSE-05.md` (Phase 11.1-06). Supervised-run-only by design (orchestrator refuses `--exec`).",
    ),
    # PREFLIGHT — Code-enforced LIVE preconditions
    (
        "PREFLIGHT-01",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "`scripts/preflight_live.py` CLI asserts all 6 LIVE preconditions and exits non-zero on any miss — (1) per-trade risk cap ≤2%, (2) `PAPER_TRADING_MODE=false`, (3) `TRADING_MODE=LIVE`, (4) `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, (5) `EMERGENCY_STOP` file absent, (6) DSR>0.95 evidence-row exists in `leaderboard` if `ENABLE_ML_PREDICTIONS=true`. Output is structured JSON per check.",
    ),
    (
        "PREFLIGHT-02",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "trading-engine boot path enforces per-trade cap mode at startup — refuses to boot in `TRADING_MODE=LIVE` with `MAX_POSITION_RISK_PCT > 2`; logs explicit `LIVE_PREFLIGHT_REJECTED reason=cap_too_high` and exits. Unit test asserts both directions (PAPER allows 10%, LIVE rejects 3%).",
    ),
    (
        "PREFLIGHT-03",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "CI workflow `preflight-live-readiness.yml` runs `preflight_live.py --dry-run --target=HEAD` and blocks any PR labeled `live: requested` that fails any check; result posted as PR check status.",
    ),
    (
        "PREFLIGHT-04",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "Pre-LIVE operator checklist added to `RUNBOOK.md` (Diagnose/Action/Verification per precondition) and cross-linked from PROJECT.md's Out of Scope LIVE-default note.",
    ),
    # MLGATE — Operator-driven ML re-enablement evidence loop
    (
        "MLGATE-01",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "`scripts/forward_paper_test/run_evidence_loop.py` driver loops ≥7-day evidence accrual + per-feature PSR-CI publish; idempotent across restart; resumes from last persisted row. Migration `0002_mlgate_evidence_columns.sql` adds `run_date` + `psr_ci_published` to `leaderboard`.",
    ),
    (
        "MLGATE-02",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "`services/trading-engine` startup auto-flips `ENABLE_ML_PREDICTIONS=true` only if a DSR>0.95 evidence row exists in `leaderboard` within the last 14 days; reverts to `false` on DSR drop or stale row; emits `MLGATE_AUTO_FLIP direction=X reason=Y` log + `/run/mlgate_auto_flip.json` schema_version=1 marker; CI grep gate enforces.",
    ),
    (
        "MLGATE-03",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        'Every "ml predictions disabled" event in trading-engine logs a structured reason from a fixed enum: `no_evidence | dsr_below_gate | evidence_stale | regime_shift | manual_override`; unauth read-only `/api/preflight/ml-gate-reason-counts`; notification-service scheduled Telegram digest of reason counts; CI grep gate enforced.',
    ),
    # DASHLIVE — Path-to-LIVE dashboard tile
    (
        "DASHLIVE-01",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "`PathToLiveTile.jsx` renders PASS/FAIL/UNKNOWN status of every PREFLIGHT-01 check on a 5-second poll against `GET /api/preflight/live-readiness`.",
    ),
    (
        "DASHLIVE-02",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "Same tile shows OP-* carry-in close states (OP-01..04 + INFRA-02 checkpoint) sourced from `GET /api/preflight/carry-ins` — file-backed (`.planning/state/carry_ins.json`).",
    ),
    (
        "DASHLIVE-03",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        'Tile renders "DO NOT FLIP" (red) until **all** PREFLIGHT checks PASS for ≥24h continuous; "READY" (green) only after the 24h continuous-PASS window holds; partial transitions render "ALMOST" (amber) with count.',
    ),
    (
        "DASHLIVE-04",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "Playwright smoke `tests/e2e/test_path_to_live_smoke.py` validates the tile renders correctly in PAPER mode and that DSR evidence-row shape is asserted; runs in `dashboard-smoke.yml` CI.",
    ),
    # CIRESTORE — Post-OP-04 CI recovery
    (
        "CIRESTORE-01",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "Operator confirms GH Actions billing resolved (OP-04 close); close-note committed under `.planning/evidence/OP-04/` with billing-page screenshot timestamp.",
    ),
    (
        "CIRESTORE-02",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "First green CI run of (a) `integration-ml-on.yml` nightly variant, (b) `tournament-harness.yml`, (c) `dashboard-smoke.yml` — three CI run URLs linked in OP-04 close note.",
    ),
    (
        "CIRESTORE-03",
        "v1.1",
        "v1.1-REQUIREMENTS.md",
        "`billing-failure-detector.yml` workflow runs every 6h via `gh run list --status failure --limit 5` filtering for `billing` substring; on detection, posts to Telegram and creates a GitHub Issue with the `ops: billing` label. Self-trigger-safe (jq filter excludes own workflow name).",
    ),
]

# ============================================================
# Era: v1.2 (.planning/milestones/v1.2-REQUIREMENTS.md)
# Subtotal: 13 rows (BC-01..07 + MOBILE-01..03 + TOOL-01..03)
# ============================================================
V1_2_ROWS = [
    # Bybit-Connector Market-Data Centralization (BC)
    (
        "BC-01",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "Repo-wide audit produces `.planning/evidence/BC-01/bybit-bypass-audit.json` enumerating every Python file outside `services/bybit-connector/` that matches any of: `from pybit`, `import pybit`, hardcoded `https://api.bybit.com`, hardcoded `https://api-testnet.bybit.com`, hardcoded `wss://stream.bybit`. Each entry is `{file, line, kind, current_call, replacement_path}` where `kind ∈ {pybit_import, mainnet_rest_url, testnet_rest_url, wss_stream_url}`. Audit covers `services/`, `scripts/`, `backtesting/`, `tests/`, `infrastructure/scripts/`. Non-Python files (helm YAML, network policies, markdown docs) are EXCLUDED.",
    ),
    (
        "BC-02",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "Every BC-01 hit is refactored to consume `bybit-connector` REST surface (`http://bybit-connector:8001/api/v1/market/{ticker,kline,orderbook,recent-trade,funding-rate/history,instruments-info}` for market-data; `http://bybit-connector:8001/api/v1/account/balance` for `infrastructure/scripts/rotate_secrets.py` auth-ping). Implementation mirrors `services/market-data-service/app/fetcher.py` (httpx + `bybit_connector_retry` tenacity decorator). Standalone scripts (`scripts/collect_*.py`, `scripts/fetch_*.py`, `backtesting/bybit_data_fetcher.py`) fail-fast with `BYBIT_CONNECTOR_URL` unreachable error pointing operator at `docker compose up bybit-connector`. No `--direct-bybit` escape hatch.",
    ),
    (
        "BC-03",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "CI grep gate `tests/ci/test_no_bybit_bypass.py` (Python pytest) is green on `main` post-refactor and fails on any new violation in `**/*.py` outside `services/bybit-connector/`. Patterns banned: `from pybit`, `import pybit`, `https?://api\\.bybit\\.com`, `https?://api-testnet\\.bybit\\.com`, `wss?://stream\\.bybit`. Test is required in `.github/workflows/` (CI workflow PR check). No allowlist entries permitted after refactor.",
    ),
    (
        "BC-04",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        '`services/trading-engine/app/exchanges/binance.py` and references are archived per operator policy ("Bybit-only"). File moves to `_archive_exchanges/binance.py`. `services/trading-engine/app/exchanges/factory.py` BinanceExchangeAdapter import + registration removed (lines 62, 189). `services/trading-engine/app/exchanges/__init__.py` Binance exports removed (lines 23, 213, 329, 330, 513). `services/trading-engine/tests/test_multi_exchange.py` Binance test branches deleted (lines 54, 161, 165). Trading-engine boots without ImportError; multi-exchange test file either deleted or down to Bybit-only branches.',
    ),
    (
        "BC-05",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        '`services/market-data-service/app/config.py:58` default port fixed: `bybit_connector_url: str = Field(default="http://localhost:8001")` (was `:8002`). Compose-env behavior unchanged (env overrides default); fix prevents misroute when scripts read config without compose env.',
    ),
    (
        "BC-06",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        '`RUNBOOK.md` gains Symptom #N "Market-data stale or missing — bybit-connector chain broken" with Diagnose/Action/Verification subsections covering: (a) bybit-connector container down, (b) `BYBIT_CONNECTOR_URL` env misconfigured, (c) bybit-connector hitting Bybit-side ratelimit, (d) `MARKET_DATA_SOURCE=tape` accidentally enabled in production. Verification steps reference concrete curl commands against `http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT`.',
    ),
    (
        "BC-07",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "Tape-replay mode preserved end-to-end. Integration test (`tests/integration/test_bybit_connector_tape_preserved.py`) asserts that with `MARKET_DATA_SOURCE=tape` enabled on `crypto-bot-bybit-connector`, every refactored consumer (ml-prediction-service orderbook handler, market-data-service fetcher, refactored scripts) receives tape data — never live. `POST /admin/tape/reset` continues to work post-refactor.",
    ),
    # Mobile Responsive (MOBILE)
    (
        "MOBILE-01",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "Viewport meta tag + responsive Tailwind tokens established (breakpoints `sm:640`, `md:768`, `lg:1024`, `xl:1280` standardized; `tailwind.config.cjs` audited for hardcoded widths). Layout audit (`scripts/audit_responsive.py` or inline grep) of every `frontend/src/components/**/*.jsx` identifies fixed-width violations; `responsive-audit.json` artifact lists each violation with file:line.",
    ),
    (
        "MOBILE-02",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "Single-column reflow ≤768px implemented for: `Dashboard.jsx` grid (collapses to stacked tiles), `PathToLiveTile.jsx` (6 PREFLIGHT chip rows + 5 carry-in rows wrap to 1-col), `KeyMetricsStrip` (horizontal scroll → 2-col grid), `TournamentDashboard.jsx` (filter chips wrap, table converts to card list). No tile loses information; only layout changes.",
    ),
    (
        "MOBILE-03",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "pytest-playwright Chromium smoke at iPhone SE (375×667) and iPad portrait (768×1024) viewports asserts: every dashboard tile rendered with `data-testid` visible without horizontal scroll, no element overflows `window.innerWidth`, PathToLiveTile banner state-token still visible, navigation tappable (≥44px touch targets per WCAG). Runs under `.github/workflows/dashboard-smoke.yml` matrix.",
    ),
    # Planning Tooling (TOOL)
    (
        "TOOL-01",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "`gsd-sdk query plan.validate <plan-path>` rejects one-liner content matching `/^Rule \\d/`, `/^Task \\d/`, `/^one-liner:\\s*$/`, `/<one-line summary>/`, or empty string. Pre-commit hook (or PR-time CI step) runs validator on every `*-PLAN.md` modified in diff; commit/CI fails with explicit error pointing at the bad line. Unit tests cover all 5 rejection patterns + 1 happy path.",
    ),
    (
        "TOOL-02",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "`gsd-sdk query roadmap.analyze` detects umbrella→decimal supersession: if Phase N.M's requirement set ⊇ Phase N's requirement set and Phase N.M is complete, ROADMAP.md auto-updates Phase N row to `Superseded by N.M` (status `[⊘]`). Idempotent. Output diff goes to stdout so the operator can review before commit. Wired into `/gsd-complete-milestone` workflow.",
    ),
    (
        "TOOL-03",
        "v1.2",
        "v1.2-REQUIREMENTS.md",
        "`/gsd-complete-milestone` workflow refuses to archive if the latest `v[X.Y]-MILESTONE-AUDIT.md` `audited_at` timestamp predates the most recent phase's `VERIFICATION.md` modification time by >1h. Error names the stale audit timestamp and the offending phase. Override flag `--accept-stale-audit` for emergency closes (documented). Test fixture replays the v1.1 13h-gap scenario and asserts refusal.",
    ),
]

# ============================================================
# Era: pre-v1 (synthetic CLAUDE-* IDs per CONTEXT D-04)
# Subtotal: 5 rows
# ============================================================
CLAUDE_ROWS = [
    (
        "CLAUDE-LSTM-ARCHIVED",
        "pre-v1",
        "CLAUDE.md",
        "LSTM deleted May 2026 (archived under `_archive_lstm/`) (CLAUDE.md ## Stack section)",
    ),
    (
        "CLAUDE-SENTIMENT-REMOVED",
        "pre-v1",
        "CLAUDE.md",
        "Sentiment leg removed from signal pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`); sentiment-analysis-service still runs in compose but idle (CLAUDE.md ## Project rules, 2026-05 feature-flags)",
    ),
    (
        "CLAUDE-VALIDATED-SYMBOLS",
        "pre-v1",
        "CLAUDE.md",
        "Validated symbols: BTC, ETH, SOL, BNB, ADA (5 active as of 2026-05-03). XRP / DOGE excluded by paper-trading data — no silent re-add (CLAUDE.md ## Project rules)",
    ),
    (
        "CLAUDE-PAPER-CAP-ADR010",
        "pre-v1",
        "CLAUDE.md",
        "Paper mode currently relaxed to 10% per ADR-010 (filed 2026-05-06) to clear Bybit min-notional on $100 balance. Pre-live checklist must restore <= 2% before flipping TRADING_MODE=LIVE (CLAUDE.md ## Project rules)",
    ),
    (
        "CLAUDE-EXEC-MAINNET-PRICES",
        "pre-v1",
        "CLAUDE.md",
        "Market data feed from Bybit mainnet (BYBIT_TESTNET=false) for real prices; orders simulated internally via PAPER_TRADING_MODE=true (CLAUDE.md top + ## Project rules)",
    ),
]


def all_rows():
    return PRE_V1_ROWS + V1_0_ROWS + V1_1_ROWS + V1_2_ROWS + CLAUDE_ROWS
