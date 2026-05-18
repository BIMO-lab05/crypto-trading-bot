# Phase 10: Path-to-LIVE Dashboard - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

> Captured via `/gsd-discuss-phase 10` with user override "make reasonable calls, redirect if wrong." User explicitly chose all four headline decisions (Recommended options); remaining specifics locked below as `decision:` and may be revisited by the planner if downstream evidence conflicts.

<domain>
## Phase Boundary

This phase makes LIVE-readiness visible on one screen, with operator-grade colour states (DO-NOT-FLIP / ALMOST / READY) and a code-enforced 24-hour continuous-PASS window before READY can light up. By end of Phase 10:

- A new React component `PathToLiveTile.jsx` renders at the top of the main dashboard (`/` route, above `KeyMetricsStrip`) as a full-width card, polling every 5 seconds.
- The tile shows the 6 PREFLIGHT checks (PASS / FAIL / UNKNOWN per row) sourced from `GET /api/preflight/live-readiness` (Phase 8, already shipped).
- The tile shows 5 carry-in close states (OP-01..04 + INFRA-02) sourced from a new endpoint `GET /api/preflight/carry-ins` owned by `api-gateway`, reading `.planning/state/carry_ins.json`.
- A new file `.planning/state/carry_ins.json` is created with documented schema (`carry_ins[]` array + `_state` object). Phase 10 ships the file with all carry-ins in `state: open` (Phase 11 LIVECLOSE will flip them to closed).
- The 24-hour continuous-PASS window is computed server-side by api-gateway: `_state.first_all_pass_at` is set when all 6 PREFLIGHT checks first become PASS simultaneously, and reset to `null` on any FAIL or UNKNOWN at the next poll. READY only lights up when `now - first_all_pass_at ≥ 24h`.
- A Playwright smoke at `tests/e2e/test_path_to_live_smoke.py` (new path) boots the recorded-tape stack, seeds a `leaderboard` row, asserts the tile renders + endpoint shape + DSR row schema, runs under a new `.github/workflows/dashboard-smoke.yml` CI.

This phase is the **operator-visibility** surface for the work that Phase 8 (preflight enforcement) and Phase 9 (ML re-enablement gate) wired into code. Phase 11 (LIVECLOSE) consumes this UI as the smoke target.

</domain>

<decisions>
## Implementation Decisions

### Carry-ins source of truth

- **D-10-01:** `GET /api/preflight/carry-ins` reads from a single JSON file `.planning/state/carry_ins.json`. **NOT** from git tags. (Chosen by user; option A.)
  - Rationale: matches the existing `.planning/` artifact-as-state convention. Containerised reads stay simple. Phase 11 will write closures by editing this file in a commit. Git tags rejected to avoid requiring `git` inside the api-gateway container and to keep closure ceremony lightweight.

- **D-10-02:** File schema (locked):
  ```json
  {
    "schema_version": 1,
    "carry_ins": [
      {"id": "OP-01", "state": "open", "closed_at": null, "evidence_path": null, "description": "LIVECLOSE-05 LIVE-flip manual smoke"},
      {"id": "OP-02", "state": "open", "closed_at": null, "evidence_path": null, "description": "Migration 005 operator action"},
      {"id": "OP-03", "state": "open", "closed_at": null, "evidence_path": null, "description": "TOURNAMENT_READER_PASSWORD set"},
      {"id": "OP-04", "state": "open", "closed_at": null, "evidence_path": null, "description": "GH Actions billing resolved"},
      {"id": "INFRA-02", "state": "open", "closed_at": null, "evidence_path": null, "description": "Fresh-clone bootstrap checkpoint"}
    ],
    "_state": {
      "first_all_pass_at": null,
      "last_evaluated_at": null,
      "last_overall": "UNKNOWN"
    }
  }
  ```
  - `state` is `"open" | "closed"`; `closed_at` is ISO 8601 string when `state="closed"`, else `null`; `evidence_path` is repo-relative path to closure evidence (e.g., `.planning/evidence/LIVECLOSE-05/`) and may be `null` while open.
  - `_state` is owned by api-gateway (writer); `carry_ins[]` array is owned by Phase 11 LIVECLOSE (writer). Schema version is bumped if either contract changes.

