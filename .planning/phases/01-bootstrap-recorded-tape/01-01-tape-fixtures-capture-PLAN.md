---
phase: 01-bootstrap-recorded-tape
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
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
autonomous: true
requirements: [INFRA-03]

must_haves:
  truths:
    - "Capture script can be re-run to refresh tape from Bybit mainnet REST without manual editing"
    - "Each JSONL fixture's first line is a tape-version=1 header that loaders can verify before replay"
    - "Klines fixtures contain 5-minute candles spanning ~7 days for the 5 validated symbols (BTC, ETH, SOL, BNB, ADA)"
    - "Capture script sends NO Bybit API key/secret on the wire (public endpoints only) and never logs auth headers"
    - "D-01: storage format = JSONL per (feed, symbol), one file per pair (e.g. tests/fixtures/tape/klines/SOLUSDT.jsonl) — human-greppable, diffable, matches Bybit REST/WS payload shape"
    - "D-03: scope = 5 validated symbols (BTC, ETH, SOL, BNB, ADA) × 7 days, 5m kline cadence + ticker snapshots, target tape size <50 MB so it stays in-repo"
    - "D-04: storage location = tests/fixtures/tape/ checked into git; no git-lfs in v1, revisit if size grows"
    - "D-05: capture method = committed script scripts/tape/capture_bybit.py hits live Bybit mainnet REST (/v5/market/kline, /v5/market/tickers) and writes JSONL; operator runs manually and commits output"
    - "D-06: refresh cadence = manual on demand only (no nightly auto-refresh — would break replay determinism for older test runs); tape SHA tracked in git"
    - "D-07: schema versioning = first line of every JSONL is a header object {tape_version:1, captured_at, source:bybit-mainnet, symbol, feed}; loader rejects mismatched tape_version"
  artifacts:
    - path: "scripts/tape/capture_bybit.py"
      provides: "Reproducible Bybit mainnet kline + ticker capture into JSONL fixtures"
      contains: "BYBIT_API_ENDPOINT = 'https://api.bybit.com'"
    - path: "tests/fixtures/tape/klines/SOLUSDT.jsonl"
      provides: "Replay-able 5m kline tape for SOLUSDT, ~7 days"
      contains: "\"tape_version\": 1"
    - path: "tests/fixtures/tape/ticker/SOLUSDT.jsonl"
      provides: "Replay-able ticker snapshot tape for SOLUSDT"
      contains: "\"feed\": \"ticker\""
  key_links:
    - from: "scripts/tape/capture_bybit.py"
      to: "tests/fixtures/tape/{klines,ticker}/<SYMBOL>USDT.jsonl"
      via: "open(path, 'w') write JSONL line-per-record"
      pattern: "tests/fixtures/tape/(klines|ticker)/[A-Z]+USDT\\.jsonl"
---

<objective>
Capture deterministic, in-repo recorded-tape fixtures for the 5 validated symbols (BTC, ETH, SOL, BNB, ADA) covering klines (5-minute) + ticker over a 7-day window from Bybit mainnet public REST. Commits both the capture script (re-runnable on demand) and the resulting 10 JSONL files (5 symbols x 2 feeds) so downstream services can boot offline against deterministic data.

Purpose: Decouple the deterministic test/CI lane from live Bybit availability (per CONTEXT.md D-01..D-08). The replay client built in plan 02 reads these files; bootstrap.sh in plan 03 boots the stack against them.
Output: One executable Python capture script + 10 JSONL fixtures committed under `tests/fixtures/tape/`.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md
@.planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md

<interfaces>
<!-- Tape JSONL schema (D-01, D-07) the loader in plan 02 will read: -->
<!-- LINE 1 (header) — JSON object with EXACT keys: -->
<!--   {"tape_version": 1, "captured_at": "<ISO8601 UTC>", "source": "bybit-mainnet", "symbol": "<SYMBOL>USDT", "feed": "klines" | "ticker"} -->
<!-- LINES 2..N — for klines: raw Bybit V5 list-of-strings  ["timestamp_ms", "open", "high", "low", "close", "volume", "turnover"] -->
<!--               for ticker: raw Bybit V5 ticker dict from /v5/market/tickers result.list[i] -->

