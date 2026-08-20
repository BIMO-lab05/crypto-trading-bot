# Wait-Window Streams (Evidence + Debt) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute Streams 0–2 of the wait-window spec (`docs/superpowers/specs/2026-08-20-wait-window-work-plan-design.md`): forward-paper evidence plumbing repair + accrual start, debt bounded-smalls batch, debt mediums. Phase 19 is NOT in this plan — it runs through GSD `/gsd:plan-phase` afterwards.

**Architecture:** Independent surgical fixes, one commit each. Evidence stream wires two existing consumers (`run_evidence_loop.py`, preflight `check_dsr_evidence`) to the tournament-harness's real sqlite file via one env var, adds a cron-driven daily tick with a staleness tripwire, fixes the broken isolation-run launcher, and implements the missing `complete-run` step that produces `run.json`. Debt stream is test repairs + config + script surgery.

**Tech Stack:** Python 3.12, pytest, pandas 3, asyncpg, sqlite3, docker compose, TimescaleDB/PostgreSQL, cron (WSL).

## Global Constraints

- **The account is $100.** Never write an account-size literal; host-run code imports `shared.account` (`ACCOUNT_EQUITY_USD`), services read their own `Settings`. Never hardcode a 10000 balance in fixtures.
- **No gate weakening**: DSR 0.95 floor, PSR-CI ≥30 observations, `psr_ci_low > 0` publish gate, 7-day accrual window — all untouchable. Costs only go up.
- **LIVE stays fenced**: nothing here touches live-enablement config, the 2% LIVE cap, or kill-switch semantics. `run_evidence_loop`/`run_isolation` LIVE-refusal guards must survive every edit.
- **Test invocations**: trading-engine host runs MUST be from `services/trading-engine/` with `--no-cov` (conftest pins `env_file=None`; do NOT export settings env vars — pydantic-settings deep-merges Dict fields). TA runs from `services/technical-analysis/` with `--no-cov`. api-gateway tests run in-container. Repo-root `pytest.ini` injects `--cov`; always `--no-cov` on targeted runs.
- **Git**: never `git add -A` or bare `git status` (NTFS/WSL, >60s) — enumerate paths; commit with explicit pathspecs (`git commit -m "..." -- <paths>`). Branch for this plan: `fix/wait-window-streams` off `feature/edge-search-v2`.
- **Format hook**: `.claude/scripts/format-python.sh` runs ruff on every Edit/Write of `*.py`. Task 1 fixes its line-length; until Task 1 is merged, check `git diff` after any Python edit for unrelated churn (cosmetic reflow, stripped imports) and revert churn before committing.
- **Never mark failing tests xfail/skip** without a tracking requirement ID.
- Timestamps in this plan: clean-data epoch is `2026-08-12T13:47:20Z` (exact, load-bearing).

---

## Stream A — debt bounded-smalls

### Task 1: ruff config — kill the 88-column format-hook churn (RES-11)

**Files:**
- Modify: `pyproject.toml` (add `[tool.ruff]` after `[tool.black]` block, ~line 33)