- **D-10-03:** Endpoint owner = `api-gateway` (not `trading-engine`).
  - Rationale: the state file is repo-bound (`.planning/state/`), not trading-engine-runtime; api-gateway already owns the proxy for `/api/preflight/live-readiness`; the 24h window writer needs RW access to the file and api-gateway already writes other repo-bound state files (`EMERGENCY_STOP` precedent at docker-compose.unified.yml:304). Trading-engine stays focused on its risk-cap + ML-gate jobs.
  - Implementation: `services/api-gateway/app/routes/preflight_carry_ins.py` (new module). Wire into existing api-gateway router registration.

- **D-10-04:** Endpoint response shape (versioned, mirrors live-readiness):
  ```json
  {
    "schema_version": 1,
    "evaluated_at": "2026-05-17T14:32:01Z",
    "overall": "DO_NOT_FLIP" | "ALMOST" | "READY",
    "carry_ins": [<copy of carry_ins[] from file>],
    "window": {
      "first_all_pass_at": "2026-05-16T14:32:01Z" | null,
      "elapsed_seconds": 86400,
      "required_seconds": 86400,
      "remaining_seconds": 0
    },
    "preflight_summary": {"pass": 6, "fail": 0, "unknown": 0}
  }
  ```
  - `overall` is **computed by api-gateway** on each request from the live-readiness response + the 24h window: `DO_NOT_FLIP` if any preflight check is not PASS; `ALMOST` if all 6 PASS but `elapsed < required`; `READY` if all 6 PASS and `elapsed ≥ required`.
  - The frontend tile renders `overall` directly — it does NOT recompute the 3-state banner client-side. Single source of truth = server.

- **D-10-05:** Container bind-mount for state file:
  - In `docker-compose.unified.yml`, api-gateway gets a new RW bind-mount: `./.planning/state:/app/planning_state:rw`. RW because api-gateway must update `_state.first_all_pass_at`.
  - Container path is `/app/planning_state/carry_ins.json` (env var `PREFLIGHT_CARRY_INS_PATH` defaults to this, overridable for tests).
  - **Mount point must be a directory, not a single file**, to avoid the WSL bind-mount-race where docker silently creates an empty dir on first up (CLAUDE.md gotcha). Bind the parent dir.

### 24-hour continuous-PASS window mechanics

- **D-10-06:** Persistence = `carry_ins.json._state.first_all_pass_at`. (Chosen by user; option A.)
  - Survives container restart. Single source. No separate history log.

- **D-10-07:** Reset rule (locked):
  - On every poll (5s), api-gateway fans out to trading-engine `/api/preflight/live-readiness`, gets the report.
  - Compute `all_pass = all(check.status == "PASS" for check in report.checks)`.
  - If `all_pass` and `_state.first_all_pass_at is None`: set `_state.first_all_pass_at = now_iso()`.
  - If not `all_pass`: set `_state.first_all_pass_at = None`.
  - `last_evaluated_at = now_iso()`; `last_overall = computed_overall_str`.
  - Write the file atomically (temp file + `os.rename`) to avoid torn writes.

- **D-10-08:** UNKNOWN counts as not-PASS for window-reset purposes. (Chosen by user; option A.)
  - Rationale: UNKNOWN is a real terminal state per Phase 8 D-09 (e.g., trading-engine unreachable, DSR row missing). Treating it as PASS would let READY light up under degradation. Treating it as reset is the safe default.

- **D-10-09:** Required window = 24h = 86400 seconds. Configurable via env `PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS` (default `86400`) so tests can override to `1` for fast-forward assertions without monkeypatching `time.time`.

- **D-10-10:** Concurrency = api-gateway is single-process per container; the 5s poll cadence and atomic-rename write make a file lock unnecessary in production. Tests inject `now` to avoid timing flakiness.

