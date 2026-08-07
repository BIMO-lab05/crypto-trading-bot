# backtesting/killtests/

Permanent, re-runnable harness answering the two remaining Phase 0 audit
hypotheses (`AUDIT.md` §7, rows H3/H4) with evidence. Design spec:
`docs/superpowers/specs/2026-08-05-phase4-measurement-h3-h4-design.md`
(read the `## Amendments` section — it corrects three implementation details
against the original design).

## What each module does

| Module | Role |
|---|---|
| `entries.py` | Extracts the 13 CLOSED paper positions from Postgres once, into the committed fixture `fixtures/closed_entries_2026-08.json` (with a provenance block). H3's primary run never touches the DB. |
| `candles.py` | `CandleStore` — loads backfilled kline CSVs (`backtesting/data/`), validates `is_mainnet`/gaps/dedup, serves as-of slices (no look-ahead). |
| `h3_atr_replay.py` | H3 kill test: replays entries (the 13 real ones, or synthetic ones built from a signal series via `--entries-from-series`) through ATR-derived stop/TP brackets, both 1.5×/2.5× variants, using a purpose-built bracket walker that copies `BacktestEngine`'s stop-first intrabar rule. |
| `offline_ensemble.py` | ASGI-seam driver: runs the real deployed TA app + `SignalAggregator` + `MultiStrategyEnsemble` in-process against backfilled CSVs, walking the 60m bar-close clock, to produce a signal series. This is the expensive one (~0.5–0.9s per decision bar). |
| `h4_information.py` | H4 kill test: scores a signal series against sign-of-24h-forward-log-return, directional accuracy + DSR (via CPCV) against the audit's ≥8-configuration floor. Gated on an H3 verdict existing and a same-day golden-parity stamp. |
| `report.py` | Emits dated verdict files (`.md` + `.json`) to `.planning/evidence/killtests/`. |
| `backfill_manifest.py` | Coverage/hash manifest over the backfilled CSVs — run after any refresh. |

## The three run commands

**H3 (primary, 13 real entries — cheap, seconds):**
```bash
python3 backtesting/killtests/h3_atr_replay.py --data-dir backtesting/data
```

**H3 secondary (regenerated entries from a signal series — larger n, same exit design):**
```bash
python3 backtesting/killtests/h3_atr_replay.py --data-dir backtesting/data \
  --entries-from-series .planning/evidence/killtests/signal-series.csv
```
Writes a separate `H3-secondary` verdict — never merged into the primary
n=13 verdict (spec §5 staged item).

**Signal series (expensive — hours; see gate chain below for why this runs first):**
```bash
PYTHONPATH=backtesting python3 backtesting/killtests/offline_ensemble.py \
  --data-dir backtesting/data --out .planning/evidence/killtests/signal-series.csv
```
`main()` builds one `CandleStore` for all `--symbols` and writes ONE csv at
the end — there is no built-in per-symbol partial write/resume despite what
earlier task instructions assumed. To bound the cost of an interruption,
invoke it once per symbol with `--symbols <ONE_SYMBOL>` and a distinct
`--out` path, sequentially, then concatenate with `pandas.concat` (not shell
`cat` — per-file headers would land as data rows). `load_stack()` pins
`StrategyPerformanceWeights` to a fixed ⅓/⅓/⅓ and asserts it, so running
symbols as separate processes is measurement-equivalent to one multi-symbol
process — no state carries across symbols in the monolithic path that a
fresh process would lose.

**H4:**
```bash
python3 backtesting/killtests/h4_information.py \
  --series .planning/evidence/killtests/signal-series.csv --data-dir backtesting/data
```

All host-run, all `--no-cov`.

## The gate chain

```
H3 verdict exists  ──┐
                      ├──► H4 CLI will run (--force overrides either gate,
golden-parity stamp ──┘     logging a caveat in the verdict)
  (same calendar date,
   >=1 non-HOLD signal
   in the parity chain)
```

The stamp comes from:
```bash
python3 -m pytest tests/killtests/test_golden_parity.py -m golden --no-cov
```
This requires the docker stack up (`docker compose -f docker-compose.unified.yml up -d`)
— it skips loudly otherwise. Run it **on its own**, not folded into a wider
pytest invocation: the minting rule below counts failures session-wide, so an
unrelated failing test elsewhere in the same session will (deliberately)
produce a `passed: false` stamp.

**Who writes the stamp, and when.** Nothing inside `test_golden_parity.py`
writes it. Each parity test records that it started and (on its last line)
that it passed; `tests/killtests/conftest.py::pytest_sessionfinish` then
applies the rules in `backtesting/killtests/parity_stamp.py`:

| Session outcome | Stamp |
|---|---|
| module skipped (stack down), or collected but no parity test executed (`-m "not golden"`, `-k`) | untouched |
| any failure/error in the session, or a required parity test that did not reach its last line | `passed: false`, with `refused_because` naming the reason |
| clean, but all-HOLD across every symbol | not written (spec §7.1 — the ensemble legs were never exercised; an earlier same-day pass stays valid) |
| clean, ≥1 non-HOLD chain action | `passed: true` |

