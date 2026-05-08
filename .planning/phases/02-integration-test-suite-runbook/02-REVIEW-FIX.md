---
phase: 02-integration-test-suite-runbook
fixed_at: 2026-05-08T14:55:00Z
review_path: .planning/phases/02-integration-test-suite-runbook/02-REVIEW.md
iteration: 2
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report (Iteration 2)

**Fixed at:** 2026-05-08T14:55:00Z
**Source review:** `.planning/phases/02-integration-test-suite-runbook/02-REVIEW.md`
**Iteration:** 2 (supersedes the iteration-1 report from the prior token-quota-truncated run)

**Summary:**
- Findings in scope: 13 (4 Blocker + 9 Warning)
- Fixed: 13
- Skipped: 0

The iteration-1 run (recorded in the prior REVIEW-FIX.md, applied BL-01..BL-04 manually as commits `c102a44`, `884ca4d`, `63a39c2`, `3bd8d55` directly on `sync/cherry-picks-2026-05-05`) completed the four blockers but deferred all nine warnings. This iteration-2 run picks up the deferred warnings AND closes a gap in BL-03 that the iteration-1 fix did not catch.

All 14 fix commits from this run live on the temp branch `gsd-reviewfix/02-30801`. The agent's transactional cleanup tail attempted `git merge --ff-only` into `sync/cherry-picks-2026-05-05` and **failed with "Diverging branches can't be fast-forwarded"** — cause: the iteration-1 BL-01 (`c102a44`) and BL-02 (`884ca4d`) commits already on the user's branch overlap with this run's BL-01 (`c172465`) and BL-02 (`1298eaa`). Per the protocol, the temp branch is preserved (NOT auto-deleted) so the user can manually merge or cherry-pick the non-overlapping commits. The worktree was removed and the recovery sentinel cleared.

WR-07 is a logic-altering correctness fix and WR-09 is a documented behavior-coupling note — flagged below for human verification.

## Fixed Issues

### BL-01: Integration test calls a non-existent Bybit endpoint

**Files modified:** `tests/integration/test_fresh_clone_round_trip.py`
**Commit:** `c172465` (this run, on `gsd-reviewfix/02-30801`); also already applied as `c102a44` on `sync/cherry-picks-2026-05-05` from iteration-1 (overlapping; the iteration-2 commit is functionally identical and can be skipped during cherry-pick).
**Applied fix:** Renamed `/api/v1/market/tickers` (plural, 404) to `/api/v1/market/ticker` (singular, matches the route at `services/bybit-connector/app/main.py:741`) at lines 44 and 141.

### BL-02: bootstrap.sh and integration suite require profile-gated services

**Files modified:** `bootstrap.sh`
**Commit:** `1298eaa` (this run); also already applied as `884ca4d` on `sync/cherry-picks-2026-05-05` from iteration-1 (overlapping).
**Applied fix:** Added `--profile ml --profile analytics` to both `docker compose up -d` invocations in bootstrap.sh (Step 4, both `--no-build` and full-build branches). Activates `ml-prediction:8007` (`profiles: [ml]`) and `sentiment-analysis:8008` (`profiles: [analytics]`) which the `[5/6]` health probe expects and the `bootstrap_stack` fixture iterates over. Env flags like `ENABLE_ML_PREDICTIONS=true` do NOT activate compose profiles — the CLI flag is the only mechanism.

### BL-03: CI Telegram secrets never reach the notification container