- **D-10-11:** On trading-engine unreachable, api-gateway returns `overall = "DO_NOT_FLIP"` (not `UNKNOWN`) for the tile contract — the dashboard tile only renders three banner colours. The per-check `live_readiness` portion of the response still shows `UNKNOWN` for any check that came back UNKNOWN, so the operator sees the cause. (Phase 8 already returns `overall=UNKNOWN` from `/api/preflight/live-readiness` on trading-engine failure; Phase 10 maps `UNKNOWN → DO_NOT_FLIP` for the banner only.)

### Tile placement + visual layout

- **D-10-12:** PathToLiveTile renders at the **top of `Dashboard.jsx`**, prepended above `<KeyMetricsStrip />`. (Chosen by user; option A.)
  - Full-width card spanning the existing dashboard max-width container.
  - First visual element below the route — operator sees LIVE-readiness state immediately on load.

- **D-10-13:** Layout (sketch — planner may refine pixel-level details):
  ```
  ┌───────────────────────────────────────────────────────────────┐
  │  [DO NOT FLIP]   Path to LIVE                  evaluated 14:32 │
  │  Banner red                                                    │
  ├───────────────────────────────────────────────────────────────┤
  │  PREFLIGHT checks                                              │
  │  cap                  [PASS] max_risk_per_trade=0.02 ≤ 0.02    │
  │  paper_mode           [PASS] PAPER_TRADING_MODE=false          │
  │  trading_mode         [FAIL] TRADING_MODE=PAPER                │
  │  ack                  [UNKNOWN] LIVE_TRADING_ACK not set       │
  │  emergency_stop       [PASS] no file at /app/EMERGENCY_STOP    │
  │  dsr_evidence         [PASS] dsr=0.97, run_date=2026-05-15     │
  ├───────────────────────────────────────────────────────────────┤
  │  Carry-ins                                                     │
  │  OP-01   [open]  LIVECLOSE-05 LIVE-flip manual smoke           │
  │  OP-02   [open]  Migration 005 operator action                 │
  │  OP-03   [open]  TOURNAMENT_READER_PASSWORD set                │
  │  OP-04   [open]  GH Actions billing resolved                   │
  │  INFRA-02 [open] Fresh-clone bootstrap checkpoint              │
  ├───────────────────────────────────────────────────────────────┤
  │  24h continuous-PASS window: 0:00:00 / 24:00:00                │
  └───────────────────────────────────────────────────────────────┘
  ```
  - Banner uses three tailwind background tokens: `bg-rose-700` (DO_NOT_FLIP), `bg-amber-600` (ALMOST), `bg-emerald-700` (READY) — match existing operator-state palette in `StatusBar.jsx` if precedent exists.
  - Status chips: PASS = `bg-emerald-700/30 text-emerald-300`, FAIL = `bg-rose-700/30 text-rose-300`, UNKNOWN = `bg-slate-600/30 text-slate-300`.
  - Carry-in chips: `[open]` = amber, `[closed]` = emerald.

- **D-10-14:** Tile wraps in `<TileState>` (existing wrapper at `frontend/src/components/TileState.jsx`). `thresholdKey` = `"default"` (60s). On error/loading/empty, TileState handles the render; the tile body assumes data is present.

- **D-10-15:** Two react-query hooks, separate cache keys, both 5s `refetchInterval`:
  - `useLiveReadiness()` → `GET /api/preflight/live-readiness` (existing endpoint).
  - `useCarryIns()` → `GET /api/preflight/carry-ins` (new endpoint).
  - `PathToLiveTile.jsx` consumes both. Rationale: separate keys allow other future tiles to reuse `useLiveReadiness` without forcing a full path-to-live payload. Both at 5s matches `useSafetyState` cadence (D-11 from Phase 6).

- **D-10-16:** The carry-ins endpoint **also** returns the joined `live_readiness` report inside its response so that the tile renders consistently even if the live-readiness query refetch happens to land between window-state writes. Locked decision: `useCarryIns().data` is the authoritative source for `overall` and `window`; `useLiveReadiness()` is used for per-check detail rows only. If they disagree (race), trust `useCarryIns`.

### Smoke test scope + CI workflow