Until 2026-08-07 the stamp was written by an ordinary test whose only
condition was "some chain action was recorded" — pytest runs that test even
when the parity assertions above it fail, so a session that had just proven
the seam BROKEN could still mint `passed: true` and open the H4 gate. The
stamp is now self-describing (test outcomes, symbols, observed actions, data
dir + its content fingerprint, backfill-manifest sha256) so a reader can tell
what a given stamp actually certifies. Its full manifest digest corresponds
to the first 12 characters recorded in each verdict's `input_hashes`.

**Freshness discipline for the stamp run.** The live leg always answers at
the current latest closed bar, so the offline leg's CSVs must reach the same
bar for every interval the chain touches (15/60/240/D). Two rules:

1. Refetch immediately before the parity run and finish both inside one 15m
   bar (bar boundaries :00/:15/:30/:45 — fetch + suite ≈ 7 min, so start
   right after a boundary).
2. If the canonical `backtesting/data` must stay frozen (it is the recorded
   provenance of an in-flight or completed signal-series run), fetch a
   throwaway parity copy instead and point the suite at it:
   ```bash
   mkdir -p backtesting/data-parity   # gitignored
   for iv in 15 60 240 D; do python3 backtesting/bybit_data_fetcher.py \
     --multiple BTCUSDT ETHUSDT SOLUSDT BNBUSDT ADAUSDT --interval $iv \
     --days 365 --schema klines --out-dir backtesting/data-parity; done
   # rename *_Dm_* -> *_1440m_* as usual, then:
   KILLTESTS_DATA_DIR=backtesting/data-parity python3 -m pytest \
     tests/killtests/test_golden_parity.py -m golden --no-cov
   ```
   The stamp certifies seam parity (code-path equivalence at the live latest
   bar), not the identity of a CSV snapshot, so a parity copy is sound.

The live leg also reads whatever TimescaleDB holds. Collection-downtime
holes there make deep-window indicators (trend filter, 240m × 300 bars)
genuinely diverge from contiguous Bybit history — that is a live data
defect, not a seam bug; see
`.planning/evidence/killtests/db-repair-2026-08-06.md` for the repair
procedure used on 2026-08-06 (174,776 missing bars filled from validated
mainnet CSVs). It compares the offline ASGI replay against the
live running TA (`:8004`) + market-data (`:8002`) stack: candle window
equality, every active indicator endpoint, and the full aggregator+ensemble
chain, for 3 golden symbols (BTC, SOL, ADA). The stamp file
(`.planning/evidence/killtests/golden-parity-stamp.json`) is only written if
parity passed **and** at least one of the three chain-parity actions was
non-HOLD (spec §7.1) — an all-HOLD live market passes parity but leaves H4
gated until a re-run catches a live non-HOLD signal, or an operator invokes
`h4_information.py --force`.

## Where verdicts land

`.planning/evidence/killtests/<TEST_ID>-verdict-<YYYYMMDD>.{md,json}` —
`h4_information.py`'s gate reads the latest `H3-verdict-*.json` by filename
glob, so `H3-secondary-verdict-*.json` does not satisfy (or shadow) the H3
order gate; only a primary `H3` verdict does.
`backfill-manifest-2026-08.md` carries per-CSV row counts, gap counts, and
sha256 digests — hashed itself into every verdict's `input_hashes` as
provenance.

The signal-series CSV itself is **not** committed if it exceeds 5 MB (a full
12-month × 5-symbol run is ~42k rows and does exceed it) — record its row
count and sha256 in the run report / verdict `input_hashes` instead, and add
it to `.gitignore` if not already covered.

## Re-run policy

Any engine change that trips `tests/killtests/test_preservation.py` (the
known-bug pins on the deployed signal path — no confidence gate, ATR always
None on the live path, `atr_stop_loss`/`atr_take_profit` unproduced,
confidence able to exceed 1.0, MTF consensus action never applied, etc.)
means the replay is no longer measuring the instrument it was built to
measure. Do not "fix" `test_preservation.py` to green silently — it exists
so a real engine fix breaks the harness loudly. When it fails:

1. Re-baseline: update the offline replay/shims consciously to match the new deployed behavior.
2. Re-run the full chain: fresh CSV backfill → golden-parity stamp → signal series → H4 → (H3 if entries or exit logic changed).
3. Standing verdict files are dated and never overwritten in place — a re-run produces a new dated verdict; old ones stay as historical record, not silently superseded.

Also re-run if the backfilled CSVs go stale relative to the live stack —
`test_candle_window_equality` (part of the golden-parity suite) catches this
directly (`only N/50 overlapping candles — backfill stale? refresh it`); if
it fails on staleness alone (not a genuine signal/indicator divergence),
refresh via `bybit_data_fetcher.py --multiple <5 symbols> --interval <iv>
--days 365 --schema klines --out-dir backtesting/data` for all 4 intervals
(`15`, `60`, `240`, `D` — not `1440`, which is not a valid Bybit v5 interval
value and silently returns 0 rows; rename `{sym}_Dm_...` → `{sym}_1440m_...`
after), then regenerate the manifest.