**Files modified:** `docker-compose.unified.yml`, `services/notification-service/app/config.py`
**Commits:** `6fa0d9d` (compose rename — same change iteration-1 made as `63a39c2`, this iteration produced an overlapping commit), `76e6c63` (Pydantic AliasChoices follow-up, NEW in this iteration — not in iteration-1).
**Applied fix (two commits):**
1. **`6fa0d9d` / `63a39c2`** — Renamed compose env vars from `TELEGRAM_TEST_BOT_TOKEN`/`TELEGRAM_TEST_CHAT_ID` to `TEST_TELEGRAM_BOT_TOKEN`/`TEST_TELEGRAM_CHAT_ID` at lines 641-642 so they match the workflow exports and reach the container. (Done in iteration-1 too.)
2. **`76e6c63`** — Added Pydantic `AliasChoices` to `telegram_bot_token` and `telegram_chat_id` in `services/notification-service/app/config.py`. **Without this commit, BL-03 was incomplete end-to-end** — even after the compose rename, the env var arrived inside the container but Pydantic Settings still looked up the field as `TELEGRAM_BOT_TOKEN` (NOT `TEST_TELEGRAM_BOT_TOKEN`), so the field was empty and the failure mode was identical to pre-fix. AliasChoices accepts either env var name, with `TELEGRAM_BOT_TOKEN` listed first so dev/.env precedence is preserved.

REVIEW.md flagged the AliasChoices need in BL-03's last paragraph and called it out of scope; the iteration-1 fix took that scoping at face value. Verified the AliasChoices behavior with a smoke test: only `TEST_TELEGRAM_BOT_TOKEN` set → reads test value (CI path); only `TELEGRAM_BOT_TOKEN` set → reads prod value (dev path); both set → `TELEGRAM_BOT_TOKEN` wins (dev safety); neither → empty default + existing `_validate_enabled_channels_have_creds` catches it.

**Cherry-pick note:** since `63a39c2` is already on `sync/cherry-picks-2026-05-05` covering the same compose rename, only `76e6c63` is needed from `gsd-reviewfix/02-30801` to fully close BL-03.

### BL-04: bybit-connector CORS — `allow_origins=["*"]` with `allow_credentials=True`

**Files modified:** `services/bybit-connector/app/config.py`, `services/bybit-connector/app/main.py`
**Commit:** `75013b9` (this run); also already applied as `3bd8d55` on `sync/cherry-picks-2026-05-05` from iteration-1.
**Applied fix:** Added `cors_origins` and `internal_service_origins` Pydantic fields to bybit-connector `Settings`, plus an `all_cors_origins` property — mirrors the trading-engine pattern at `services/trading-engine/app/config.py:588-670` exactly. Then replaced `allow_origins=["*"]` with `allow_origins=settings_instance.all_cors_origins` in main.py CORSMiddleware. Default origins match the trading-engine list (localhost frontend + internal service ports 8000-8008) so api-gateway and frontend continue to work.

Note: project formatter reflowed long-line `Field(...)` declarations elsewhere in `services/bybit-connector/app/config.py` during the edit. These are cosmetic-only changes (one logical statement per declaration, unchanged defaults/descriptions) and were committed alongside the CORS additions; the CORS additions themselves are the only semantic change.

### WR-01: `iter-fix-check-diff.sh` threshold-lowering regex is one-sided

**Files modified:** `scripts/iter-fix-check-diff.sh`, `tests/scripts/test_iter_fix.sh`
**Commit:** `061b53d` (NEW in this iteration)
**Applied fix:** Extended `THRESHOLD_RE` to capture both `<`/`<=` and `>`/`>=` operators, with the operator at `BASH_REMATCH[1]` and the numeric at `BASH_REMATCH[2]`. Branched the relax-detection logic by direction: `<` lowered = new_num > old_num, `>` lowered = new_num < old_num. Operator must match between - and + lines (flipping `<` to `>` is a different change, not a relax). Added two test cases: T5b (`>` lowering refused) and T6b (`>` tightening allowed). All 10 cases pass (8 prior + 2 new) — verified by running `bash tests/scripts/test_iter_fix.sh`.

### WR-02: telegram_notifier.py — `[DEBUGGER:...]` print-style logger calls

**Files modified:** `services/notification-service/app/telegram_notifier.py`
**Commit:** `8e6d9a7` (NEW in this iteration)
**Applied fix:** Removed all 8 `[DEBUGGER:...]` lines (init + send_message entry/exit/before/after/success/error). Replaced with two structured log calls: one in `__init__` (using `extra={enabled, chat_id_set, token_set}`) and one in the success/error paths of `send_message` (using `extra={status_code, chat_id}` and `extra={error_type, error_msg}`). Conforms to project structured-logging convention. Stale line numbers removed.