- **D-10-17:** Smoke path = `tests/e2e/test_path_to_live_smoke.py`. (Chosen by user; option A.)
  - New top-level `tests/e2e/` directory (no precedent; Phase 7 smoke lives under `tests/integration/`). The split keeps DASHLIVE-04 scope independent of the Phase 7 dashboard-audit walker.
  - Uses pytest-playwright + Chromium-only, mirroring Phase 7's `test_dashboard_smoke.py` shape.
  - Boots stack via the recorded-tape `bootstrap_stack` + `tape_reset` fixtures (Phase 2 infra). Reuses `tests/integration/conftest.py` fixture imports.

- **D-10-18:** Required assertions (locked, the planner must cover all):
  1. Tile is visible at `data-testid="path-to-live-tile"` on the `/` route.
  2. Each of the 6 PREFLIGHT rows renders with a labelled status chip; the chip text matches the `status` field for that check from a snapshot of `GET /api/preflight/live-readiness`.
  3. Each of the 5 carry-in rows renders with state `open` (seeded fixture, all open).
  4. Banner text matches `overall` from `GET /api/preflight/carry-ins`. In PAPER mode with no DSR row, expected banner = `DO NOT FLIP`.
  5. Endpoint `GET /api/preflight/carry-ins` returns `schema_version=1`, top-level keys = `{schema_version, evaluated_at, overall, carry_ins, window, preflight_summary}`.
  6. DSR row schema assertion: seed a row in `leaderboard` with `dsr=0.97, run_date=<today>, psr_ci_published=1, status='success'`, hit `/api/preflight/live-readiness`, assert `dsr_evidence.status == "PASS"` and `dsr_evidence.detail` contains the numeric `dsr` and the ISO `run_date`.
  7. With `PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1` (test override): force all 6 checks PASS via env stubs, wait 2s, hit endpoint twice, assert second response has `overall == "READY"` and `window.elapsed_seconds ≥ 1`. (Mechanics test, isolated from real 24h timer.)

- **D-10-19:** CI workflow = `.github/workflows/dashboard-smoke.yml` (NEW). (Roadmap-aligned.)
  - Triggers: `pull_request` with `paths` filter on `frontend/`, `services/api-gateway/`, `services/trading-engine/app/preflight/`, `services/trading-engine/app/handlers/preflight.py`, `tests/e2e/test_path_to_live_smoke.py`. Plus `workflow_dispatch`.
  - Job: `dashboard-smoke` runs `bash bootstrap.sh` (paper mode, no Bybit secrets), then `pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v`.
  - Required-check on PRs touching the listed paths (operator can mark it required in branch protection).
  - Not nightly — runs only on PRs touching the relevant code, to avoid burning CI minutes during OP-04 billing pressure. Phase 12 (CI Recovery) is the right place to add nightly cadence.

- **D-10-20:** Grep gates (defence-in-depth, follows Phase 8/9 pattern):
  - `tests/integration/test_dashlive_grep_gates.py` with two assertions:
    1. `grep -r "PathToLiveTile" frontend/src/` returns ≥1 match.
    2. `grep -r "carry-ins" services/api-gateway/app/` returns ≥1 match (catches if endpoint silently removed).
  - Mirrors the TOURN-07 + PREFLIGHT-01 + MLGATE-03 grep-gate pattern. Runs in the existing `tests/integration/` CI lane — no new infra.

### Claude's Discretion

- Per-row icon choice (lucide-react). Recommend `Check` (PASS), `X` (FAIL), `HelpCircle` (UNKNOWN) for chips. Carry-in state icons: `Circle` (open), `CheckCircle2` (closed).
- Banner h1 typography (existing operator-state palette in `StatusBar.jsx` is the reference).
- Exact tailwind utility-class composition. Stay within existing palette tokens — no new design system entries.
- Error rendering text for `useCarryIns` failure: route through `TileState`'s `Failed (<code>): <msg>. [Retry]` shape per D-14 from Phase 6.
- Hook file locations: `frontend/src/hooks/useLiveReadiness.js`, `frontend/src/hooks/useCarryIns.js` (one file each; matches existing `useSafetyState.js` shape).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase boundary + requirements

