---
phase: 01-bootstrap-recorded-tape
plan: 01
subsystem: infra
tags: [bybit, jsonl, fixtures, tape, klines, ticker, recorded-tape]

# Dependency graph
requires: []
provides:
  - 10 JSONL tape fixtures (5 symbols x 2 feeds) under tests/fixtures/tape/
  - scripts/tape/capture_bybit.py — re-runnable public-endpoint-only capture script
affects:
  - 01-02 (tape replay client reads these files)
  - 01-03 (bootstrap.sh bind-mounts tests/fixtures/tape/)
  - any plan that boots bybit-connector in tape mode

# Tech tracking
tech-stack:
  added: [requests (stdlib only — no new deps)]
  patterns:
    - JSONL-per-(feed,symbol) with tape_version=1 header (D-07)
    - Paginated backward window traversal for Bybit V5 kline (200 candles/request, sort ascending before write)

key-files:
  created:
    - scripts/tape/capture_bybit.py
    - tests/fixtures/tape/klines/BTCUSDT.jsonl
    - tests/fixtures/tape/klines/ETHUSDT.jsonl
    - tests/fixtures/tape/klines/SOLUSDT.jsonl
    - tests/fixtures/tape/klines/BNBUSDT.jsonl
    - tests/fixtures/tape/klines/ADAUSDT.jsonl
    - tests/fixtures/tape/ticker/BTCUSDT.jsonl
    - tests/fixtures/tape/ticker/ETHUSDT.jsonl
    - tests/fixtures/tape/ticker/SOLUSDT.jsonl
    - tests/fixtures/tape/ticker/BNBUSDT.jsonl
    - tests/fixtures/tape/ticker/ADAUSDT.jsonl
  modified: []

key-decisions:
  - "Used parents[2] (not parents[1] as written in PLAN.md) for OUTPUT_DIR because script lives at scripts/tape/ (2 levels deep from repo root)"
  - "Captured 2016 candles per symbol (11 x 200-candle chunks, last chunk = 16) covering 2026-04-29..2026-05-06"
  - "No new Python dependencies required — requests already present in repo"

patterns-established:
  - "Tape JSONL line 1: header object {tape_version:1, captured_at, source:bybit-mainnet, symbol, feed}"
  - "Kline data lines: raw Bybit V5 list-of-strings [ts_ms, open, high, low, close, volume, turnover]"
  - "Ticker data lines: raw Bybit V5 ticker dict from result.list[0]"

requirements-completed: [INFRA-03]

# Metrics
duration: 8min
completed: 2026-05-07
---

# Phase 01 Plan 01: Tape Fixtures Capture Summary

**Captured 7-day Bybit mainnet 5m klines + ticker snapshots for 5 validated symbols into 10 JSONL fixtures (844KB total) using a re-runnable public-endpoint-only Python script**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-06T22:55:44Z
- **Completed:** 2026-05-06T23:03:57Z
- **Tasks:** 2
- **Files modified:** 11 (1 script + 10 JSONL fixtures)

## Accomplishments
- Created `scripts/tape/capture_bybit.py` — re-runnable, public-only, exits 0 on full success, exits non-zero on any API error. Supports `--dry-run` for connectivity validation without writing files.
- Captured 2016 x 5m klines per symbol (11 paginated requests of 200 each, 16-candle final chunk) spanning 2026-04-29 to 2026-05-06, sorted ascending before write.
- Captured 1 ticker snapshot per symbol from `/v5/market/tickers` (single point-in-time, sufficient for replay — replay client serves the same snapshot on every request in tape mode).
- All 10 JSONL files: line 1 is a `tape_version=1` header; klines files have 2017 lines (header + 2016 candles); ticker files have 2 lines (header + 1 record). Total: 844KB (well under 50MB cap, no git-lfs needed).
- Zero auth credentials in the script (verified via grep gate).

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement capture_bybit.py** - `7b5b35d` (feat(tape))
2. **Task 2: Run capture script and commit all 10 JSONL fixtures** - `b71b909` (chore(tape))

**Plan metadata:** `docs(phase-01-plan-01): summary` (this commit)