### WR-03: file handle leak on `open()` in test_notification_delivery.py

**Files modified:** `tests/integration/test_notification_delivery.py`
**Commit:** `d95a113` (NEW in this iteration)
**Applied fix:** Wrapped the `open(p, encoding="utf-8").read()` call in a `with open(p, encoding="utf-8") as fh: text_content = fh.read()` context manager. Identical semantics, deterministic close, no longer flaky on Windows hosts.

### WR-04: bybit-connector `/metrics` endpoint dead try/except block

**Files modified:** `services/bybit-connector/app/main.py`
**Commit:** `e8174c0` (NEW in this iteration)
**Applied fix:** Removed the entire `try: pass except: pass` block from the `/metrics` endpoint. The breaker gauge is already kept in sync via the on-state-change callback (visible in main.py around line 222 + bottom-of-file comment), so no in-endpoint refresh is needed. Eliminates a bare `except:` which was on the project ban-list.

### WR-05: notification_test_mode default mismatch — local test hangs

**Files modified:** `docker-compose.unified.yml`
**Commit:** `8c63d59` (NEW in this iteration)
**Applied fix:** Changed compose default at line 639 from `${NOTIFICATION_TEST_MODE:-}` to `${NOTIFICATION_TEST_MODE:-record}`. The host conftest fixture already defaults to "record" (`tests/integration/conftest.py:230`). With the new default, out-of-the-box local `pytest tests/integration` runs match the host fixture and the container writes to `tests/.notifications.log` instead of falling through to live POST. CI workflows already export `NOTIFICATION_TEST_MODE=live` explicitly and remain unaffected.

### WR-06: force_signal integration test casing mismatch

**Files modified:** `tests/integration/test_fresh_clone_round_trip.py`
**Commit:** `d07f18e` (NEW in this iteration)
**Applied fix:** Changed `"action": "buy"` to `"action": "BUY"` at line 64. Picked the test-side fix (one literal change, contained) rather than adding a Pydantic validator that uppercases the field — the validator would change the public API contract for every consumer and is a wider blast radius for what is fundamentally a casing typo in this one test.

### WR-07: `_load_model` returns falsy on success-without-metadata path — flagged for verification

**Files modified:** `services/ml-prediction-service/app/ml_models/gru_predictor.py`, `services/ml-prediction-service/app/ml_models/gru_model.py`
**Commit:** `4c6b818` (NEW in this iteration)
**Status:** fixed: requires human verification (logic correctness change)
**Applied fix:** Restructured both files so the success path always returns `True` at the end of the try block. Moved `return True` outside the `if metadata_path.exists()` block, with an explicit `else` branch that logs a warning when the metadata sidecar is missing (partial-retrain indicator). The existing `test_model_reload.py:55-56` documented this exact trap.

**Why human verification is needed:** This changes the boolean return semantics of `_load_model` and therefore the value `_reload_if_stale` returns to its caller. Any code path that compared `_load_model()`'s return value as a 3-state proxy (truthy/falsy/None) — which is unlikely but possible — would now see consistent `True`/`False` only. Run `pytest services/ml-prediction-service/tests/test_model_reload.py` and any predictor-call sites to confirm there are no consumers depending on the previous "falsy on success-without-metadata" quirk.

### WR-08: notification_test_mode accepts arbitrary strings

**Files modified:** `services/notification-service/app/config.py`
**Commit:** `b70b883` (NEW in this iteration)
**Applied fix:** Changed type from `str` to `Literal["", "record", "live"]` and added `Literal` to the typing import. Pydantic now raises a `ValueError` at startup if the env var is set to a typo like `RECORD` or `Record`, instead of silently falling through to live POST. Defaults `""` and the new WR-05 `record` default both validate cleanly.

### WR-09: EMERGENCY_STOP / auto-trader coupling — flagged for verification