- `.planning/PROJECT.md` — Current Milestone v1.1 section; Validated requirements (DASH-01..06 Phase 6/7 baseline); Out of Scope clauses.
- `.planning/REQUIREMENTS.md` — DASHLIVE-01..04 (Phase 10 owns these).
- `.planning/ROADMAP.md` §Phase 10 — Goal + 4 Success Criteria (lines 70–80).
- `.planning/ROADMAP.md` §Phase 11 — Dependencies on Phase 10 (LIVECLOSE-05 needs tile visible during smoke).

### Phase 8 (PREFLIGHT) — direct dependency

- `.planning/phases/08-pre-live-preflight/08-CONTEXT.md` — schema_version=1 shape, UNKNOWN semantics, unauth read-only contract, gateway proxy pattern at `/api/preflight/live-readiness`.
- `services/trading-engine/app/handlers/preflight.py` — `GET /api/preflight/live-readiness` handler. Phase 10 carry-ins endpoint fans out to this.
- `services/trading-engine/app/preflight/checks.py` — 6 check functions; DSR check reads `leaderboard` (D-10-22 below confirms).
- `services/api-gateway/app/main.py:1168-1210` — existing `/api/preflight/live-readiness` proxy. New carry-ins endpoint follows the same fan-out + graceful-degradation pattern.

### Phase 9 (MLGATE) — DSR row contract

- `.planning/phases/09-ml-re-enablement-gate/09-VERIFICATION.md` — DSR evidence row contract (`psr_ci_published=1`, `run_date` within 14 days, `status='success'`).
- `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` — `run_date` + `psr_ci_published` columns on `leaderboard`.
- `services/trading-engine/app/lifespan/ml.py` — auto-flip marker `/run/mlgate_auto_flip.json` (referenced by Phase 8 DSR check semantics; Phase 10 surfaces the result, does not consume the marker directly).

### Frontend patterns

- `frontend/src/hooks/useSafetyState.js` — 5s poll pattern + react-query usage + JSDoc shape. **Copy this idiom for `useLiveReadiness` and `useCarryIns`.**
- `frontend/src/components/TileState.jsx` — shared wrapper for every audited tile. PathToLiveTile MUST wrap in TileState.
- `frontend/src/components/StatusBar.jsx` — operator-state header reference; reuse colour palette tokens here for the 3-state banner.
- `frontend/src/components/Dashboard.jsx` — host route; PathToLiveTile gets prepended above `<KeyMetricsStrip />` (line ~75 area).
- `frontend/src/services/api.js` — axios baseURL `/api`; response interceptor unwraps `.data`. Hook code returns raw body, not `.data.data`.

### Smoke test infra

- `tests/integration/test_dashboard_smoke.py` — Phase 7 audit-driven Playwright walker (header doc at top of file). Path-to-live smoke reuses the bootstrap_stack + tape_reset fixtures pattern; **mirror the structure, do NOT extend the file**.
- `tests/integration/conftest.py` — fixtures for the stack. `tests/e2e/conftest.py` (new) re-exports the needed fixtures, or imports from `tests/integration/conftest.py` via `pytest_plugins`. Planner picks the cleaner path.
- `.github/workflows/preflight-live-readiness.yml` — Phase 8 CI workflow shape; `dashboard-smoke.yml` follows the same job-skeleton + paths-filter conventions.
- `.github/workflows/live-smoke.yml` — bootstrap.sh-in-CI example (paper mode); reuse the env-block pattern.

### Conventions + retrospectives

- `RUNBOOK.md` §"Pre-LIVE Operator Checklist" (added Phase 8) — operator workflow context. Phase 10 may add a sub-section "Reading the dashboard tile" but is not required to.
- `CLAUDE.md` §"Trading-mode flags" — four deliberate steps to LIVE; PathToLiveTile surfaces preconditions but does not change flag semantics.
- `CLAUDE.md` §"Verification standards" — `/verify-stack` checklist; smoke test must hit real endpoints, not 200-only checks.
- `.planning/RETROSPECTIVE.md` — v1.0 lessons: pair every "watch" surface with a CI grep gate (TOURN-07 model); defence-in-depth at component + endpoint + grep test.
- `wiki/decisions/` (ADR-010, ADR-011, ADR-012) — paper-relaxed 10% cap, tier-2 monitoring deletion, backtest divergence. Inform tile copy; do not affect tile logic.

