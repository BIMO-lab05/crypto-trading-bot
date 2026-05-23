# Phase 14: Mobile Responsive Dashboard - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 11 (4 CREATE + 7 MODIFY)
**Analogs found:** 9 / 11 (with strong matches in the codebase)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/audit_responsive.py` | script (CLI walker) | file-I/O (read JSX → write JSON) | `scripts/audit_bybit_bypass.py` | **exact** (same idiom: regex-dict, repo walk, sorted JSON emit, allowlist, `--out`) |
| `tests/e2e/test_responsive_dashboard.py` | test (e2e) | request-response (browser DOM probe) | `tests/e2e/test_path_to_live_smoke.py` | **role+flow match** (Playwright + viewport fixture); matrix parametrize from RESEARCH Pattern 2 |
| `tests/integration/test_no_mobile_hidden_data.py` | test (static gate) | file-I/O (grep + AST-ish scan) | `tests/integration/test_dashlive_grep_gates.py` | **exact** (dual-form pathlib + subprocess grep, scope discipline, REPO_ROOT idiom) |
| `responsive-audit.json` | artifact (output) | output of audit script | — | NO ANALOG (output, not source) |
| `frontend/tailwind.config.js` | config | build-time | self (existing extend block) | self-modify (insert top-level `screens:` sibling) |
| `frontend/src/components/Dashboard.jsx` | component (root layout) | render | self + RESEARCH Pattern 1 / UI-SPEC line 145 | self-modify (extend existing responsive pattern) |
| `frontend/src/components/PathToLiveTile.jsx` | component (tile) | render | self (existing chip-row markup) | self-modify (add reflow utilities to existing `flex` rows) |
| `frontend/src/components/KeyMetricsStrip.jsx` | component (strip) | render | self (line 284 already responsive grid) | self-modify (swap fixed grid for breakpoint-aware) |
| `frontend/src/pages/TournamentDashboard.jsx` | page (composition) | render | — | NO ANALOG for dual-render; Pitfall 5 + UI-SPEC line 148 specify shape |
| `frontend/src/components/TournamentFilterChips.jsx` | component (chips) | render | self (lines 165/196/227 — already `flexWrap: 'wrap'` in inline style) | self-modify (convert inline `flexWrap` to Tailwind + add 44px touch target) |
| `.github/workflows/dashboard-smoke.yml` | workflow (CI) | event-driven | self (extend single pytest step to matrix or 2 steps) | self-modify |

---

## Pattern Assignments

### `scripts/audit_responsive.py` (script, file-I/O)

**Analog:** `scripts/audit_bybit_bypass.py` — same role (Python CLI walker emitting JSON over `frontend/src/**/*.jsx`), same data flow.

**REPO_ROOT + BANNED_PATTERNS pattern** (lines 33–41):
```python
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Banned patterns per CONTEXT D-05.
BANNED_PATTERNS: dict[str, re.Pattern[str]] = {
    "pybit_import": re.compile(r"^\s*(from\s+pybit\b|import\s+pybit\b)", re.MULTILINE),
    "mainnet_rest_url": re.compile(r"https?://api\.bybit\.com"),
    "testnet_rest_url": re.compile(r"https?://api-testnet\.bybit\.com"),
    "wss_stream_url": re.compile(r"wss?://stream(?:-testnet)?\.bybit"),
}
```

**Walk + match + per-line collection** (lines 106–138):
```python
def collect_bypass_entries() -> list[dict[str, Any]]:
    """Walk the repo and emit one entry per banned-pattern match."""
    entries: list[dict[str, Any]] = []
    for py in REPO_ROOT.rglob("*.py"):
        if any(_is_under(py, exempt) for exempt in EXEMPT_DIRS):
            continue
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        rel_path = py.relative_to(REPO_ROOT).as_posix()
        # Skip the audit script itself — the regex literals it contains would
        # otherwise self-match. The script lives at scripts/audit_bybit_bypass.py.
        if rel_path == "scripts/audit_bybit_bypass.py":
            continue
        for kind, pattern in BANNED_PATTERNS.items():
            for m in pattern.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                lines = text.splitlines()
                snippet = lines[line_no - 1].strip() if line_no - 1 < len(lines) else ""
                entries.append(
                    {
                        "file": rel_path,
                        "line": line_no,
                        "kind": kind,
                        "current_call": snippet,
                        "replacement_path": _replacement_for(rel_path, kind),
                    }
                )
    entries.sort(key=lambda e: (e["file"], e["line"], e["kind"]))
    return entries
```

**`main()` + `--out` + JSON emit** (lines 141–165):
```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BC-01: Audit every Bybit-bypass site in the repo "
        "and emit JSON per the locked schema."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON to this path (default: stdout).",
    )
    args = parser.parse_args(argv)

    entries = collect_bypass_entries()

    if args.out is None:
        json.dump(entries, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2, sort_keys=False)
            fh.write("\n")

    return 0