## Files Created/Modified
- `scripts/tape/capture_bybit.py` — Bybit mainnet capture script (public endpoints only, D-05)
- `tests/fixtures/tape/klines/BTCUSDT.jsonl` — 2017 lines, 7d 5m klines
- `tests/fixtures/tape/klines/ETHUSDT.jsonl` — 2017 lines, 7d 5m klines
- `tests/fixtures/tape/klines/SOLUSDT.jsonl` — 2017 lines, 7d 5m klines
- `tests/fixtures/tape/klines/BNBUSDT.jsonl` — 2017 lines, 7d 5m klines
- `tests/fixtures/tape/klines/ADAUSDT.jsonl` — 2017 lines, 7d 5m klines
- `tests/fixtures/tape/ticker/BTCUSDT.jsonl` — 2 lines, single snapshot
- `tests/fixtures/tape/ticker/ETHUSDT.jsonl` — 2 lines, single snapshot
- `tests/fixtures/tape/ticker/SOLUSDT.jsonl` — 2 lines, single snapshot
- `tests/fixtures/tape/ticker/BNBUSDT.jsonl` — 2 lines, single snapshot
- `tests/fixtures/tape/ticker/ADAUSDT.jsonl` — 2 lines, single snapshot

## Decisions Made

- **OUTPUT_DIR path fix (Rule 1 - auto-fix):** PLAN.md specified `Path(__file__).resolve().parents[1]` for OUTPUT_DIR, but `capture_bybit.py` lives at `scripts/tape/` — two levels deep — so `parents[1]` would have pointed to `scripts/` not the repo root. Used `parents[2]` instead. This is a silent path bug that would have produced files in `scripts/tests/fixtures/tape/` (wrong location, Task 2 acceptance criteria would fail). Fixed before first commit; documented here.
- No new Python dependencies: `requests` is already used in `scripts/collect_bybit_direct_180days.py`; `stdlib` only otherwise.
- Opted for `--dry-run` flag (advisory, not mandatory) to enable connectivity validation without writing files. Plan did not specify this but it costs nothing and helps operators verify API reachability before a full capture.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Incorrect OUTPUT_DIR path in plan spec**
- **Found during:** Pre-write review (advisor call before Task 1)
- **Issue:** Plan action specified `parents[1]` for OUTPUT_DIR when script is at `scripts/tape/capture_bybit.py`. `parents[1]` = `scripts/`, not repo root. Would have written fixtures to `scripts/tests/fixtures/tape/` — wrong location.
- **Fix:** Used `parents[2]` (= repo root worktree dir). Verified with Python path resolution check before writing.
- **Files modified:** `scripts/tape/capture_bybit.py`
- **Verification:** `python3 -c "from pathlib import Path; p = Path(...).resolve(); print(p.parents[2] / 'tests' / 'fixtures' / 'tape')"` confirmed correct path.
- **Committed in:** `7b5b35d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — path resolution)
**Impact on plan:** Essential fix. Without it, Task 2 acceptance gate `test -f tests/fixtures/tape/klines/BTCUSDT.jsonl` would have failed. No scope creep.

## Issues Encountered

None — Bybit mainnet API responded without rate-limit errors; all 11 paginated chunks per symbol returned data on first attempt. Total network time ~84 seconds for 5 symbols.

## Self-Check: PASSED

All verification gates from the plan verified:

| Check | Result |
|-------|--------|
| `ls tests/fixtures/tape/klines/*.jsonl` — exactly 5 files | PASS |
| `ls tests/fixtures/tape/ticker/*.jsonl` — exactly 5 files | PASS |
| `head -1 tests/fixtures/tape/klines/BTCUSDT.jsonl` contains `tape_version=1` | PASS |
| `wc -l tests/fixtures/tape/klines/BTCUSDT.jsonl` = 2017 (> 2000) | PASS |
| `python3 scripts/tape/capture_bybit.py --help` exits 0 | PASS |
| `du -sh tests/fixtures/tape/` = 844K (under 50MB) | PASS |
| `git log --oneline -5` — 2 atomic commits visible | PASS |
| `grep -r "BYBIT_API_KEY\|api_key" scripts/tape/` returns empty | PASS |
| No XRP/DOGE fixtures present | PASS |

## User Setup Required

None — no external service configuration required. The capture script requires only network access to `api.bybit.com` (public endpoints, no API key).

## Next Phase Readiness
- Ready for Plan 01-02: `bybit-connector` tape replay loader can read these JSONL files directly. Contract: line 1 parses as `{tape_version: 1, ...}`; subsequent lines are raw Bybit V5 list-of-strings (klines) or ticker dicts.
- Per D-06: tape is frozen at capture time. Future refresh = re-run `python3 scripts/tape/capture_bybit.py` + new commit. No automated refresh.

---
*Phase: 01-bootstrap-recorded-tape*
*Completed: 2026-05-07*