### Files this phase will create / modify (planner reference)

- NEW `frontend/src/components/PathToLiveTile.jsx`
- NEW `frontend/src/hooks/useLiveReadiness.js`
- NEW `frontend/src/hooks/useCarryIns.js`
- MOD `frontend/src/components/Dashboard.jsx` (single line: import + prepend tile)
- NEW `services/api-gateway/app/routes/preflight_carry_ins.py`
- MOD `services/api-gateway/app/main.py` (register router; carry-ins handler block adjacent to live-readiness proxy)
- NEW `.planning/state/carry_ins.json` (initial seed — all 5 carry-ins `open`, `_state` zeroed)
- MOD `docker-compose.unified.yml` (api-gateway volume: `./.planning/state:/app/planning_state:rw`)
- NEW `tests/e2e/__init__.py`, `tests/e2e/conftest.py` (re-exports), `tests/e2e/test_path_to_live_smoke.py`
- NEW `tests/integration/test_dashlive_grep_gates.py`
- NEW `.github/workflows/dashboard-smoke.yml`
- MOD `frontend/src/services/api.js` (optional — only if a typed helper is added; otherwise hooks call `api.get('/preflight/...')` directly)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`useSafetyState` hook** (`frontend/src/hooks/useSafetyState.js`) — 5s `refetchInterval` + `staleTime`, `retry: 2`, `retryDelay: 1000`. Copy the idiom verbatim for `useLiveReadiness` and `useCarryIns`. Same `@tanstack/react-query` v5.
- **`TileState` wrapper** (`frontend/src/components/TileState.jsx`) — D-12..D-15 state-machine for every audited tile. PathToLiveTile is a new audited tile, so it MUST wrap. Uses `STALE_THRESHOLDS_MS.default = 60s`.
- **`/api/preflight/live-readiness` proxy** (`services/api-gateway/app/main.py:1168-1210`) — graceful-degradation pattern: on trading-engine unreachable, return `overall=UNKNOWN`. New carry-ins endpoint follows the same `httpx.AsyncClient` fan-out, then merges the trading-engine response into its own.
- **`EMERGENCY_STOP` bind-mount precedent** (`docker-compose.unified.yml:300-304`) — api-gateway has RW access to a repo-rooted file. Bind a dir, not a file, to dodge the WSL bind-mount-race noted in CLAUDE.md.
- **Phase 7 `test_dashboard_smoke.py`** — pytest-playwright shape with `bootstrap_stack` + `tape_reset` fixtures. Path-to-live smoke reuses the fixtures; structure mirrors but file is separate.
- **`scripts/preflight_live.py`** — CLI entry; planner does NOT modify this in Phase 10. Listed only so planner doesn't accidentally re-implement check logic.
- **Phase 8 grep gates** (`tests/integration/test_preflight_grep_gates.py`) — model for the two grep gates in D-10-20.

### Established Patterns

- **5-second poll cadence everywhere** (D-11 from Phase 6) — `useSafetyState`, `useTicker`, and the upcoming `useLiveReadiness` + `useCarryIns` all match. No WebSocket — REST polling is the decision.
- **Schema versioning on every preflight payload** (`schema_version: 1`) — Phase 8 contract. Phase 10 carries it forward on `/api/preflight/carry-ins`.
- **Unauthenticated read-only preflight endpoints** — `/api/preflight/live-readiness` (Phase 8), `/api/preflight/ml-gate-reason-counts` (Phase 9). `/api/preflight/carry-ins` follows: no auth dependency, no secrets in response.
- **Defence-in-depth grep gates for every "watch" emission** — TOURN-07 (canonical metrics imports), PREFLIGHT-01 (LIVE_PREFLIGHT_REJECTED), MLGATE-02 (MLGATE_AUTO_FLIP), MLGATE-03 (reason= field). DASHLIVE follows: grep for `PathToLiveTile` + `carry-ins`.
- **Atomic file writes for state files** — temp file + `os.rename`. Same pattern Phase 9's `/run/mlgate_auto_flip.json` writer uses (`services/trading-engine/app/lifespan/ml.py`). api-gateway carry-ins writer copies the idiom.
- **DSR query source** (`services/trading-engine/app/preflight/checks.py`) — `leaderboard` table, **not** the non-existent `tournament_results`. Phase 8 wording correction in 08-CONTEXT.md D-08; Phase 10 smoke seeds `leaderboard` accordingly.