**Files modified:** `tests/integration/conftest.py`
**Commit:** `dbcb3e4` (NEW in this iteration)
**Status:** fixed: requires human verification (chose documentation over code change to preserve test isolation)
**Applied fix:** Documented the EMERGENCY_STOP / auto-trader coupling in the `bootstrap_stack` fixture's docstring. Explains that this suite intentionally bypasses the auto-trader (force_signal + direct notify-trade POST), notes that future tests requiring an armed auto-trader must clear the file themselves, and documents the WSL bind-mount race that can create a directory at the EMERGENCY_STOP mount point.

**Why human verification is needed:** REVIEW.md offered two options — clear the file in the fixture (Option A, code change) or document the coupling (Option B, doc change). I chose Option B because clearing the file would alter auto-trader state for every downstream test in the session, a wider semantic change than the original review intent. If the team prefers the active-clear approach (the trading-engine restart path becomes testable), a follow-up commit can add `(tmp_fresh_clone / "EMERGENCY_STOP").unlink(missing_ok=True)` after the health-probe loop and before `yield` in the fixture.

## Skipped Issues

None — all 13 in-scope findings (4 Blocker + 9 Warning) were addressed across iterations 1 and 2.

## Branch State at End of Run

- **All 14 iteration-2 fix commits** live on `gsd-reviewfix/02-30801` (this agent's worktree branch, preserved on divergence).
- The agent's transactional cleanup tail attempted `git merge --ff-only gsd-reviewfix/02-30801` into `sync/cherry-picks-2026-05-05` and **failed with "Diverging branches can't be fast-forwarded"**. Cause: the iteration-1 manual fixes (`c102a44`, `884ca4d`, `63a39c2`, `3bd8d55`) for BL-01..BL-04 had already landed on `sync/cherry-picks-2026-05-05` from a different route, so this iteration's BL-01 (`c172465`) and BL-02 (`1298eaa`) commits create a divergence the FF cannot resolve.
- Per the agent protocol, the temp branch is preserved (NOT auto-deleted on divergence) so the user can manually merge or cherry-pick. The worktree was removed and the recovery sentinel cleared.

### Suggested merge — minimal cherry-pick (recommended)

The iteration-1 commits already cover BL-01, BL-02, BL-04 (and the compose part of BL-03) on `sync/cherry-picks-2026-05-05`. Only the iteration-2-NEW commits need to land:

```bash
# From the main repo on sync/cherry-picks-2026-05-05:
git cherry-pick \
  76e6c63 \  # BL-03 follow-up (Pydantic AliasChoices) — REQUIRED to actually close BL-03
  061b53d \  # WR-01 anti-mock guard `>` direction
  8e6d9a7 \  # WR-02 [DEBUGGER:...] removal
  d95a113 \  # WR-03 context manager
  e8174c0 \  # WR-04 dead try/except removal
  8c63d59 \  # WR-05 NOTIFICATION_TEST_MODE default
  d07f18e \  # WR-06 BUY casing
  4c6b818 \  # WR-07 _load_model return True (NEEDS HUMAN VERIFICATION)
  b70b883 \  # WR-08 Literal[] for notification_test_mode
  dbcb3e4    # WR-09 docstring (NEEDS HUMAN VERIFICATION)
```

After landing, verify by re-running:
- `bash tests/scripts/test_iter_fix.sh` — should report 10 PASS / 0 FAIL
- `pytest services/ml-prediction-service/tests/test_model_reload.py` — confirms WR-07 logic change
- Read `services/notification-service/app/config.py` and check `AliasChoices(...)` is present on `telegram_bot_token` and `telegram_chat_id` — confirms BL-03 is end-to-end fixed

### Alternative — full merge

If the team prefers a single merge commit:

```bash
git -C /mnt/d/Bimo_max/crypto-trading-bot merge gsd-reviewfix/02-30801
```

Will produce a merge commit with both iteration-1 and iteration-2 BL-* fixes overlapping but git will resolve them as no-op (same content). The merge is non-destructive.

### Cleanup after merge

After verifying the merge or cherry-picks land cleanly:

```bash
git branch -D gsd-reviewfix/02-30801
```

---

_Fixed: 2026-05-08T14:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
_Supersedes: iteration-1 report (4 BLOCKERS applied, 9 WARNINGS deferred)_