```

**Adaptations for Phase 14:**
- Walk path is `REPO_ROOT / "frontend" / "src"` (not repo root); file glob is `*.jsx`.
- Allowlist file: `.planning/phases/14-mobile-responsive-dashboard/responsive-audit-allowlist.json`. Each entry has `file`, `line`, `reason` keys (compare RESEARCH Example 3 lines 550–557). Skip-only when `reason` field is non-empty (per CONTEXT.md "Allowlist entries permitted only with explicit `reason` field").
- Pattern set per RESEARCH Example 3 (lines 543–548): `w-[NNNpx]`, `min-w-[NNNpx]`, `max-w-[NNNpx]`, `width: NNNpx`.
- Output file path is `responsive-audit.json` at repo root by default (CONTEXT.md "Specifics"); `--out` overrides.
- Exit 0 if no unallowlisted hits, exit 1 otherwise (gate-friendly, mirrors `audit_bybit_bypass.py` script semantics).
- Self-exclusion guard (mirror line 121): skip the script itself so its regex literals don't self-match.

---

### `tests/e2e/test_responsive_dashboard.py` (test, request-response)

**Analog:** `tests/e2e/test_path_to_live_smoke.py` — same role (pytest-playwright e2e against gateway origin), same fixture infrastructure (`bootstrap_stack`, viewport via `browser_context_args`).

**Imports + module-level constants** (lines 22–31):
```python
from __future__ import annotations

import time
from datetime import date

import httpx
import pytest
from playwright.sync_api import expect

GATEWAY_ORIGIN = "http://localhost:8000"
```

**Viewport fixture pattern** (lines 39–42) — **OVERRIDE for matrix per RESEARCH Pattern 2**:
```python
# EXISTING SINGLE-VIEWPORT FORM (replace with matrix below):
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Match the dashboard's native viewport so layout-dependent tiles render."""
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}}
```

**Matrix viewport pattern from RESEARCH.md Pattern 2 (lines 247–285)** — **load-bearing for MOBILE-03**:
```python
# NEW MATRIX FORM (Phase 14):
VIEWPORTS = [
    {"viewport": {"width": 375, "height": 667},  "label": "iphone-se"},
    {"viewport": {"width": 768, "height": 1024}, "label": "ipad-portrait"},
]

@pytest.mark.parametrize(
    "browser_context_args",
    VIEWPORTS,
    indirect=True,           # ← routes to the fixture, not the test arg
    ids=[v["label"] for v in VIEWPORTS],
)
def test_no_horizontal_scroll(page, browser_context_args):
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")
    overflowing = page.evaluate("""
        () => {
          const innerW = window.innerWidth;
          const violators = [];
          document.querySelectorAll('[data-testid]').forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.x + rect.width > innerW) {
              violators.push({
                testid: el.getAttribute('data-testid'),
                right: rect.x + rect.width,
                innerWidth: innerW,
              });
            }
          });
          return violators;
        }
    """)
    assert overflowing == [], (
        f"{len(overflowing)} elements overflow window.innerWidth: {overflowing[:5]}"
    )
```

**Test body shape — locator + expect + asserts** (lines 73–142, lines 102–104, 132–134):
```python
@pytest.mark.usefixtures("bootstrap_stack", "tape_reset")
def test_path_to_live_tile_renders(page):
    # ...snapshot APIs before navigation...
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle", timeout=30000)

    # Assertion #1 — tile is visible
    tile = page.locator('[data-testid="path-to-live-tile"]')
    expect(tile).to_be_visible(timeout=15000)

    # ...iterate testids, build chip locators...
    for check in checks:
        chip_locator = page.locator(f'[data-testid="path-to-live-check-{check_name}"]')
        expect(chip_locator).to_be_visible(timeout=10000)
        chip_text = chip_locator.inner_text().strip()
        assert check_status in chip_text, (...)

    # Banner state-token assertion (reused verbatim for MOBILE-03 banner visibility)
    banner = page.locator('[data-testid="path-to-live-banner"]')
    expect(banner).to_be_visible(timeout=10000)
```

**Touch-target assertion pattern from RESEARCH.md Pattern 3 (lines 292–309)** — **NEW for Phase 14**:
```python
def test_touch_targets_44px(page, browser_context_args):
    page.goto(f"{GATEWAY_ORIGIN}/", wait_until="networkidle")
    failures = page.evaluate("""
        () => {
          const out = [];
          document.querySelectorAll('button, a, [role="button"]').forEach(el => {
            const h = el.getBoundingClientRect().height;
            if (h < 44 && el.offsetParent !== null) {
              out.push({tag: el.tagName, text: el.innerText.slice(0, 30), height: h});
            }
          });
          return out;
        }
    """)
    assert failures == [], f"{len(failures)} interactive targets below 44px: {failures[:5]}"