From services/bybit-connector/app/bybit_rest_client.py (signatures the tape feeds via this format):
  async def get_kline(category, symbol, interval, limit=200, start_time=None, end_time=None) -> List[List[str]]
  async def get_ticker(category="linear", symbol=None) -> Dict[str, Any]   # returns {"list": [...], ...}

Validated symbol set (CLAUDE.md "Project rules / Validated symbols", D-03):
  BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement capture_bybit.py (D-01..D-08, D-03 symbol set)</name>
  <files>scripts/tape/capture_bybit.py</files>
  <read_first>
    - scripts/collect_bybit_direct_180days.py (analog: REST V5 kline pagination + rate-limit pacing — copy the params/url/header style)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (decisions D-01..D-08, especially D-03, D-05, D-07)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section "scripts/tape/capture_bybit.py" — quotes lines 1-38, 41-71, 89-118 of the analog)
    - services/bybit-connector/app/bybit_rest_client.py (lines 509-563 — get_kline + get_ticker wire shape that capture must mirror)
  </read_first>
  <action>
    Create `scripts/tape/capture_bybit.py` (executable Python 3.11+, shebang `#!/usr/bin/env python3`). Mirror the structure of `scripts/collect_bybit_direct_180days.py` but write JSONL fixtures instead of CSV+DB.

    EXACT constants (do not parameterize away from these):
      SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT']     # D-03 — 5 validated symbols only
      INTERVAL = '5'                                                          # D-03 — 5-minute klines
      DAYS = 7                                                                # D-03 — 7-day window
      BYBIT_API_ENDPOINT = 'https://api.bybit.com'                           # D-05 — mainnet REST
      RATE_LIMIT_DELAY = 0.5
      OUTPUT_DIR = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'tape'

    Two collectors:
      1. capture_klines(symbol):
         - Hit GET /v5/market/kline with params {"category": "linear", "symbol": symbol, "interval": "5", "start": <start_ms>, "end": <end_ms>, "limit": 200}.
         - Paginate backwards until 7 days of 5m candles are collected (~2016 candles per symbol).
         - Sort ascending by timestamp before write.
         - Write to {OUTPUT_DIR}/klines/{symbol}.jsonl. LINE 1 = header object per D-07:
             {"tape_version": 1, "captured_at": "<datetime.now(timezone.utc).isoformat()>", "source": "bybit-mainnet", "symbol": symbol, "feed": "klines"}
         - LINES 2..N = each kline as a JSON array (Bybit V5 raw list-of-strings):
             ["<ts_ms>", "<open>", "<high>", "<low>", "<close>", "<volume>", "<turnover>"]
      2. capture_ticker(symbol):
         - Hit GET /v5/market/tickers with params {"category": "linear", "symbol": symbol}.
         - Take 1 snapshot (Bybit's tickers endpoint returns the current snapshot, not historical). Loop is OK if you want multiple snapshots, but ONE is sufficient — replay client serves the same snapshot to every caller in tape mode.
         - Write to {OUTPUT_DIR}/ticker/{symbol}.jsonl. LINE 1 = header object per D-07 with `"feed": "ticker"`.
         - LINE 2 = the ticker dict from `result["list"][0]`.

    Auth + safety constraints (per threat model):
      - DO NOT send any auth headers. The script uses ONLY public endpoints (`/v5/market/kline`, `/v5/market/tickers`).
      - DO NOT read or print BYBIT_API_KEY / BYBIT_API_SECRET — script must work with completely empty env.
      - Use `requests.get(url, params=params, timeout=30)` with NO `headers={"X-BAPI-API-KEY": ...}` (compare to collect_bybit_direct_180days.py to confirm public-only style).
      - If the response status_code != 200 OR `data.get("retCode") != 0`, log error and exit non-zero. Do NOT swallow.

    main() prints a one-line summary per file written: `wrote {path} (lines={N})`. Returns exit 0 on full success, non-zero on any failure.

    Make script executable: `chmod +x scripts/tape/capture_bybit.py` after write (or rely on git fileMode).
  </action>
  <verify>
    <automated>python3 -c "import ast; ast.parse(open('scripts/tape/capture_bybit.py').read())" && grep -q "BYBIT_API_ENDPOINT = 'https://api.bybit.com'" scripts/tape/capture_bybit.py && grep -q "tape_version" scripts/tape/capture_bybit.py && grep -q "SYMBOLS = \['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT'\]" scripts/tape/capture_bybit.py && ! grep -E "BYBIT_API_KEY|BYBIT_API_SECRET|X-BAPI-API-KEY" scripts/tape/capture_bybit.py</automated>
  </verify>
  <done>
    Script parses cleanly, references the correct mainnet endpoint and the 5 validated symbols, includes the tape_version header schema, and contains zero references to API keys or auth headers.
  </done>
</task>

<task type="auto">
  <name>Task 2: Run capture script and commit all 10 JSONL fixtures (D-04, D-05)</name>
  <files>tests/fixtures/tape/klines/BTCUSDT.jsonl, tests/fixtures/tape/klines/ETHUSDT.jsonl, tests/fixtures/tape/klines/SOLUSDT.jsonl, tests/fixtures/tape/klines/BNBUSDT.jsonl, tests/fixtures/tape/klines/ADAUSDT.jsonl, tests/fixtures/tape/ticker/BTCUSDT.jsonl, tests/fixtures/tape/ticker/ETHUSDT.jsonl, tests/fixtures/tape/ticker/SOLUSDT.jsonl, tests/fixtures/tape/ticker/BNBUSDT.jsonl, tests/fixtures/tape/ticker/ADAUSDT.jsonl</files>
  <read_first>
    - scripts/tape/capture_bybit.py (just created in Task 1)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-04 storage location, D-05 capture method, D-06 manual on-demand refresh)
  </read_first>
  <action>
    1. Create the output directories: `mkdir -p tests/fixtures/tape/klines tests/fixtures/tape/ticker`.
    2. Run the capture script: `python3 scripts/tape/capture_bybit.py`. Expect ~30-60 seconds (10 REST requests with 0.5s pacing + kline pagination ~11 pages per symbol).
    3. If the run fails (network blip or rate-limit), retry up to 2 more times. If it still fails, STOP and report — do NOT manually fabricate fixtures.
    4. Verify each kline file has at least 2000 lines (header + ~2016 candles) and each ticker file has exactly 2 lines (header + 1 snapshot).
    5. Verify total tape size: `du -sh tests/fixtures/tape/` must be under 50 MB (D-04 budget — no git-lfs in v1).
    6. Stage all 10 JSONL files. Do NOT add `.env`, logs, or any other path.

    Per D-06 (manual refresh): committing these files freezes the tape. Future refreshes mean re-running the script + a NEW commit; bootstrap.sh in plan 03 never refreshes the tape automatically.
  </action>
  <verify>
    <automated>test -f tests/fixtures/tape/klines/BTCUSDT.jsonl && test -f tests/fixtures/tape/klines/ETHUSDT.jsonl && test -f tests/fixtures/tape/klines/SOLUSDT.jsonl && test -f tests/fixtures/tape/klines/BNBUSDT.jsonl && test -f tests/fixtures/tape/klines/ADAUSDT.jsonl && test -f tests/fixtures/tape/ticker/BTCUSDT.jsonl && test -f tests/fixtures/tape/ticker/ETHUSDT.jsonl && test -f tests/fixtures/tape/ticker/SOLUSDT.jsonl && test -f tests/fixtures/tape/ticker/BNBUSDT.jsonl && test -f tests/fixtures/tape/ticker/ADAUSDT.jsonl && head -1 tests/fixtures/tape/klines/SOLUSDT.jsonl | grep -q '"tape_version":\s*1' && head -1 tests/fixtures/tape/ticker/SOLUSDT.jsonl | grep -q '"feed":\s*"ticker"' && [ "$(wc -l < tests/fixtures/tape/klines/SOLUSDT.jsonl)" -gt 2000 ] && [ "$(du -sm tests/fixtures/tape | awk '{print $1}')" -lt 50 ]</automated>
  </verify>
  <done>
    All 10 JSONL files exist; line 1 of each file is a header containing `"tape_version":1`; ticker files declare `"feed":"ticker"`; each klines file is over 2000 lines; total tape size is under 50 MB.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| capture_bybit.py -> Bybit mainnet REST | Outbound HTTP to `api.bybit.com`; PUBLIC endpoints only — no auth, no PII outbound |