### Integration Points

- **Dashboard.jsx** — single-line insertion of `<PathToLiveTile />` above `<KeyMetricsStrip />`. No prop drilling — hooks own their own queries.
- **api-gateway router** — new file `services/api-gateway/app/routes/preflight_carry_ins.py` registered in `main.py` next to the existing live-readiness proxy block (~line 1168).
- **docker-compose.unified.yml** — add `./.planning/state:/app/planning_state:rw` to `api-gateway` `volumes:`. Mount the directory, not the single file (CLAUDE.md WSL gotcha).
- **Phase 11 (LIVECLOSE)** — Phase 11 will edit `.planning/state/carry_ins.json` to flip `state: "closed"` per carry-in as evidence lands. Phase 10 ships the file with all open. **Phase 11 does NOT need to touch `_state` — that is api-gateway's exclusive territory.**

</code_context>

<specifics>
## Specific Ideas

- The 24h banner copy: `DO NOT FLIP` (uppercase, weight 700), `ALMOST` (uppercase, weight 600), `READY` (uppercase, weight 700). No subtitle on banner — the per-row detail is enough.
- ALMOST banner subtitle (small text under banner): `"All checks PASS — XX:XX:XX of 24:00:00 elapsed"`. Pure UI text.
- The 24h window display uses `Intl.DateTimeFormat` or a small `hh:mm:ss` formatter inline. No moment/dayjs dep.
- Carry-in row click behaviour for Phase 10 = **none**. The row is text + chip. Phase 12 may add a click-to-expand for evidence path; out of scope here.
- The tile heading text = `"Path to LIVE"`. Operator-facing copy — keep it short and unambiguous.
- The tile MUST render even if `useCarryIns` fails (TileState handles the error state with Failed/Retry). It MUST NOT render the banner if data is absent — render TileState error UI.

</specifics>

<deferred>
## Deferred Ideas

These came up during planning but belong elsewhere:

- **Per-carry-in click-to-expand showing evidence path + screenshot** — Phase 12 (CI Recovery) or post-v1.1. Phase 10 surface is read-only flat.
- **Telegram/Pushover alert on `READY → DO_NOT_FLIP` transition** — operator-experience nicety; defer until at least one READY→DO_NOT_FLIP has happened in practice and the operator confirms they want push.
- **WebSocket replacement for 5s poll** — explicit Phase 6 decision (D-11) to keep REST polling everywhere; revisit only if poll cost becomes measurable.
- **Storing `_state.first_all_pass_at` in PostgreSQL instead of JSON** — overkill for one timestamp; revisit only if the carry_ins.json file gains write-contention symptoms (it won't at 5s single-process).
- **"Force ALMOST → READY" operator override button** — explicitly **rejected** as a future feature. The 24h continuous-PASS window is the safety property; an override defeats it. If the operator needs to bypass for emergency LIVE testing, they edit `carry_ins.json` directly on the host — leaves a git-diff audit trail.
- **History log of every banner-state transition** — append-only `preflight_history.jsonl` was option C in the discussion; not chosen. May be added later as a separate audit feature if operators want a "show me the last 7 days" view.
- **Nightly cron for `dashboard-smoke.yml`** — Phase 12 (CI Recovery) territory; Phase 10 keeps the workflow PR-triggered only to conserve CI minutes during OP-04 pressure.
- **Backporting the tile to Phase 7's audited-tile JSON** — Phase 7's audit walker covers existing tiles. Adding PathToLiveTile to that JSON is a Phase 7-style audit chore, not a Phase 10 deliverable. Planner can decide whether to insert one row into `06-TILE-AUDIT.json` as a single-line addition; not load-bearing for the Phase 10 success criteria.

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 10-path-to-live-dashboard*
*Context gathered: 2026-05-17*