```

**Adaptations for Phase 14:**
- Replace the session-scoped `browser_context_args` override with the parametrized form (RESEARCH Pitfall 3 — never `playwright.devices['iPhone SE']` because that's 320×568 1st gen, not 375×667 2nd gen required by spec).
- Keep `@pytest.mark.usefixtures("bootstrap_stack")` decorator on test bodies (`tape_reset` not needed — no API state seeded for layout tests).
- Test functions to author: `test_no_horizontal_scroll`, `test_touch_targets_44px`, `test_banner_visible_without_scroll`, `test_dashboard_single_column_mobile`, `test_path_to_live_rows_full_width`, `test_key_metrics_2col`, `test_tournament_dual_render`. Each parametrized via the `VIEWPORTS` list (per RESEARCH "Phase Requirements → Test Map", lines 705–717).
- `page.evaluate()` single-pass JS over `[data-testid]` instead of N round-trips (RESEARCH "Don't Hand-Roll" table).

---

### `tests/integration/test_no_mobile_hidden_data.py` (test, file-I/O)

**Analog:** `tests/integration/test_dashlive_grep_gates.py` — same role (defence-in-depth grep gate), same data flow, same dual-form scan idiom.

**Module docstring + REPO_ROOT scoping** (lines 1–39):
```python
"""Phase 10 DASHLIVE — Path-to-LIVE defence-in-depth grep gates (D-10-20).

Two CI-enforced regression detectors per 10-CONTEXT.md decision D-10-20:
...
Both gates use a dual-form scan — pathlib ``rglob`` for cross-platform fidelity
AND a subprocess ``grep`` call to mirror the literal command an operator runs
locally. Pattern verbatim from tests/integration/test_preflight_grep_gates.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level constants — SCOPE IS LOAD-BEARING.
# ...
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
```

**Dual-form scan (pathlib + subprocess)** (lines 47–95):
```python
def test_path_to_live_tile_component_exists():
    """...Dual-form scan: pathlib `rglob` ... subprocess `grep -r` ..."""
    pattern = re.compile(r"PathToLiveTile")
    matches: list[str] = []

    for ext in ("*.jsx", "*.js"):
        for f in FRONTEND_SRC.rglob(ext):
            posix = f.as_posix()
            if "/tests/" in posix or "node_modules" in posix:
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            if pattern.search(text):
                matches.append(str(f.relative_to(FRONTEND_SRC)))

    assert matches, (
        "PathToLiveTile component removed from frontend. ..."
    )

    # Fidelity to the literal CI grep command. Scope MUST be FRONTEND_SRC.
    result = subprocess.run(
        ["grep", "-r", "PathToLiveTile", str(FRONTEND_SRC)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches for PathToLiveTile under {FRONTEND_SRC}. ..."
    )
```

**Target shape from RESEARCH Example 2 (lines 460–518)** — **load-bearing literal for Phase 14**:
```python
# tests/integration/test_no_mobile_hidden_data.py
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
ALLOWLIST_PATH = (
    REPO_ROOT / ".planning" / "phases"
    / "14-mobile-responsive-dashboard" / "mobile-hidden-allowlist.json"
)

# Forbidden: `hidden md:block`, `hidden md:flex`, `hidden lg:grid`, etc.
# Permitted: `md:hidden`, `sm:hidden`, etc. (desktop-hide family)
MOBILE_HIDE_PATTERN = re.compile(
    r'\bhidden\s+(?:sm|md|lg|xl):(?:block|flex|grid|table|inline|inline-block|inline-flex)\b'
)
DATA_TESTID_DATA_CARRIER = re.compile(
    r'data-testid="(metric|tile|chip|row)-[^"]+"'
)

def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    entries = json.loads(ALLOWLIST_PATH.read_text())
    return {e["data_testid"] for e in entries if "reason" in e and e["reason"]}

def test_no_hidden_md_on_data_carrier():
    allowlist = _load_allowlist()
    violations = []
    for jsx_file in FRONTEND_SRC.rglob("*.jsx"):
        for lineno, line in enumerate(jsx_file.read_text().splitlines(), start=1):
            if not MOBILE_HIDE_PATTERN.search(line):
                continue
            testid_match = DATA_TESTID_DATA_CARRIER.search(line)
            if not testid_match:
                continue   # decorative element, not a data carrier — PERMITTED
            testid = testid_match.group(0).split('"')[1]
            if testid in allowlist:
                continue
            violations.append({...})
    assert violations == [], (...)
```

**Adaptations for Phase 14:**
- Regex MUST require `data-testid="(metric|tile|chip|row)-*"` adjacency on the same JSX line (UI-SPEC "Scope clarification"; RESEARCH Pitfall 2 verification table proves this is safe — no preexisting false positives).
- `md:hidden` is explicitly PERMITTED (TournamentDashboard dual-render depends on it).
- Allowlist file shape: `[{"data_testid": "...", "reason": "..."}]`; entries without `reason` are silently dropped (mirrors `audit_bybit_bypass.py` allowlist discipline).
- Pair with sibling assertions in the same file (per RESEARCH Wave 0): `test_tailwind_screens_declared` (read `frontend/tailwind.config.js`, assert `theme.screens` or `theme.extend.screens` literal), `test_viewport_meta_present` (read `frontend/index.html`, assert viewport-meta regex). Both reuse the `REPO_ROOT = Path(__file__).resolve().parents[2]` idiom.
- Skip preexisting subprocess `grep -r` defense-in-depth — Pattern 2's pathlib regex with `data-testid` adjacency is per-line and can't be expressed in plain `grep -r` without false negatives; document this in the test docstring.

---

### `responsive-audit.json` (artifact, output)

**No source analog.** This file is produced by `scripts/audit_responsive.py`, not authored.

Schema (per CONTEXT.md line 21):
```json
[
  {"file": "frontend/src/components/Dashboard.jsx", "line": 82, "rule": "no-hardcoded-width", "snippet": "..."}
]
```

**Planner action:** generate file by running `python3 scripts/audit_responsive.py --out responsive-audit.json` from repo root after script lands. Commit the artifact per ROADMAP SC#1 ("`responsive-audit.json` exists at repo root").

**Note:** RESEARCH Open Question #1 — whether to commit or gitignore — defaults to commit for Phase 14; Phase 15 may move to CI-generated and add to `.gitignore`. RESEARCH Pitfall 1: pre-create `responsive-audit-allowlist.json` with the ~20 out-of-phase-14-scope hits (8 confirmed file paths listed in RESEARCH lines 354–361) so the count-zero gate ships green.

---

### `frontend/tailwind.config.js` (config, build-time)

**Analog:** the file itself (lines 64–66 show the existing `theme: { extend: { ... } }` block).

**Existing pattern** (lines 64–66):
```js
  theme: {
    extend: {
      // -----------------------------------------------------------------------
      // COLOR PALETTE
      // -----------------------------------------------------------------------
      colors: {
        ...
      },
      ...
    },
  },
```

**Insertion target from RESEARCH Pattern 1 / Example 1 (lines 213–238, 430–453) — Option A (replaces defaults; SAFE per RESEARCH Pitfall: zero `2xl:` usage verified 2026-05-22):**
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: 'class',
  theme: {
    screens: {                    // ← NEW: top-level, replaces defaults
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
    },
    extend: {
      // colors, spacing, fontFamily, animation, etc. — ALL existing content
      // UNTOUCHED. screens lands as SIBLING of extend, not inside it.
      colors: { /* existing */ },
      ...
    }
  },
  plugins: [],
}
```

**Adaptations:**
- Re-grep `grep -rn "2xl:" frontend/src/ frontend/index.html` at implementation time (UI-SPEC gating step) — if any hit, switch to Option B (additive `theme.extend.screens`).
- Do NOT rename to `.cjs` (CONTEXT.md explicit).
- Leave entire `theme.extend.*` block intact; only add the top-level `screens:` sibling immediately before `extend:`.

---

### `frontend/src/components/Dashboard.jsx` (component, render)

**Analog:** the file itself; existing responsive patterns at lines 148, 159, 201, 222.

**Existing outer-padding pattern (line 148 — REUSE on reflowed sections):**
```jsx
<div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
  <div className="space-y-5">
```

**Existing responsive-grid pattern (line 159 — adopt shape for reflowed sections):**
```jsx
<section className="grid grid-cols-1 xl:grid-cols-3 gap-5">
  <div className="xl:col-span-2">
    <PriceChart symbol={selectedSymbol} interval="60" />
  </div>
  <div className="xl:col-span-1">
    <TradingSignals symbols={TRADING_PAIRS} interval={60} compact={true} />
  </div>
</section>
```

**Existing two-col-to-multi-col pattern (line 201):**
```jsx
<section className="grid grid-cols-1 lg:grid-cols-3 gap-5">
  <div className="lg:col-span-2"><PortfolioCard /></div>
  <div className="lg:col-span-1"><EmergencyStop /></div>
</section>
```

**Adaptations per UI-SPEC line 145 / CONTEXT.md `<decisions>`:**
- Reflowed sections collapse to `flex flex-col gap-N md:grid md:grid-cols-N` at ≤768px (preserve `space-y-5` outer rhythm).
- Tile render order preserved verbatim (no reordering across breakpoints).
- Header section (line 110–145) already responsive — leave intact; only adjust grid-bearing sections that would horizontal-scroll on mobile.
- The two existing sections that use `grid grid-cols-1 xl:grid-cols-3` (line 159) and `grid grid-cols-1 lg:grid-cols-3` (line 201) already start with single-column at mobile; verify no internal `data-testid` content overflows at 375×667 via Playwright probe.

---

### `frontend/src/components/PathToLiveTile.jsx` (component, render)

**Analog:** the file itself (existing chip-row markup at lines 184–207 and 220–243).

**Existing PREFLIGHT row pattern (lines 184–207):**
```jsx
{checks.map((chk) => (
  <div
    key={chk.check}
    data-testid={`path-to-live-check-${chk.check}`}
    className="flex items-center gap-3 py-0.5"
  >
    <span
      className="w-28 shrink-0 text-xs"
      style={{ color: '#a09e98', fontFamily: 'JetBrains Mono, monospace' }}
    >
      {chk.check}
    </span>
    <StatusChip status={chk.status} />
    <span className="text-xs truncate" style={{ ... }}>{chk.detail}</span>
  </div>
))}
```

**Adaptations per UI-SPEC line 146 / CONTEXT.md:**
- Row container becomes `flex flex-col md:flex-row md:flex-wrap md:items-center gap-1 md:gap-3 py-0.5` so each chip+label stacks vertically ≤768px and goes back to row layout ≥md.
- Each inner span becomes `w-full md:w-auto` so chips wrap to full-width-per-row ≤768px.
- Replace fixed `w-28 shrink-0` / `w-20 shrink-0` (lines 190, 226) with `w-full md:w-28 md:shrink-0` so mobile-stacked labels span full width.
- Banner (line 142–167) stays first visible element; verify `[data-testid="path-to-live-banner"]` visible without scroll at 375×667 (MOBILE-03 banner-visibility assertion).
- 44px touch-target rule: PREFLIGHT and carry-in rows currently `py-0.5` (8px). They are NOT interactive (no `onClick`, no `<button>` wrapping); only `<button>`/`<a>`/`[role="button"]` are subject to the rule per UI-SPEC. Verify no interactive child exists; if any chip becomes a button later, apply `py-3 md:py-1` pattern (RESEARCH Pitfall 4).

---

### `frontend/src/components/KeyMetricsStrip.jsx` (component, render)

**Analog:** the file itself (line 284 already declares a responsive grid).

**Existing responsive-grid pattern (line 284):**
```jsx
{/* Asymmetric metric grid: hero balance spans 2 cols on lg+ */}
<div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3">
  <Cell eyebrow="Total Balance" value={...} hero ... />
  <Cell eyebrow="Unrealized P&L" value={...} ... />
  ...
</div>
```

**Existing outer wrapper (line 217):**
```jsx
<div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
```

**Adaptations per UI-SPEC line 147 / CONTEXT.md:**
- Phase 14 spec says "horizontal-scroll layout becomes `grid grid-cols-2 gap-N md:flex md:overflow-x-auto md:gap-N`". The current code is ALREADY `grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3` — no horizontal-scroll path exists today. Confirm with the count: 6 `<Cell>` children at `grid-cols-2` = 3 rows on phone, no overflow.
- Action: **verify** at 375×667 via Playwright that all 6 cells render in a 2-col grid with no `x + width > innerWidth`. If hero `<Cell>` (line 286, `hero` prop spans 2 cols via inline `gridColumn: 'span 2'`) makes row 1 a single hero cell at mobile — accept that layout (it's per-cell, not a separate breakpoint pattern).
- Outer padding pattern (line 217) already matches Dashboard.jsx convention — no change.
- Lines 233 (`hidden sm:inline italic`) and 260 (`hidden md:inline`) are decorative (no `data-testid`); per RESEARCH Pitfall 2 verification table, they will NOT trip the anti-pattern gate. Leave intact.
- `data-testid="key-metrics-strip"` (line 202) is the top-level marker; ensure it survives reflow.

---

### `frontend/src/pages/TournamentDashboard.jsx` (page, render)

**NO direct codebase analog for dual-render.** Pattern shape is locked by RESEARCH Pitfall 5 (lines 409–417) + UI-SPEC line 148.

**Existing page composition pattern (lines 332–349):**
```jsx
<TournamentFilterChips counts={counts} />

<TileState
  query={snapshotQuery}
  title="Tournament Leaderboard"
  isEmpty={(d) => !d?.snapshot?.rows?.length}
  lastUpdatedAt={exportedAt}
  staleAfterMs={Infinity}
>
  <TournamentLeaderboard
    rows={sortedRows}
    ensembleMembersBySymbol={ensembleMembersBySymbol}
    perSymbolSignificance={perSymbolSignificance}
    sort={sortCol}
    dir={sortDir}
    onSort={onSort}
  />
</TileState>
```

**Adaptations per Pitfall 5 / UI-SPEC line 148:**
- `TournamentLeaderboard.jsx` is **read-only** for this phase — do NOT modify.
- Wrap the existing `<TournamentLeaderboard>` invocation in `<div className="hidden md:block">` (component renders a `<table>` internally; the wrapper hides on mobile).
- Add a NEW sibling `<div className="md:hidden">` containing `.map()` over `sortedRows` (already computed at line 183–193) rendering stacked cards.
- Each mobile-card MUST carry the SAME `data-testid` as the corresponding desktop table row (so Playwright queries locate exactly one visible element at each viewport). Inspect `TournamentLeaderboard.jsx` for the row's existing `data-testid` shape and mirror it.
- RESEARCH Assumption A4: dual-render means BOTH branches in DOM; use `expect(locator).to_have_count(1)` with `:visible` filter, or set viewport-conditional assertion (asserting visibility, not count).
- Outer container patterns at lines 252 (sticky header `flex flex-col gap-3 md:flex-row`) already reflow; no change needed there.
- Card-content order per CONTEXT.md "Claude's Discretion": column-heading → primary-metric (DSR) → secondary-metrics (oos_sharpe, psr, etc.) → meta (timestamps, sha). Implementer determines exact ordering at PR time.

---

### `frontend/src/components/TournamentFilterChips.jsx` (component, render)

**Analog:** the file itself (lines 165, 196, 227 — already use `flexWrap: 'wrap'` in inline styles).

**Existing inline-style wrap pattern (lines 165, 196, 227):**
```jsx
{/* SYMBOLS row */}
<div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
  <span style={eyebrowStyle()}>SYMBOLS</span>
  {SYMBOLS.map((sym) => {
    ...
    return (
      <button
        key={sym}
        type="button"
        data-testid={`tournament-filter-chip-symbol-${sym}`}
        aria-pressed={selected}
        onClick={() => toggleSymbol(sym)}
        style={chipStyle(selected)}
      >
        ...
      </button>
    )
  })}
</div>
```

**Existing chip-style padding (lines 59–75 — `chipStyle(selected)`):**
```jsx
function chipStyle(selected) {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '4px 10px',          // ← 4px+text+4px ≈ 22-24px chip height
    borderRadius: 4,
    ...
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    ...
  }
}
```

**Adaptations per CONTEXT.md + RESEARCH Pitfall 4:**
- `flexWrap: 'wrap'` ALREADY present in inline styles — no action needed for wrap behaviour. CONTEXT.md "add `flex-wrap`" is satisfied; verify visually that chips wrap onto multiple lines at 375×667.
- 44px touch-target compliance per UI-SPEC AAA: chips currently ~22-24px. Two options (planner picks):
  - **Option preferred (RESEARCH Pitfall 4):** add responsive padding `paddingTop: '12px', paddingBottom: '12px'` at mobile (or convert `chipStyle` to a Tailwind utility class `py-3 md:py-1 px-2.5`). On a `<button>`, this gives ≥44px tap target on mobile and preserves dense look ≥md.
  - **Alternative:** add `minHeight: 44` inside `chipStyle` unconditionally and `gap: 12` between chips on mobile.
- The STATUS segmented group (line 244) uses `<button>` per segment too — apply the same 44px treatment.
- The "Clear filters" button (line 267) also needs the 44px treatment (`<button>` with `padding: '4px 8px'` currently → ~22px).
- All `data-testid="tournament-filter-chip-*"` markers (lines 174, 205) and `data-testid="tournament-filter-status"` (line 232) preserved verbatim.

---

### `.github/workflows/dashboard-smoke.yml` (workflow, event-driven)

**Analog:** the file itself (lines 70–73 single pytest step).

**Existing single-test pytest step (lines 70–73):**
```yaml
      - name: Run smoke
        run: |
          pip install pytest-playwright
          pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v
```

**Existing trigger + paths-filter (lines 14–22):**
```yaml
on:
  pull_request:
    paths:
      - 'frontend/**'
      - 'services/api-gateway/**'
      - 'services/trading-engine/app/preflight/**'
      - 'services/trading-engine/app/handlers/preflight.py'
      - 'tests/e2e/test_path_to_live_smoke.py'
      - '.planning/state/carry_ins.json'
  workflow_dispatch:
```

**Adaptations per RESEARCH Example 4 (lines 587–614):**

Two equivalent options (planner picks):

**Option A — second pytest step (simpler, no matrix syntax):**
```yaml
      - name: Run smoke (Path-to-LIVE)
        run: |
          pip install pytest-playwright
          pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v

      - name: Run smoke (responsive)
        run: |
          pytest tests/e2e/test_responsive_dashboard.py --screenshot=only-on-failure --video=retain-on-failure -v
```

**Option B — strategy matrix (parallel, more rigorous):**
```yaml
    strategy:
      fail-fast: false
      matrix:
        include:
          - test_target: tests/e2e/test_path_to_live_smoke.py
            label: path-to-live
          - test_target: tests/e2e/test_responsive_dashboard.py
            label: responsive-mobile
    steps:
      # ... existing setup ...
      - name: Run ${{ matrix.label }}
        run: |
          pip install pytest-playwright
          pytest ${{ matrix.test_target }} --screenshot=only-on-failure --video=retain-on-failure -v
```

**Other workflow extensions:**
- Add `tests/e2e/test_responsive_dashboard.py` to `paths:` trigger list.
- Add `frontend/tailwind.config.js` and `scripts/audit_responsive.py` to `paths:` list so audit-affecting changes re-run the suite.
- Keep existing log-collect + cleanup steps unchanged (lines 75–91).
- The viewport parametrization itself lives INSIDE `test_responsive_dashboard.py` (per RESEARCH Example 4 closing paragraph) — workflow does NOT pass viewport via matrix; tests report as `test_no_horizontal_scroll[iphone-se]` / `[ipad-portrait]` in CI output.

---

## Shared Patterns

### Pattern S1: `REPO_ROOT = Path(__file__).resolve().parents[N]` idiom

**Source:** `tests/integration/test_dashlive_grep_gates.py:37`, `tests/integration/test_preflight_grep_gates.py:41`, `scripts/audit_bybit_bypass.py:33`.

**Apply to:** `scripts/audit_responsive.py` (`parents[1]`), `tests/integration/test_no_mobile_hidden_data.py` (`parents[2]`).

```python
REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/integration/foo.py → repo
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
```

Verified to resolve correctly under Claude Code worktree paths per `tests/ci/test_no_bybit_bypass.py:56-63` comment.

---

### Pattern S2: Dual-form scan (pathlib + subprocess grep)

**Source:** `tests/integration/test_preflight_grep_gates.py` (DASHLIVE-04 idiom).

**Apply to:** `tests/integration/test_no_mobile_hidden_data.py` — but **only the pathlib half**. The subprocess `grep -r` half requires per-line `data-testid` adjacency (which `grep` can't express without false negatives); document this constraint in the docstring. Use pathlib + per-line scan only.

For `scripts/audit_responsive.py`, no dual-form needed — it's a producer script, not a gate.

---

### Pattern S3: Allowlist with mandatory `reason` field

**Source:** `scripts/audit_bybit_bypass.py` (per-(file,kind) tuple key, default fallback); RESEARCH Example 3 (lines 550–557).

**Apply to:** `scripts/audit_responsive.py` (allowlist file: `.planning/phases/14-mobile-responsive-dashboard/responsive-audit-allowlist.json`), `tests/integration/test_no_mobile_hidden_data.py` (allowlist file: `.planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json`).

```python
def _load_allowlist() -> dict[str, str]:
    if not ALLOWLIST.exists():
        return {}
    return {
        f"{e['file']}:{e['line']}": e["reason"]
        for e in json.loads(ALLOWLIST.read_text())
        if e.get("reason")               # ← mandatory; silently drop missing-reason entries
    }
```

**Rationale:** prevents drive-by allowlisting without explanation; mirrors the discipline used by Phase 13's Bybit-bypass allowlist (see `tests/ci/test_no_bybit_bypass.py:68-94` comment block where every exempt path carries an inline rationale).

---

### Pattern S4: `data-testid` scoping in regex (anti-collateral)

**Source:** RESEARCH Pitfall 2 verification table (lines 367–381) — verified safe against 10 existing `hidden <bp>:*` usages.

**Apply to:** `tests/integration/test_no_mobile_hidden_data.py` per-line regex.

```python
MOBILE_HIDE_PATTERN = re.compile(
    r'\bhidden\s+(?:sm|md|lg|xl):(?:block|flex|grid|table|inline|inline-block|inline-flex)\b'
)
DATA_TESTID_DATA_CARRIER = re.compile(
    r'data-testid="(metric|tile|chip|row)-[^"]+"'
)

# Per-line evaluation: BOTH patterns must match the SAME line for it to count
# as a violation. Decorative usage (no data-testid match) is permitted.
```

This is load-bearing — without the data-testid adjacency requirement, the gate falsely flags 10 valid decorative `hidden sm:inline` / `hidden md:flex` usages.

---

### Pattern S5: Outer-padding container `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`

**Source:** `Dashboard.jsx:82,148,245`; `KeyMetricsStrip.jsx:217`.

**Apply to:** every reflowed container in Dashboard.jsx, KeyMetricsStrip.jsx. Do NOT introduce a different outer-padding pattern (UI-SPEC line 161 explicitly forbids).

---

### Pattern S6: `browser_context_args` session-scoped fixture override

**Source:** `tests/e2e/test_path_to_live_smoke.py:39-42`.

**Apply to:** `tests/e2e/test_responsive_dashboard.py` — BUT replace session-scoped form with `@pytest.mark.parametrize("browser_context_args", VIEWPORTS, indirect=True)` matrix per RESEARCH Pattern 2 (lines 257–262). The matrix form supersedes session-scope for the responsive matrix; both forms can coexist if a default viewport is also needed.

**Anti-pattern (RESEARCH Anti-Patterns to Avoid + Pitfall 3):** never call `page.set_viewport_size()` after `page.goto()` (Chromium may not retrigger media-query matching); never use `playwright.devices['iPhone SE']` (descriptor is 320×568, spec requires 375×667).

---

### Pattern S7: `@pytest.mark.usefixtures("bootstrap_stack")` decorator

**Source:** `tests/e2e/test_path_to_live_smoke.py:73,149,196,242`.

**Apply to:** every test function in `tests/e2e/test_responsive_dashboard.py` that requires the stack booted (every test that does `page.goto(GATEWAY_ORIGIN)`). `tape_reset` is NOT needed for layout tests (no API state seeded).

```python
@pytest.mark.usefixtures("bootstrap_stack")
@pytest.mark.parametrize("browser_context_args", VIEWPORTS, indirect=True, ids=[...])
def test_no_horizontal_scroll(page, browser_context_args):
    ...
```

`bootstrap_stack` is session-scoped (per `tests/integration/conftest.py:94`); single boot for all matrix runs.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `responsive-audit.json` | artifact (output) | output | Generated by `scripts/audit_responsive.py`; not authored. Schema in CONTEXT.md line 21. |
| `frontend/src/pages/TournamentDashboard.jsx` (dual-render addition) | page composition | render | No dual-render-pair pattern exists in the codebase. Shape locked by RESEARCH Pitfall 5 + UI-SPEC line 148. Note: the existing file IS modified (sibling `<div className="md:hidden">` + wrapper `<div className="hidden md:block">` around existing `<TournamentLeaderboard>`); the page composition pattern is well-established, but the dual-render-with-mirrored-testids idiom is new. |

---

## Metadata

**Analog search scope:**
- `tests/e2e/` (all 8 files; primary analog `test_path_to_live_smoke.py`)
- `tests/integration/` (all 18 files; primary analogs `test_dashlive_grep_gates.py`, `test_preflight_grep_gates.py`)
- `tests/ci/test_no_bybit_bypass.py` (single file; allowlist-discipline reference)
- `scripts/` (audit_*.py family; primary analog `audit_bybit_bypass.py`)
- `frontend/src/components/{Dashboard,PathToLiveTile,KeyMetricsStrip,TournamentFilterChips,TournamentLeaderboard}.jsx`
- `frontend/src/pages/TournamentDashboard.jsx`
- `frontend/tailwind.config.js`
- `.github/workflows/dashboard-smoke.yml`
- Project skill `gsd-phase-researcher` output: RESEARCH.md Patterns 1–3, Examples 1–4 (already canonical for this phase).

**Files scanned:** ~30 source files, 4 workflow files, all 11 Phase-14 target files (5 self-modify, 4 create, 2 with no analog).

**Pattern extraction date:** 2026-05-22

**Wave 0 gap flag (planner note):** RESEARCH.md "Wave 0 Gaps" lists three additional test files not in the upstream Phase 14 file list:
- `tests/integration/test_responsive_audit_shape.py` (verifies `responsive-audit.json` schema)
- `tests/integration/test_responsive_audit_count_zero.py` (verifies count of unallowlisted hits is 0)
- `tests/integration/test_dashboard_smoke_workflow_extended.py` (verifies workflow YAML has the new test target)

These would reuse Pattern S1 + S2 + (for the YAML-check file) `pyyaml` load + key-existence assert. They are listed in this PATTERNS.md as candidate analogs for the planner to decide on scope expansion — not added to the per-file table above to respect the explicit 11-file list provided by the orchestrator. If the planner expands scope, all three follow the `test_dashlive_grep_gates.py` shape verbatim with assertion-target swap.

**Cross-cutting note:** every Phase-14 file leans on at least one of S1–S7. Pattern S3 (allowlist with mandatory reason) and Pattern S4 (data-testid adjacency) are LOAD-BEARING for not shipping false-positive gates. Pattern S6 (matrix viewport via `browser_context_args`) is LOAD-BEARING for Playwright correctly applying mobile viewports before navigation (RESEARCH Pitfall 3 + Nyquist false-positive #1).