| capture_bybit.py -> tests/fixtures/tape/*.jsonl | File write to in-repo path; output is checked into git |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | I (Information disclosure) | scripts/tape/capture_bybit.py | mitigate | Script never reads or sends BYBIT_API_KEY / BYBIT_API_SECRET. Verify gate: `! grep -E "BYBIT_API_KEY\|BYBIT_API_SECRET\|X-BAPI-API-KEY" scripts/tape/capture_bybit.py` returns success (i.e. no matches). |
| T-01-02 | T (Tampering) | tests/fixtures/tape/*.jsonl | mitigate | Header schema includes `captured_at` ISO timestamp + `source: bybit-mainnet` so any future operator can grep file provenance. Loader in plan 02 enforces `tape_version == 1` (rejects mismatched). |
| T-01-03 | I (Information disclosure) | response logs | mitigate | Capture script logs only summary (`wrote {path} (lines={N})`); does NOT log raw HTTP headers or full response bodies (which on Bybit V5 public endpoints contain no sensitive data anyway, but discipline is consistent). |
| T-01-04 | D (Denial of service) | Bybit REST rate-limit | accept | RATE_LIMIT_DELAY=0.5 between requests; script is one-shot manual run (D-06), not in CI hot path. Exhausting Bybit public quota would block one developer for ~5 min. |
</threat_model>

<verification>
- `python3 scripts/tape/capture_bybit.py` exits 0 in a clean environment with NO `BYBIT_API_KEY`/`SECRET` set.
- All 10 JSONL files committed; line 1 of every file parses as valid JSON containing `tape_version=1`, `source="bybit-mainnet"`, and the matching `symbol` + `feed`.
- Total `tests/fixtures/tape/` size is under 50 MB (verified via `du -sm`).
- Capture script contains zero references to auth keys (verified via `grep -E "BYBIT_API_KEY|BYBIT_API_SECRET|X-BAPI-API-KEY"` returning empty).
- All 5 validated symbols are present in both `klines/` and `ticker/` directories. XRPUSDT and DOGEUSDT do NOT appear (per D-03 + CLAUDE.md "Validated symbols").
</verification>

<success_criteria>
- Capture script is re-runnable: a second `python3 scripts/tape/capture_bybit.py` invocation overwrites the JSONL files cleanly with fresher data, header `captured_at` timestamp updated.
- Loader in plan 02 can read line 1, decode as JSON, assert `tape_version == 1`, then iterate lines 2..N as kline arrays / ticker dicts without further parsing changes.
- Per D-06, refresh is manual: nobody automated this; the operator commits a new tape when they want one.
</success_criteria>

<output>
After completion, create `.planning/phases/01-bootstrap-recorded-tape/01-01-SUMMARY.md` summarizing the capture run timestamp, total fixture size, and any pagination retries that occurred.
</output>