**Interfaces:**
- Produces: repo-wide ruff config honored by `.claude/scripts/format-python.sh` (which invokes `ruff format` / `ruff check --fix` with no explicit config — ruff discovers `pyproject.toml` from the file's directory upward).

**Why first:** every later task edits Python files; the hook currently reformats them at ruff's default 88 columns against the repo's 100 (black/isort both set 100). No test cycle — config-only; verification is behavioral.

- [ ] **Step 1: Add the section**

Insert into `pyproject.toml` immediately after the `[tool.black]` exclude block:

```toml
[tool.ruff]
# Must agree with [tool.black] line-length and [tool.isort] line_length above.
# The PostToolUse format hook (.claude/scripts/format-python.sh) runs ruff with
# no explicit config; without this section ruff falls back to its 88-column
# default and reflows every edited file against the repo's 100-column standard.
line-length = 100
target-version = "py312"
```

- [ ] **Step 2: Verify ruff picks it up**

Run: `~/.local/bin/ruff check --show-settings scripts/check_collection_gaps.py 2>/dev/null | grep -i "line.length" | head -3`
Expected: `line_length = 100` (not 88). If `--show-settings` output format differs, alternative proof: create a scratch file with a 95-column line, run `~/.local/bin/ruff format <file>`, confirm the line is NOT wrapped.

- [ ] **Step 3: Verify no repo-wide reformat ambush**

Run: `~/.local/bin/ruff format --check --quiet services/trading-engine/app/config.py scripts/validate_risk_limits.py; echo "exit=$?"`
Expected: note the result either way — this tells you whether later hook-triggered formats will churn those files. Record it in the commit message if nonzero.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "fix(tooling): pin ruff line-length 100 to match black/isort (RES-11)" -- pyproject.toml
```

### Task 2: pairs-trading pandas `freq='H'` — fix all 6 sites

**Files:**
- Modify: `services/trading-engine/tests/strategies/test_pairs_trading.py:43,142`
- Modify: `services/trading-engine/app/utils/statistical/tests/test_cointegration.py:53,63,80,103`

**Interfaces:** none — test-only fixture helpers.

RED already exists: pandas 3.0.2 removed `freq='H'`; 11 tests in `test_pairs_trading.py` fail at collection/setup with `ValueError`.

- [ ] **Step 1: Confirm the failure (RED)**

Run: `cd services/trading-engine && python3 -m pytest tests/strategies/test_pairs_trading.py --no-cov -x -q 2>&1 | tail -5`
Expected: `ValueError` mentioning invalid frequency `'H'`.

- [ ] **Step 2: Fix all 6 sites**

In both files, every occurrence is inside `pd.date_range('2025-01-01', periods=..., freq='H')`. Change `freq='H'` → `freq='h'`:
- `tests/strategies/test_pairs_trading.py` line 43 (in `generate_cointegrated_pair`) and line 142 (in `test_calibrate_non_cointegrated_pair`).
- `app/utils/statistical/tests/test_cointegration.py` lines 53, 63, 80, 103 (in `generate_stationary_series`, `generate_nonstationary_series`, `generate_cointegrated_pair`, `generate_non_cointegrated_pair`). These 4 are latent (root `pytest.ini` testpaths never collects them) — fix anyway, same defect class.

- [ ] **Step 3: Verify GREEN**

Run: `cd services/trading-engine && python3 -m pytest tests/strategies/test_pairs_trading.py --no-cov -q 2>&1 | tail -3`
Expected: all pass (was 11 failures).
Also run the latent file directly: `cd services/trading-engine && python3 -m pytest app/utils/statistical/tests/test_cointegration.py --no-cov -q 2>&1 | tail -3`
Expected: pass (or collection succeeds — if these tests have their own pre-existing failures unrelated to freq, record them, do not chase).

- [ ] **Step 4: Commit**

```bash
git add services/trading-engine/tests/strategies/test_pairs_trading.py services/trading-engine/app/utils/statistical/tests/test_cointegration.py
git commit -m "fix(trading-engine): pandas 3 freq='H'->'h' in test fixtures (6 sites, 11 red tests)" -- services/trading-engine/tests/strategies/test_pairs_trading.py services/trading-engine/app/utils/statistical/tests/test_cointegration.py
```

### Task 3: connector-envelope tests — repair stale mocks

**Files:**
- Modify: `services/trading-engine/tests/integration/test_connector_contract.py:201-281` (class `TestLiveTradingResponseEnvelope`, both tests)

**Interfaces:**
- Consumes (production reality, do NOT change production): `app/live_trading.py:156-171` — `execute_market_order` calls `self.position_manager.get_open_positions()` (sync), `await self.get_balance()` (which awaits `self.client.get(...)` then `.raise_for_status()`/`.json()`), then unpacks `allowed, reason = self.risk_manager.check_position_limits(open_positions, balance_for_check)`.

The tests mock `risk_manager.can_open_position` — a method the flow no longer calls — so `check_position_limits` returns a bare `MagicMock` whose 2-tuple unpack raises `ValueError`.

- [ ] **Step 1: Confirm the failure (RED)**

Run: `cd services/trading-engine && python3 -m pytest tests/integration/test_connector_contract.py::TestLiveTradingResponseEnvelope --no-cov -q 2>&1 | tail -5`
Expected: 2 failures.

- [ ] **Step 2: Fix the mocks in BOTH tests**

Preserve the existing pattern (`LiveTradingEngine.__new__` to bypass the fenced `__init__`, lazy imports, `MagicMock`/`AsyncMock` already imported at file top). In each test, replace the stale block

```python
        engine.risk_manager = MagicMock()
        engine.risk_manager.can_open_position.return_value = True
```

with (test #1 — keep its `calculate_stop_loss`/`calculate_take_profit` lines below it):

```python
        engine.risk_manager = MagicMock()
        engine.risk_manager.check_position_limits.return_value = (True, None)
        engine.position_manager = MagicMock()
        engine.position_manager.get_open_positions.return_value = []
        # get_balance awaits self.client.get(...); stub it directly so the
        # balance fetch never touches the (sync) MagicMock client.
        engine.get_balance = AsyncMock(return_value=Decimal("100"))
```

Notes: test #1 already sets `engine.position_manager` afterwards for `create_position` — merge, don't duplicate (keep `create_position.return_value = MagicMock(id=uuid4())` on the same `position_manager` mock). Test #2 gets the identical block. `Decimal` is already imported in the file (used for order quantity).

- [ ] **Step 3: Verify GREEN**

Run: `cd services/trading-engine && python3 -m pytest tests/integration/test_connector_contract.py --no-cov -q 2>&1 | tail -3`
Expected: whole file passes.

- [ ] **Step 4: Full-suite sanity (the point of this stream)**

Run: `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q 2>&1 | tail -3`
Expected: **0 failures** (was 13: 11 pairs + 2 envelope). If anything else is red, STOP and report — do not fix unrelated failures in this task.

- [ ] **Step 5: Commit**

```bash
git add services/trading-engine/tests/integration/test_connector_contract.py
git commit -m "fix(trading-engine): repair stale LiveTrading envelope mocks (check_position_limits tuple, async get_balance)" -- services/trading-engine/tests/integration/test_connector_contract.py
```

### Task 4: TA `test_comprehensive_80.py` — align with fail-loud fetcher

**Files:**
- Modify: `services/technical-analysis/tests/test_comprehensive_80.py:227-287` (two tests in `TestMarketDataFetcherDataFrame`)

**Interfaces:**
- Consumes (production reality, do NOT change production): `app/fetcher.py` — `get_klines_as_dataframe` raises `ValueError` on empty klines AND on `< MIN_VALID_ROWS` (30) valid candles; success returns a DataFrame with a `DatetimeIndex` named `datetime`.

- [ ] **Step 1: Confirm the failures (RED)**

Run: `cd services/technical-analysis && python3 -m pytest tests/test_comprehensive_80.py::TestMarketDataFetcherDataFrame --no-cov -q 2>&1 | tail -5`
Expected: 2 failures, both `ValueError` from the fetcher.

- [ ] **Step 2: Rewrite `test_get_klines_as_dataframe_success` to supply 35 candles**

Replace the single-candle `mock_data` with a generator of 35 valid, safely-past candles (Nov 2023 base, hourly spacing — the still-forming-candle drop can't fire):

```python
        mock_data = {
            "success": True,
            "data": [
                {
                    "timestamp": 1700000000000 + i * 3600_000,
                    "open": "30000.0",
                    "high": "30500.0",
                    "low": "29800.0",
                    "close": "30200.0",
                    "volume": "100.5",
                }
                for i in range(35)
            ],
        }
```

Keep the existing mock style (`patch.object(fetcher.client, 'get')` with a sync `Mock` response). Update assertions: `assert len(df) == 35`; keep the column and `pd.DatetimeIndex` assertions unchanged.

- [ ] **Step 3: Rewrite `test_get_klines_as_dataframe_empty` to expect the raise**

```python
    @pytest.mark.asyncio
    async def test_get_klines_as_dataframe_empty(self):
        """Empty kline data must raise, not return an empty frame (fail-loud fetcher)."""
        fetcher = MarketDataFetcher()

        mock_data = {"success": True, "data": []}

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            with pytest.raises(ValueError, match="No kline data available"):
                await fetcher.get_klines_as_dataframe("BTCUSDT", "60", 200)

        await fetcher.close()
```

(`pytest` is already imported in the file; verify, add if not.)

- [ ] **Step 4: Verify GREEN**

Run: `cd services/technical-analysis && python3 -m pytest tests/test_comprehensive_80.py --no-cov -q 2>&1 | tail -3`
Expected: file passes (the 2 known-red gone, nothing else broken).

- [ ] **Step 5: Commit**

```bash
git add services/technical-analysis/tests/test_comprehensive_80.py
git commit -m "fix(technical-analysis): align comprehensive_80 fetcher tests with fail-loud ValueError contract" -- services/technical-analysis/tests/test_comprehensive_80.py
```

### Task 5: RES-12 — remove duplicate tickers retention job (operator SQL)

**Files:** none (DB-state one-liner + evidence paste). Boot-DDL hardening is explicitly OUT of scope (spec §4.1).

- [ ] **Step 1: Confirm both jobs still exist**

Run: `docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c "SELECT job_id, hypertable_name, config FROM timescaledb_information.jobs WHERE proc_name='policy_retention' ORDER BY job_id;"`
Expected: two rows for `tickers` (job_ids 1000 and 1001, identical `drop_after`). If only one row exists, record that and SKIP the delete.

- [ ] **Step 2: Delete the duplicate**

Run: `docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c "SELECT delete_job(1001);"`

- [ ] **Step 3: Verify exactly one remains**

Re-run Step 1's query. Expected: single `tickers` retention row (job_id 1000). Paste both query outputs into the session log / commit message of the next docs commit (no repo file changes here — record in `progress.md` at close-out).

---

## Stream B — evidence plumbing + accrual

### Task 6: `TOURNAMENT_DB_PATH` — one env var, two consumers, one real file

**Files:**
- Modify: `scripts/forward_paper_test/run_evidence_loop.py` (~line 51 constant + argparse default ~line 370)
- Modify: `services/trading-engine/app/preflight/checks.py` (~line 304, `check_dsr_evidence` path resolution)
- Modify: `docker-compose.unified.yml` (trading-engine service block: one env line, one volume line)
- Create: `services/tournament-harness/data/leaderboard/.gitkeep`
- Test: `scripts/forward_paper_test/tests/test_evidence_loop_db_path.py` (create — the existing evidence-loop tests live in `scripts/forward_paper_test/tests/`, which has an `__init__.py`; run with `python3 -m pytest scripts/forward_paper_test/tests/ --no-cov` from repo root)
- Test: `services/trading-engine/tests/test_preflight_checks.py` (extend — file exists, 25 tests)

**Interfaces:**
- Produces: env var **`TOURNAMENT_DB_PATH`** honored by both consumers. Container value: `/data/leaderboard.db` (ro mount of `./services/tournament-harness/data/leaderboard`). Host value: unset → falls back to existing default; cron/operator pass `--db-path` or the env var explicitly.
- The tournament-harness's real DB is `leaderboard_db_path` default `/app/data/leaderboard/leaderboard.db` (`services/tournament-harness/app/config/settings.py:32`), host-side `./services/tournament-harness/data/leaderboard/leaderboard.db`. It does not exist until the harness first runs — both consumers must stay fail-soft on a missing file (they already are: preflight returns `UNKNOWN`, evidence loop exits 2).

- [ ] **Step 1: Write the failing tests**

Evidence-loop test (new file):

```python
"""TOURNAMENT_DB_PATH env override for the evidence-loop driver."""
import importlib


def test_db_path_env_override(monkeypatch):
    monkeypatch.setenv("TOURNAMENT_DB_PATH", "/tmp/somewhere/else.db")
    import scripts.forward_paper_test.run_evidence_loop as rel
    importlib.reload(rel)
    assert rel.resolve_db_path() == "/tmp/somewhere/else.db"


def test_db_path_default_without_env(monkeypatch):
    monkeypatch.delenv("TOURNAMENT_DB_PATH", raising=False)
    import scripts.forward_paper_test.run_evidence_loop as rel
    importlib.reload(rel)
    assert rel.resolve_db_path() == rel.DEFAULT_TOURNAMENT_DB_PATH
```

Preflight test (append to `services/trading-engine/tests/test_preflight_checks.py`, following its existing style — read the file's existing `check_dsr_evidence` tests first and mirror their fixtures):

```python
def test_dsr_evidence_honors_tournament_db_path_env(monkeypatch, tmp_path):
    """check_dsr_evidence with no db_path arg must consult TOURNAMENT_DB_PATH."""
    from app.preflight import checks

    db_file = tmp_path / "leaderboard.db"
    import sqlite3

    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE leaderboard (dsr REAL, run_date TEXT, "
        "psr_ci_published INTEGER, status TEXT)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("TOURNAMENT_DB_PATH", str(db_file))
    result = checks.check_dsr_evidence()
    # Empty table -> whatever status the existing no-rows branch returns
    # (read the function; assert on that status), but the detail string must
    # reference our tmp path, proving the env var was consulted.
    assert str(db_file) in result.detail or result.status != "UNKNOWN"
```

(Adjust the final assertion after reading the no-rows branch — the load-bearing check is that the env-supplied path was used, e.g. via the `db_path=` detail text.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest scripts/forward_paper_test/tests/test_evidence_loop_db_path.py --no-cov -q` (repo root) — expected: FAIL (`resolve_db_path` doesn't exist).
Run: `cd services/trading-engine && python3 -m pytest tests/test_preflight_checks.py -k tournament_db_path --no-cov -q` — expected: FAIL.

- [ ] **Step 3: Implement**

`run_evidence_loop.py` — add beside the constant:

```python
def resolve_db_path() -> str:
    """CLI default for --db-path: TOURNAMENT_DB_PATH env, else the legacy literal."""
    return os.environ.get("TOURNAMENT_DB_PATH", DEFAULT_TOURNAMENT_DB_PATH)
```

and change the argparse default: `default=resolve_db_path(),` (leave `DEFAULT_TOURNAMENT_DB_PATH` itself untouched — it is cross-referenced from checks.py comments).

`checks.py` — in `check_dsr_evidence`, change the resolution line (~304):

```python
    path = db_path or os.environ.get("TOURNAMENT_DB_PATH") or _DEFAULT_TOURNAMENT_DB_PATH
```

(`os` is already imported in checks.py — verify; add if not. Env-read rather than a Settings field is deliberate: `run_all()` calls `check_dsr_evidence()` with no args and threading Settings through its callers is a bigger diff for zero behavioral gain; tests override via `monkeypatch.setenv`.)

`docker-compose.unified.yml` — trading-engine service block, add:

```yaml
      # environment: (append)
      - TOURNAMENT_DB_PATH=/data/leaderboard.db
      # volumes: (append)
      # RO — preflight only reads; the harness + host evidence loop write.
      - ./services/tournament-harness/data/leaderboard:/data:ro
```

Create `services/tournament-harness/data/leaderboard/.gitkeep` so the host dir exists before docker mounts it (else Docker creates it root-owned).

- [ ] **Step 4: Run tests to verify they pass**

Re-run both Step 2 commands. Expected: PASS. Also re-run the full preflight file: `cd services/trading-engine && python3 -m pytest tests/test_preflight_checks.py --no-cov -q` — expected: no regressions.

- [ ] **Step 5: Deploy + four-proof verification (compose change requires recreate)**

```bash
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine
```

Then prove: (1) `docker exec crypto-bot-trading-engine printenv TOURNAMENT_DB_PATH` → `/data/leaderboard.db`; (2) `docker exec crypto-bot-trading-engine ls -la /data/` → mounted dir visible; (3) hit the preflight surface (`curl -s localhost:8000/api/preflight/carry-ins | python3 -m json.tool | head -30` or the engine's preflight endpoint) and confirm `dsr_evidence` detail cites `/data/leaderboard.db` — an `UNKNOWN`/failure status is EXPECTED (file doesn't exist yet); the path in the detail is the proof; (4) engine boots clean (`docker logs crypto-bot-trading-engine --tail 20`, no new errors).

- [ ] **Step 6: Commit**

```bash
git add scripts/forward_paper_test/run_evidence_loop.py services/trading-engine/app/preflight/checks.py docker-compose.unified.yml services/tournament-harness/data/leaderboard/.gitkeep scripts/forward_paper_test/tests/test_evidence_loop_db_path.py services/trading-engine/tests/test_preflight_checks.py
git commit -m "feat(evidence): TOURNAMENT_DB_PATH env wires evidence loop + preflight to the harness leaderboard DB" -- scripts/forward_paper_test/run_evidence_loop.py services/trading-engine/app/preflight/checks.py docker-compose.unified.yml services/tournament-harness/data/leaderboard/.gitkeep scripts/forward_paper_test/tests/test_evidence_loop_db_path.py services/trading-engine/tests/test_preflight_checks.py
```

### Task 7: clean-epoch constant + SQL view

**Files:**
- Create: `scripts/forward_paper_test/epoch.py`
- Create: `scripts/sql/create_clean_epoch_views.sql`
- Test: `scripts/forward_paper_test/tests/test_epoch.py`

**Interfaces:**
- Produces: `CLEAN_DATA_EPOCH_ISO = "2026-08-12T13:47:20Z"` and `CLEAN_DATA_EPOCH_MS` importable by any host script; DB views `public.clean_epoch_positions` / `public.clean_epoch_trades` in the **postgres app DB** (`cryptobot` — NOT TimescaleDB `market_data`; positions/trades live in postgres).
- Consumed by: Task 11 (`complete-run` reads `clean_epoch_positions`), any future clean-paper analysis.

- [ ] **Step 1: Write the failing test**

```python
"""Clean-data epoch constant — single source for analysis filters."""


def test_epoch_constants_agree():
    from scripts.forward_paper_test.epoch import CLEAN_DATA_EPOCH_ISO, CLEAN_DATA_EPOCH_MS
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(CLEAN_DATA_EPOCH_ISO.replace("Z", "+00:00"))
    assert dt.tzinfo is not None
    assert int(dt.timestamp() * 1000) == CLEAN_DATA_EPOCH_MS
    assert CLEAN_DATA_EPOCH_ISO == "2026-08-12T13:47:20Z"
```

- [ ] **Step 2: Run to verify it fails** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `epoch.py`**

```python
"""Clean-data epoch: positions opened at/after this instant ran entirely on the
repaired engine (progress.md 2026-08-12). The two legacy sweep closes seconds
after the epoch (13:47:27Z / 13:47:35Z) belong to PRE-epoch positions and are
excluded by filtering on the POSITION's opened_at, never on trade timestamps.

Single source of truth for host-side analysis. The DB-side twin is the
public.clean_epoch_positions / clean_epoch_trades views
(scripts/sql/create_clean_epoch_views.sql) — keep them in agreement.
"""

CLEAN_DATA_EPOCH_ISO = "2026-08-12T13:47:20Z"
CLEAN_DATA_EPOCH_MS = 1786470440000
```

(Compute the ms value in the test first if unsure; the test pins agreement either way.)

- [ ] **Step 4: Write the SQL (committed record, applied manually — engine has no boot-DDL hook; matches the `repair_res01` script precedent)**

`scripts/sql/create_clean_epoch_views.sql`:

```sql
-- Clean-data epoch views (2026-08-20). Idempotent. Apply to the POSTGRES app
-- DB (cryptobot), not TimescaleDB:
--   docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
--     -f - < scripts/sql/create_clean_epoch_views.sql
-- Epoch: 2026-08-12T13:47:20Z — must agree with
-- scripts/forward_paper_test/epoch.py. Filter is on the POSITION's opened_at;
-- trades join through position_id so post-epoch closes of pre-epoch positions
-- (the two legacy sweeps at 13:47:27Z/13:47:35Z) are excluded.

CREATE OR REPLACE VIEW public.clean_epoch_positions AS
SELECT p.*
FROM public.positions p
WHERE p.opened_at >= TIMESTAMPTZ '2026-08-12T13:47:20Z';

CREATE OR REPLACE VIEW public.clean_epoch_trades AS
SELECT t.*
FROM public.trades t
JOIN public.positions p ON p.position_id = t.position_id
WHERE p.opened_at >= TIMESTAMPTZ '2026-08-12T13:47:20Z';
```

- [ ] **Step 5: Apply + verify with pasted SELECTs**

```bash
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot < scripts/sql/create_clean_epoch_views.sql
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT count(*), min(opened_at) FROM clean_epoch_positions;"
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT count(*) FROM clean_epoch_trades;"
```

Expected as of plan-writing: 2 positions (SOL/BNB opened 2026-08-16), 4 trades (2 entries + 2 exits; the 2 legacy sweep closes EXCLUDED — if you see 6, the join filter is wrong). Counts may be higher if new positions opened since — check `min(opened_at) >= 2026-08-12T13:47:20Z` instead of exact counts. Paste outputs.

- [ ] **Step 6: Run the epoch test to verify it passes; commit**

```bash
git add scripts/forward_paper_test/epoch.py scripts/sql/create_clean_epoch_views.sql scripts/forward_paper_test/tests/test_epoch.py
git commit -m "feat(evidence): clean-data epoch constant + DB views (positions-basis filter excludes legacy sweeps)" -- scripts/forward_paper_test/epoch.py scripts/sql/create_clean_epoch_views.sql scripts/forward_paper_test/tests/test_epoch.py
```

### Task 8: daily evidence tick + staleness tripwire

**Files:**
- Create: `scripts/forward_paper_test/daily_evidence_tick.sh`
- Create: `scripts/check_evidence_staleness.py`
- Test: `scripts/forward_paper_test/tests/test_evidence_staleness.py`

**Interfaces:**
- Produces: marker file `.planning/state/evidence_loop_last_tick.json` — `{"ts_utc": "<iso>", "exit_code": <int>}` — written by the tick wrapper on EVERY attempt (including failures: the marker tracks "the loop ran", not "the loop succeeded"; the exit code inside carries the outcome). `check_evidence_staleness.py` exits 1 if the marker is missing or older than 48h, and prints the last exit code either way.
- Consumes: Task 6's `resolve_db_path()` (via env in cron line).

- [ ] **Step 1: Write the failing test for the staleness checker**

```python
"""Staleness tripwire for the daily evidence tick."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

SCRIPT = "scripts/check_evidence_staleness.py"


def _run(marker_path):
    return subprocess.run(
        [sys.executable, SCRIPT, "--marker", str(marker_path)],
        capture_output=True,
        text=True,
    )


def test_missing_marker_exits_1(tmp_path):
    r = _run(tmp_path / "absent.json")
    assert r.returncode == 1
    assert "missing" in (r.stdout + r.stderr).lower()


def test_fresh_marker_exits_0(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": 0,
    }))
    r = _run(m)
    assert r.returncode == 0


def test_stale_marker_exits_1(tmp_path):
    m = tmp_path / "m.json"
    stale = datetime.now(timezone.utc) - timedelta(hours=49)
    m.write_text(json.dumps({"ts_utc": stale.isoformat(), "exit_code": 0}))
    r = _run(m)
    assert r.returncode == 1
    assert "stale" in (r.stdout + r.stderr).lower()
```

- [ ] **Step 2: Run to verify failure** (script doesn't exist → all 3 fail).

- [ ] **Step 3: Implement `check_evidence_staleness.py`**

```python
#!/usr/bin/env python3
"""Tripwire: alarm when the daily evidence tick has not run in >48h.

The kline collector once died silently for weeks; this is the same class of
guard for the MLGATE evidence loop. Checks marker AGE only — a tick that ran
and failed still counts as alive (its exit_code is printed for the operator).
Exit 0 = tick alive; exit 1 = missing/stale/unreadable marker.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MARKER = ".planning/state/evidence_loop_last_tick.json"
MAX_AGE_HOURS = 48

parser = argparse.ArgumentParser()
parser.add_argument("--marker", default=DEFAULT_MARKER)
args = parser.parse_args()

p = Path(args.marker)
if not p.exists():
    print(f"BREACH: evidence-tick marker missing at {p}")
    sys.exit(1)

try:
    data = json.loads(p.read_text())
    ts = datetime.fromisoformat(data["ts_utc"])
except (ValueError, KeyError) as e:
    print(f"BREACH: marker unreadable ({type(e).__name__})")
    sys.exit(1)

age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
print(f"last tick: {data['ts_utc']} (age {age_h:.1f}h, exit_code={data.get('exit_code')})")
if age_h > MAX_AGE_HOURS:
    print(f"BREACH: evidence tick stale (> {MAX_AGE_HOURS}h)")
    sys.exit(1)
print("OK")
sys.exit(0)
```

- [ ] **Step 4: Implement `daily_evidence_tick.sh`**

```bash
#!/usr/bin/env bash
# Daily MLGATE evidence tick. Cron-invoked (Task 9). Runs the evidence loop
# against the harness leaderboard DB and ALWAYS writes the liveness marker —
# the marker records that the tick ran; exit_code inside records how it went.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

DB="${TOURNAMENT_DB_PATH:-$REPO/services/tournament-harness/data/leaderboard/leaderboard.db}"
LOG="$REPO/.planning/state/evidence_loop_last_tick.log"

python3 -m scripts.forward_paper_test.run_evidence_loop --db-path "$DB" >"$LOG" 2>&1
EC=$?

python3 - "$EC" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
Path(".planning/state").mkdir(parents=True, exist_ok=True)
Path(".planning/state/evidence_loop_last_tick.json").write_text(json.dumps({
    "ts_utc": datetime.now(timezone.utc).isoformat(),
    "exit_code": int(sys.argv[1]),
}))
PY
exit "$EC"
```

`chmod +x scripts/forward_paper_test/daily_evidence_tick.sh`.

- [ ] **Step 5: Run staleness tests to verify pass; simulate the tripwire end-to-end**

Run tests (from repo root, `--no-cov`). Then run the tick once manually: `bash scripts/forward_paper_test/daily_evidence_tick.sh; echo "tick_ec=$?"` — expected while the leaderboard DB doesn't exist: nonzero exit (sqlite error path, exit 2), marker STILL written. Then `python3 scripts/check_evidence_staleness.py` → exit 0 with `exit_code=2` printed. That combination — dead DB, live tripwire — is the designed dormant state until the harness first populates the DB.

- [ ] **Step 6: Commit**

```bash
git add scripts/forward_paper_test/daily_evidence_tick.sh scripts/check_evidence_staleness.py scripts/forward_paper_test/tests/test_evidence_staleness.py
git commit -m "feat(evidence): daily evidence tick wrapper + 48h staleness tripwire" -- scripts/forward_paper_test/daily_evidence_tick.sh scripts/check_evidence_staleness.py scripts/forward_paper_test/tests/test_evidence_staleness.py
```

### Task 9: cron install + runbook note (operator-visible)

**Files:**
- Modify: `docs/runbooks/forward-paper-test.md` (append an "Automation" section)

- [ ] **Step 1: Install the crontab entries**

```bash
( crontab -l 2>/dev/null; \
  echo "30 6 * * * /usr/bin/bash /mnt/d/Bimo_max/crypto-trading-bot/scripts/forward_paper_test/daily_evidence_tick.sh"; \
  echo "0 7 * * * /usr/bin/python3 /mnt/d/Bimo_max/crypto-trading-bot/scripts/check_evidence_staleness.py --marker /mnt/d/Bimo_max/crypto-trading-bot/.planning/state/evidence_loop_last_tick.json >> /mnt/d/Bimo_max/crypto-trading-bot/.planning/state/evidence_staleness.log 2>&1"; \
  echo "15 7 * * 1 cd /mnt/d/Bimo_max/crypto-trading-bot && /usr/bin/python3 scripts/check_collection_gaps.py --window-minutes 10080 >> .planning/state/collection_gaps_weekly.log 2>&1" \
) | crontab -
crontab -l
```

Paste `crontab -l` output. Check cron service is running: `service cron status || sudo service cron start` (WSL does not always autostart it — if sudo needs a password this is an operator step; say so and hand it over rather than guessing).

- [ ] **Step 2: Append to the runbook**

Add to `docs/runbooks/forward-paper-test.md`:

```markdown
## Automation (2026-08-20)

- Daily evidence tick: cron `30 6 * * *` runs `scripts/forward_paper_test/daily_evidence_tick.sh`
  (evidence loop against `TOURNAMENT_DB_PATH`, default
  `services/tournament-harness/data/leaderboard/leaderboard.db`), writing
  `.planning/state/evidence_loop_last_tick.json` on every attempt.
- Staleness tripwire: cron `0 7 * * *` runs `scripts/check_evidence_staleness.py`
  (exit 1 when the marker is missing or older than 48h). WSL caveat: cron only
  runs while WSL is up and the cron service is started (`sudo service cron start`);
  the tripwire exists precisely because this scheduler can die silently — check
  `.planning/state/evidence_staleness.log` when in doubt.
- Weekly collection gap check: cron `15 7 * * 1` (Mondays) runs `check_collection_gaps.py --window-minutes 10080` into `.planning/state/collection_gaps_weekly.log` — the Phase C 21-day clock's tripwire (spec Stream 0).
- The tick is expected to exit 2 (sqlite error, marker still written) until the
  tournament harness first creates the leaderboard DB — dormant-but-alive is the
  designed state during accrual.
```

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/forward-paper-test.md
git commit -m "docs(evidence): automation section — daily tick cron + staleness tripwire semantics" -- docs/runbooks/forward-paper-test.md
```

### Task 10: fix the broken isolation-run launcher (`docker compose up -e` does not exist)

**Files:**
- Modify: `scripts/forward_paper_test/run_isolation.py` (`_build_docker_argv` ~line 114, and the `runner(argv, cwd=...)` call ~line 323)
- Modify: `docker-compose.unified.yml` (trading-engine env block — ensure the three flag vars interpolate from the shell)
- Test: extend `scripts/forward_paper_test/tests/test_run_isolation_live.py` (the existing launcher tests — they inject `subprocess_runner`)

**Interfaces:**
- Consumes: `TIER1_FLAG_PROFILES` (`profiles.py`) — `env_overrides` dicts like `{"ENABLE_VOL_TARGETING": "false", "PREFER_MAKER_ORDERS": "true", "ENABLE_FUNDING_GATE": "false"}`.
- Produces: launcher passes overrides via the **subprocess environment** (compose interpolates `${VAR:-default}` from the invoking shell env), argv is plain `docker compose -f docker-compose.unified.yml up -d trading-engine`.

- [ ] **Step 1: Verify compose interpolation exists for all three flags**

Run: `grep -n "ENABLE_VOL_TARGETING\|PREFER_MAKER_ORDERS\|ENABLE_FUNDING_GATE" docker-compose.unified.yml`
Expected: three lines in the trading-engine environment block shaped like `- PREFER_MAKER_ORDERS=${PREFER_MAKER_ORDERS:-false}`. **If any are missing or hardcoded**, add/fix them (default `false` for all three) — without `${}` interpolation the env-based launcher cannot work.

- [ ] **Step 2: Write the failing test**

In the existing run_isolation test file, following its established `subprocess_runner` injection pattern:

```python
def test_launcher_passes_overrides_via_env_not_argv(monkeypatch, tmp_path):
    """docker compose up has no -e flag; overrides must ride the subprocess env."""
    import scripts.forward_paper_test.run_isolation as ri

    captured = {}

    def fake_runner(argv, cwd=None, env=None):
        captured["argv"] = argv
        captured["env"] = env
        class R: returncode = 0
        return R()

    monkeypatch.setenv("PAPER_TRADING_MODE", "true")
    monkeypatch.delenv("TRADING_MODE", raising=False)
    # invoke the launch path the existing tests use, injecting fake_runner
    ri.launch_isolation_run(
        flag="prefer_maker_orders",
        duration_days=7,
        run_id="test-run",
        paper_trade_log=None,
        subprocess_runner=fake_runner,
    )  # adapt name/signature to the real function the existing tests call

    assert "-e" not in captured["argv"]
    assert captured["argv"][-1] == "trading-engine"
    assert captured["env"]["PREFER_MAKER_ORDERS"] == "true"
    assert captured["env"]["ENABLE_VOL_TARGETING"] == "false"
    assert captured["env"]["ENABLE_FUNDING_GATE"] == "false"
    # sanity: the rest of the operator environment is preserved
    assert "PATH" in captured["env"]
```

(Read the real function name/signature from the file and existing tests first; adapt. The three assertions on argv/env are the contract.)

- [ ] **Step 3: Run to verify it fails** (current code puts `-e` pairs in argv and passes no `env`).

- [ ] **Step 4: Implement**

`_build_docker_argv` loses the `-e` loop:

```python
def _build_docker_argv(flag: str) -> list[str]:
    """docker compose argv for an isolation run.

    Env overrides are NOT argv: `docker compose up` has no -e flag (the
    pre-2026-08-20 version emitted one and could never have launched). They
    ride the subprocess environment instead — compose interpolates
    ${VAR:-default} entries in the trading-engine block from it.
    """
    return ["docker", "compose", "-f", _COMPOSE_FILE, "up", "-d", _TRADING_ENGINE_SERVICE]
```

Call site: build the env and pass it:

```python
    argv = _build_docker_argv(flag)
    run_env = {**os.environ, **env_overrides}
    result = runner(argv, cwd=str(_REPO), env=run_env)
```

(Adjust `_build_docker_argv`'s other callers if any; `grep -n "_build_docker_argv" scripts/ tests/`.)

- [ ] **Step 5: Run the new test + the whole run_isolation test file** — expected: new test passes, existing argv-shape tests updated if they asserted the old broken `-e` form (update them to the new contract; that is correcting a test that pinned a bug).

- [ ] **Step 6: Dry-run proof against real docker**

Run: `PAPER_TRADING_MODE=true python3 -m scripts.forward_paper_test.run_isolation --flag prefer_maker_orders --duration-days 7 --dry-run`
Expected: JSON plan printed, exit 0, no docker invocation.

- [ ] **Step 7: Commit**

```bash
git add scripts/forward_paper_test/run_isolation.py docker-compose.unified.yml scripts/forward_paper_test/tests/test_run_isolation_live.py
git commit -m "fix(evidence): isolation launcher passed env overrides as 'docker compose up -e' (no such flag) — ride subprocess env" -- scripts/forward_paper_test/run_isolation.py docker-compose.unified.yml scripts/forward_paper_test/tests/test_run_isolation_live.py
```

### Task 11: `complete-run` — produce `run.json` from closed clean-epoch positions

**Files:**
- Modify: `scripts/forward_paper_test/run_isolation.py` (new subcommand; its error text at ~line 307 already references `complete-run` as if it existed)
- Test: same run_isolation test file

**Interfaces:**
- Consumes: `clean_epoch_positions` view (Task 7); `meta.json` in the evidence dir (written at launch; contains flag, run_id, launch time).
- Produces: `<evidence_dir>/run.json` with the shape `psr_ci.load_run_returns` requires: non-empty, NaN-free `"returns"` array of per-trade returns. Per-trade return = `realized_pnl / (entry_price * quantity)` per CLOSED position opened within the run window. Plus provenance: `run_id`, `flag`, `window`, `n_positions`, `source`.

- [ ] **Step 1: Read first** — `psr_ci.load_run_returns` (exact keys it validates) and `_write_meta_json` (exact meta.json keys, especially the launch timestamp key name). The subcommand must match both. Do not guess: open the files.

- [ ] **Step 2: Write the failing test**

```python
def test_complete_run_writes_run_json(tmp_path, monkeypatch):
    """complete-run derives per-trade returns from closed positions and writes run.json."""
    import json
    import scripts.forward_paper_test.run_isolation as ri

    ev = tmp_path / "prefer_maker_orders" / "r1"
    ev.mkdir(parents=True)
    (ev / "meta.json").write_text(json.dumps({
        "flag": "prefer_maker_orders",
        "run_id": "r1",
        "launched_at_utc": "2026-08-20T12:00:00+00:00",
        "duration_days": 7,
    }))  # adapt keys to the real _write_meta_json output

    rows = [
        # (symbol, side, entry_price, quantity, realized_pnl, opened_at, closed_at)
        ("SOLUSDT", "LONG", "180.0", "0.05", "0.25", "2026-08-21T01:00:00+00:00", "2026-08-22T01:00:00+00:00"),
        ("BNBUSDT", "LONG", "700.0", "0.012", "-0.03", "2026-08-21T02:00:00+00:00", "2026-08-23T02:00:00+00:00"),
    ]
    monkeypatch.setattr(ri, "_fetch_closed_positions", lambda since_iso: rows)

    rc = ri.complete_run(ev)
    assert rc == 0
    data = json.loads((ev / "run.json").read_text())
    assert len(data["returns"]) == 2
    assert abs(data["returns"][0] - 0.25 / (180.0 * 0.05)) < 1e-12
    assert data["n_positions"] == 2


def test_complete_run_refuses_empty_window(tmp_path, monkeypatch):
    import json
    import scripts.forward_paper_test.run_isolation as ri

    ev = tmp_path / "prefer_maker_orders" / "r2"
    ev.mkdir(parents=True)
    (ev / "meta.json").write_text(json.dumps({
        "flag": "prefer_maker_orders", "run_id": "r2",
        "launched_at_utc": "2026-08-20T12:00:00+00:00", "duration_days": 7,
    }))
    monkeypatch.setattr(ri, "_fetch_closed_positions", lambda since_iso: [])

    rc = ri.complete_run(ev)
    assert rc != 0
    assert not (ev / "run.json").exists()
```

- [ ] **Step 3: Run to verify failure** (`complete_run` / `_fetch_closed_positions` don't exist).

- [ ] **Step 4: Implement**

```python
def _fetch_closed_positions(since_iso: str) -> list[tuple]:
    """Closed clean-epoch positions opened at/after since_iso, via docker-exec psql.

    Uses the clean_epoch_positions view (scripts/sql/create_clean_epoch_views.sql)
    so pre-epoch legacy rows can never leak into evidence. Host-run: goes through
    the postgres container like scripts/check_collection_gaps.py does for
    TimescaleDB. Injection-safe: since_iso comes from our own meta.json, and is
    still passed through a strict ISO parse before interpolation.
    """
    from datetime import datetime

    datetime.fromisoformat(since_iso)  # raises on garbage — never skip
    sql = (
        "SELECT symbol, side, entry_price, quantity, realized_pnl, "
        "opened_at, closed_at FROM public.clean_epoch_positions "
        f"WHERE status = 'CLOSED' AND opened_at >= '{since_iso}' "
        "ORDER BY opened_at"
    )
    out = subprocess.run(
        ["docker", "exec", "crypto-bot-postgres", "psql", "-U", "cryptobot",
         "-d", "cryptobot", "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True, text=True, check=True,
    )
    return [tuple(line.split("|")) for line in out.stdout.strip().splitlines() if line]


def complete_run(evidence_dir) -> int:
    """Write run.json: per-trade returns for the run's window. Returns exit code."""
    import json
    from decimal import Decimal
    from pathlib import Path

    evidence_dir = Path(evidence_dir)
    meta = json.loads((evidence_dir / "meta.json").read_text())
    since = meta["launched_at_utc"]  # adapt key to real meta.json
    rows = _fetch_closed_positions(since)
    if not rows:
        print(
            f"ERROR: no closed positions opened since {since}; refusing to write "
            "an empty run.json (psr_ci requires a non-empty returns array).",
            file=sys.stderr,
        )
        return 1
    returns = []
    for symbol, side, entry_price, quantity, realized_pnl, opened_at, closed_at in rows:
        notional = Decimal(entry_price) * Decimal(quantity)
        returns.append(float(Decimal(realized_pnl) / notional))
    payload = {
        "returns": returns,
        "run_id": meta["run_id"],
        "flag": meta["flag"],
        "window": {"since": since},
        "n_positions": len(rows),
        "source": "clean_epoch_positions view via complete-run",
    }
    (evidence_dir / "run.json").write_text(json.dumps(payload, indent=2))
    print(f"run.json written: {len(returns)} returns -> {evidence_dir / 'run.json'}")
    return 0
```

Wire into the CLI beside the existing `publish-evidence` subcommand (mirror its argparse shape): `python -m scripts.forward_paper_test.run_isolation complete-run <evidence_dir>`. Check whether positions rows carry the position's own status column name (`status`) and side values — read `app/database/models.py` Position columns and adjust the SQL column list to reality before finalizing.

- [ ] **Step 5: Run tests to verify pass; then a live smoke against the real DB**

`python3 -m scripts.forward_paper_test.run_isolation complete-run .planning/evidence/forward_paper_test/does-not-exist 2>&1 | head -2` → clean error, nonzero exit (no meta.json). That's the negative proof; the positive one happens at day-8 completion of the real run.

- [ ] **Step 6: Commit**

```bash
git add scripts/forward_paper_test/run_isolation.py scripts/forward_paper_test/tests/test_run_isolation_live.py
git commit -m "feat(evidence): complete-run subcommand — run.json per-trade returns from clean_epoch_positions" -- scripts/forward_paper_test/run_isolation.py scripts/forward_paper_test/tests/test_run_isolation_live.py
```

### Task 12: START the `prefer_maker_orders` isolation run (operator-gated, changes running system)

**Files:** none (operational). **Depends on Tasks 6, 10.**

**STOP — operator confirmation required before this task.** It recreates the trading-engine container with `PREFER_MAKER_ORDERS=true`: the live paper-trader's execution style changes for ~7 days. That is the point of the isolation run, but it must not happen as a silent side effect. Confirm with the operator in-session before executing.

- [ ] **Step 1 (after confirmation): launch**

```bash
PAPER_TRADING_MODE=true python3 -m scripts.forward_paper_test.run_isolation --flag prefer_maker_orders --duration-days 7
```

- [ ] **Step 2: Four-proof verification**

(1) `docker exec crypto-bot-trading-engine printenv PREFER_MAKER_ORDERS` → `true`, and the other two flags `false`; (2) engine log shows a maker-path line on the next actionable signal (or at minimum boots clean with the flag visible in its settings dump); (3) `ls .planning/evidence/forward_paper_test/prefer_maker_orders/<run_id>/meta.json` exists — paste it; (4) kill-switch file absent + `/api/trading/status` shows the loop running (the isolation run must not silently halt trading).

- [ ] **Step 3: Record** — run_id + launch timestamp into `progress.md` (session log), with the day-8 follow-up noted: `complete-run` → `psr_ci` → `publish-evidence`.

### Task 13: 48h collection acceptance check (time-gated: on/after 2026-08-21 17:30 UTC)

**Files:**
- Create: `.planning/evidence/collection-48h-acceptance-20260821.md` (output paste)

- [ ] **Step 1: Run the gap check over the 48h window**

Not before 2026-08-21 17:30 UTC (collection started 2026-08-19 ~17:30 UTC):

```bash
python3 scripts/check_collection_gaps.py --window-minutes 2880 | tee /tmp/claude-1000/collection-48h.txt; echo "exit=$?"
```

- [ ] **Step 2: Record verdict**

Write the full output + exit code + date into `.planning/evidence/collection-48h-acceptance-20260821.md` with a one-line verdict: PASS (exit 0, all symbols OK) or BREACH (any breach line — a breach is a collection incident: fix the collector before anything else in this plan, per spec Stream 0, and note that the 21-day Phase C clock resets).

- [ ] **Step 3: Commit**

```bash
git add .planning/evidence/collection-48h-acceptance-20260821.md
git commit -m "data(collection): 48h acceptance check verdict" -- .planning/evidence/collection-48h-acceptance-20260821.md
```

---

## Stream C — debt mediums

### Task 14: conftest collision — shared helper modules with unique basenames

**Files:**
- Create: `tests/edge_lab/el_shared.py` (move `DAY`, `T0`, `make_daily`, `assert_shift_invariant` out of conftest)
- Create: `tests/killtests/kt_shared.py` (move `_write_candles` out of conftest)
- Modify: `tests/edge_lab/conftest.py` (keep: sys.path insert, `universe12` fixture — now importing from `el_shared`)
- Modify: `tests/killtests/conftest.py` (keep: sys.path insert, `write_candles` fixture importing from `kt_shared`, and `pytest_sessionfinish` — the golden-parity hook MUST stay in a conftest, untouched)
- Modify: 9 edge_lab test files + 2 killtests test files (import lines only; exact list below)

**Mechanism rationale (pinned here, per spec §4.2):** pytest's default `prepend` import mode gives both `conftest.py` files the top-level module name `conftest`; the 11 `from conftest import …` lines resolve through `sys.modules["conftest"]` and whichever directory loaded last wins → ImportError in the other suite when both are collected in one session. Adding `__init__.py` packages was rejected: `tests/` itself has none and packaging it changes module identity for every other suite under `tests/` (e2e, smoke, security…) — too much blast radius. Unique basenames (`el_shared` / `kt_shared`) remove the only colliding import surface; fixtures keep flowing through conftests (fixture injection needs no import).

- [ ] **Step 1: Reproduce the collision (RED)**

Run: `python3 -m pytest tests/edge_lab tests/killtests --no-cov -q 2>&1 | tail -5`
Expected: collection errors — `ImportError` around `DAY` (or `_write_candles`, order-dependent). Also record the current standalone baselines: `python3 -m pytest tests/edge_lab --no-cov -q | tail -2` and `python3 -m pytest tests/killtests --no-cov -q | tail -2` (killtests has 3 pre-existing golden-parity failures needing the live stack — those are NOT this task's problem; capture the count to compare after).

- [ ] **Step 2: Create the shared modules**

`tests/edge_lab/el_shared.py`: move the entire contents of `tests/edge_lab/conftest.py` EXCEPT the `universe12` fixture and the pytest import — i.e. the `sys`/`Path`/`numpy`/`pandas` imports, the `REPO`/`sys.path.insert` side effect (keep a copy of the side effect in BOTH conftest and el_shared: el_shared is imported by test modules directly and must be independently safe), `DAY`, `T0`, `make_daily`, `assert_shift_invariant` — all verbatim, no logic changes.

`tests/killtests/kt_shared.py`: same treatment for `_write_candles` (with its `numpy`/`pandas` imports and the `REPO` sys.path side effect copied).

- [ ] **Step 3: Slim the conftests**

`tests/edge_lab/conftest.py` becomes:

```python
"""Fixtures for edge_lab tests. Shared constants/helpers live in el_shared
(unique basename — a second top-level `conftest` module in tests/killtests
collides under pytest prepend import mode; see 2026-08-20 wait-window plan)."""

import pytest

from el_shared import DAY, T0, make_daily, assert_shift_invariant  # noqa: F401


@pytest.fixture
def universe12():
    syms = [f"S{i:02d}USDT" for i in range(12)]
    drifts = {
        s: 0.004 if i < 3 else (-0.004 if i >= 9 else 0.0) for i, s in enumerate(syms)
    }
    return make_daily(syms, drifts=drifts)
```

(The re-export line keeps any straggler `from conftest import` working during review, but Step 4 removes them all anyway; keep the `# noqa: F401` so the format hook cannot strip it — that exact failure mode is on record.)

`tests/killtests/conftest.py`: keep the file verbatim MINUS the `_write_candles` body, plus `from kt_shared import _write_candles  # noqa: F401` at top; the `write_candles` fixture returns the imported function; `pytest_sessionfinish` untouched.

- [ ] **Step 4: Update the 11 import lines**

edge_lab (9 files — change `from conftest import` → `from el_shared import`, keeping each file's exact imported names and `# noqa: E402` comments): `test_edge_lab_battery.py:9`, `test_edge_lab_funding_carry.py:9`, `test_edge_lab_funding_carry_variants.py:18`, `test_edge_lab_lf_trend.py:10`, `test_edge_lab_lf_trend_regime.py:10`, `test_edge_lab_pairs_statarb.py:10`, `test_edge_lab_trials_threading.py:28`, `test_edge_lab_vol_breakout.py:11`, `test_edge_lab_xs_momentum.py:9`.

killtests (2 files — `from conftest import _write_candles` → `from kt_shared import _write_candles`): `test_offline_driver.py:11`, `test_offline_ensemble_seam.py:14`.

- [ ] **Step 5: Verify — standalone AND combined (GREEN)**

```bash
python3 -m pytest tests/edge_lab --no-cov -q | tail -2
python3 -m pytest tests/killtests --no-cov -q | tail -2
python3 -m pytest tests/edge_lab tests/killtests --no-cov -q | tail -2
```

Expected: edge_lab all pass standalone AND combined; killtests matches its Step-1 baseline (3 pre-existing live-stack failures, no new ones); the combined run has ZERO collection errors. Also confirm no `from conftest import` remains: `grep -rn "from conftest import" tests/edge_lab tests/killtests` → empty.

- [ ] **Step 6: Commit**

```bash
git add tests/edge_lab/el_shared.py tests/killtests/kt_shared.py tests/edge_lab/conftest.py tests/killtests/conftest.py tests/edge_lab/test_edge_lab_battery.py tests/edge_lab/test_edge_lab_funding_carry.py tests/edge_lab/test_edge_lab_funding_carry_variants.py tests/edge_lab/test_edge_lab_lf_trend.py tests/edge_lab/test_edge_lab_lf_trend_regime.py tests/edge_lab/test_edge_lab_pairs_statarb.py tests/edge_lab/test_edge_lab_trials_threading.py tests/edge_lab/test_edge_lab_vol_breakout.py tests/edge_lab/test_edge_lab_xs_momentum.py tests/killtests/test_offline_driver.py tests/killtests/test_offline_ensemble_seam.py
git commit -m "fix(tests): resolve edge_lab/killtests conftest module-name collision via unique shared-helper basenames" -- tests/edge_lab tests/killtests
```

### Task 15: `validate_risk_limits.py` — delete tautologies, keep real probes

**Files:**
- Modify: `scripts/validate_risk_limits.py`

**Surgery list (pinned):**
- **DELETE** `test_stop_loss_calculation` (lines ~434-512): both sides of every comparison come from the same `entry ± atr*multiplier` formula — cannot fail, probes nothing.
- **DELETE** `test_leverage_restrictions` (~586-629): three hardcoded `print_test(..., True)` + one `equity*0.10 <= equity` tautology.
- **SURGICAL** `test_emergency_stop` (~631-691): delete the two hardcoded "endpoint exists" `print_test(True)` blocks (no HTTP call behind them); KEEP the two real probes (GET `{TRADING_ENGINE_URL}/api/v1/status`, GET `:8006/health`).

Mechanical consequences (the report is counter-based, but statics are hardcoded): (1) remove the two deleted `await` lines in `main()` (~790-797); (2) renumber every remaining section's hardcoded `[N/8]` banner to `[N/6]`; (3) prune the `• Stop-loss: ATR-based dynamic` and `• Leverage: {MAX_LEVERAGE}x (no leverage)` bullets from `print_summary`'s success branch (~709-728) and reword `• Emergency stop: Available` to reflect what is actually probed (`status + notification health endpoints`); (4) update the script docstring "Tests:" list (~17-25); (5) remove now-unused constants/imports if any (`MAX_LEVERAGE` — check remaining references first).

- [ ] **Step 1: Baseline run**

Run: `python3 scripts/validate_risk_limits.py; echo "exit=$?"` (stack must be up). Record pass/fail/warning counts.

- [ ] **Step 2: Apply the surgery** exactly as listed above.

- [ ] **Step 3: Verify**

Re-run. Expected: 6 sections, `[1/6]`..`[6/6]` banners, lower Tests Run count, same exit code as baseline (deletions removed only always-PASS rows — if the exit code CHANGED, a real probe was damaged: stop and diff). `grep -n "8\]" scripts/validate_risk_limits.py` → no stale `[N/8]` banners.

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_risk_limits.py
git commit -m "fix(scripts): validate_risk_limits — delete tautological stop-loss/leverage sections, keep only real emergency-stop probes" -- scripts/validate_risk_limits.py
```

### Task 16: RES-10 — make the in-container gateway-test rule true

**Files:**
- Modify: `services/api-gateway/Dockerfile` (~line 64: add tests COPY)
- Modify: `services/api-gateway/tests/test_tournament_snapshots.py` (~lines 225-257: RecursionError fix)
- Modify: `.claude/rules/testing.md` (note the image now carries tests)

- [ ] **Step 1: Fix the RecursionError first (host-independent)**

In `test_detail_returns_500_when_file_exceeds_50mb`, the patched `fake_stat` calls `target.resolve()` on every `Path.stat` invocation — `resolve()` re-enters the patched `stat` → unbounded recursion. Fix: resolve ONCE, before the monkeypatch:

```python
    original_stat = pathlib.Path.stat
    resolved_target = target.resolve()  # BEFORE the patch — resolve() calls stat()

    def fake_stat(self, *args, **kwargs):  # type: ignore[override]
        real = original_stat(self, *args, **kwargs)
        if self == resolved_target or self == target:
            return _BigStat(real)
        return real
```

(`_BigStat` unchanged.)

- [ ] **Step 2: Verify pytest is in the gateway image, then add the COPY**

Run: `docker exec crypto-bot-api-gateway python -c "import pytest; print(pytest.__version__)"` — if this fails, pytest is not in `requirements.txt`; STOP and report (installing test deps into the image is a scope decision, not a silent add). If it succeeds, add to the Dockerfile after the pytest.ini COPY (line ~65):

```dockerfile
COPY --chown=appuser:appuser tests/ ./tests/
```

- [ ] **Step 3: Rebuild + run in-container (GREEN)**

```bash
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build api-gateway
docker exec crypto-bot-api-gateway pytest --no-cov -q 2>&1 | tail -3
```

Expected: suite runs (finally possible) and passes — including the RecursionError test, and the 3 rate-limiter-vs-suite interactions may need `RATE_LIMIT_ENABLED=false` (`docker exec -e RATE_LIMIT_ENABLED=false crypto-bot-api-gateway pytest --no-cov -q`) — that interaction is on record (2026-08-04), use the flag and note it.

- [ ] **Step 4: Update `.claude/rules/testing.md`**

Amend the in-container bullet: the image now COPYs `tests/`; the documented command `docker exec crypto-bot-api-gateway pytest` works as of this commit (previously the image had no tests — the rule was aspirational). Keep the fastapi 0.109-vs-0.136 rationale text.

- [ ] **Step 5: Commit**

```bash
git add services/api-gateway/Dockerfile services/api-gateway/tests/test_tournament_snapshots.py .claude/rules/testing.md
git commit -m "fix(api-gateway): ship tests/ in image (RES-10), fix Path.stat monkeypatch recursion in snapshot-size test" -- services/api-gateway/Dockerfile services/api-gateway/tests/test_tournament_snapshots.py .claude/rules/testing.md
```

### Task 17: RES-09 — hydrate PM transaction history from the shared `trades` table

**Files:**
- Create: `services/portfolio-manager/app/services/trade_history_db.py`
- Modify: `services/portfolio-manager/app/handlers/transaction_history.py` (~line 130: hydration seam)
- Modify: `services/portfolio-manager/app/main.py` (expose the pool to the handler — read how other handlers access module globals first and follow that pattern; re-add any import the format hook strips with `# noqa: F401`)
- Test: `services/portfolio-manager/tests/test_trade_history_db.py` (create, beside existing PM tests)

**Interfaces:**
- Decision (pinned by spec §4.2 leaning, confirmed by scan): **hydrate from DB**, not proxy. PM already holds an asyncpg pool to the SAME postgres DB (`cryptobot`) that the engine writes `trades` to; a proxy would return round-trip POSITIONS (both TE endpoints serve positions, not fills) — a semantic change to `/api/portfolio/trades`, whereas the trades table matches PM's fill-level `Transaction` model. PM stays read-only on engine tables (FIX 11 mirror doctrine).
- Produces: `async def fetch_transactions(pool, portfolio_id: str, limit: int | None, symbol: str | None) -> list[Transaction]`
- Field mapping (trades row → PM `Transaction`): `transaction_id=str(trade_id)`, `portfolio_id`, `symbol`, `action`, `quantity=str(quantity)`, `price=str(price)`, `total_amount=str(total_cost)`, `realized_pnl=str(realized_pnl) if not None`, `realized_pnl_pct=str(pnl_percentage) if not None`, `timestamp=int(executed_at.timestamp()*1000)`.
- Fail-soft: `db_pool is None` (PM boots without DB by design) → fall back to the in-memory dict exactly as today, log a warning once.

- [ ] **Step 1: Write the failing tests**

```python
"""RES-09: /api/v1/transactions hydrates from the shared trades table."""
import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.trade_history_db import fetch_transactions


class FakePool:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_args = None

    async def fetch(self, query, *args):
        self.last_query = query
        self.last_args = args
        return self._rows


def _row(**kw):
    base = dict(
        trade_id="11111111-2222-3333-4444-555555555555",
        portfolio_id="paper_trading",
        symbol="SOLUSDT",
        action="SELL",
        quantity=Decimal("0.05"),
        price=Decimal("180.0"),
        total_cost=Decimal("9.0"),
        realized_pnl=Decimal("0.25"),
        pnl_percentage=Decimal("2.78"),
        executed_at=dt.datetime(2026, 8, 22, 1, 0, tzinfo=dt.timezone.utc),
    )
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_fetch_maps_row_to_transaction():
    pool = FakePool([_row()])
    txns = await fetch_transactions(pool, "paper_trading", limit=50, symbol=None)
    t = txns[0]
    assert t.action == "SELL"
    assert t.quantity == "0.05"
    assert t.total_amount == "9.0"
    assert t.realized_pnl == "0.25"
    assert t.realized_pnl_pct == "2.78"
    assert t.timestamp == int(dt.datetime(2026, 8, 22, 1, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)


@pytest.mark.asyncio
async def test_fetch_buy_row_has_no_pnl():
    pool = FakePool([_row(action="BUY", realized_pnl=None, pnl_percentage=None)])
    txns = await fetch_transactions(pool, "paper_trading", limit=None, symbol=None)
    assert txns[0].realized_pnl is None


@pytest.mark.asyncio
async def test_fetch_parameterizes_symbol_and_limit():
    pool = FakePool([])
    await fetch_transactions(pool, "paper_trading", limit=10, symbol="SOLUSDT")
    assert "$2" in pool.last_query  # symbol is a bind param, never interpolated
    assert "SOLUSDT" in pool.last_args
```

(asyncpg returns `Record` objects supporting `row["col"]` — dicts satisfy the same access; write `fetch_transactions` against subscript access.)

- [ ] **Step 2: Run to verify failure** (module doesn't exist). PM tests: check for a PM-local pytest.ini / conftest; run from `services/portfolio-manager/` with `--no-cov`.

- [ ] **Step 3: Implement `trade_history_db.py`**

```python
"""Read-only hydration of PM transaction history from the engine-owned trades
table (RES-09). PM never writes engine tables — mirror doctrine (FIX 11).

The trades table lives in the same postgres DB both services already share;
idx_trades_portfolio_date (portfolio_id, executed_at) backs this query.
"""

import logging
from typing import Optional

from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

_BASE_QUERY = (
    "SELECT trade_id, portfolio_id, symbol, action, quantity, price, "
    "total_cost, realized_pnl, pnl_percentage, executed_at "
    "FROM trades WHERE portfolio_id = $1"
)


async def fetch_transactions(
    pool, portfolio_id: str, limit: Optional[int], symbol: Optional[str]
) -> list[Transaction]:
    query = _BASE_QUERY
    args: list = [portfolio_id]
    if symbol:
        query += " AND symbol = $2"
        args.append(symbol)
    query += " ORDER BY executed_at DESC"
    if limit:
        query += f" LIMIT ${len(args) + 1}"
        args.append(limit)

    rows = await pool.fetch(query, *args)
    txns = []
    for r in rows:
        txns.append(
            Transaction(
                transaction_id=str(r["trade_id"]),
                portfolio_id=r["portfolio_id"],
                symbol=r["symbol"],
                action=r["action"],
                quantity=str(r["quantity"]),
                price=str(r["price"]),
                total_amount=str(r["total_cost"]),
                realized_pnl=(
                    str(r["realized_pnl"]) if r["realized_pnl"] is not None else None
                ),
                realized_pnl_pct=(
                    str(r["pnl_percentage"]) if r["pnl_percentage"] is not None else None
                ),
                timestamp=int(r["executed_at"].timestamp() * 1000),
            )
        )
    return txns
```

- [ ] **Step 4: Wire the handler**

In `handlers/transaction_history.py`, at the seam where `manager.get_transaction_history(...)` is called: if the DB pool is available, `transactions = await fetch_transactions(pool, portfolio_id, limit, symbol)`; else keep the in-memory call and `logger.warning("trades hydration unavailable (no db pool); serving in-memory history")`. How the handler reaches the pool: read `app/main.py`'s existing pattern for module globals (e.g. how `get_portfolio_manager()` is exposed) and mirror it — likely a `get_db_pool()` accessor in `main.py` imported by the handler. The summary-statistics loop below the seam already consumes `Transaction` objects with string Decimals — unchanged.

- [ ] **Step 5: Run tests to verify pass**, then run the whole PM suite (`cd services/portfolio-manager && python3 -m pytest tests/ --no-cov -q | tail -3`) — no regressions (baseline was 99 passed).

- [ ] **Step 6: Deploy + four-proof**

```bash
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build portfolio-manager
```

Then: (1) `curl -s "localhost:8000/api/portfolio/trades?limit=5" | python3 -m json.tool | head -40` → real trade rows (non-empty for the first time; expect the RES-01-corrected pnl values); (2) cross-check one row against `docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT trade_id, symbol, action, realized_pnl FROM trades ORDER BY executed_at DESC LIMIT 5;"` — paste both; (3) PM logs clean; (4) container was rebuilt+recreated (config/code change).

- [ ] **Step 7: Commit**

```bash
git add services/portfolio-manager/app/services/trade_history_db.py services/portfolio-manager/app/handlers/transaction_history.py services/portfolio-manager/app/main.py services/portfolio-manager/tests/test_trade_history_db.py
git commit -m "feat(portfolio-manager): hydrate /api/v1/transactions from shared trades table (RES-09, read-only, fail-soft)" -- services/portfolio-manager/app/services/trade_history_db.py services/portfolio-manager/app/handlers/transaction_history.py services/portfolio-manager/app/main.py services/portfolio-manager/tests/test_trade_history_db.py
```

---

## Close-out (after all tasks)

- [ ] Update `progress.md` with a session entry: suite status (was 15 known-red → now), evidence plumbing state (env var, views, cron, tripwire), isolation run_id + day-8 follow-up date, RES-12 SQL evidence, remaining spec items (Phase 19 → GSD plan-phase next).
- [ ] Run `/gsd:plan-phase` for the reframed Phase 19 with the spec as CONTEXT input — that is the next unit of work, not part of this plan.

## Execution notes

- Tasks 1–5 are independent of 6–13 and 14–17; within each stream, order as written (Task 1 first overall — it defuses the format hook for everything after).
- Task 12 has a hard operator gate. Task 13 has a hard time gate (2026-08-21 17:30 UTC). Everything else can run immediately.
- Docker rebuilds: BuildKit off (`DOCKER_BUILDKIT=0`), never pipe compose build output through `tail` (masked a dead credential helper once — pipefail or full output).
- If the WSL vsock credential-helper failure appears during rebuilds: clean `DOCKER_CONFIG` (`{"auths":{}}`) workaround is on record.
