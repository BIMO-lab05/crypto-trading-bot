# Phase 7: Tournament View & Smoke Test — Pattern Map

**Mapped:** 2026-05-14
**Files analyzed:** 14 new + 5 modified
**Analogs found:** 17 / 19 (2 patterns are net-new — pytest-playwright, gateway disk-read; called out in "No Analog Found")

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `frontend/src/pages/TournamentDashboard.jsx` *(new)* | page | request-response, read-only | `frontend/src/pages/PerformanceDashboard.jsx` | exact (sticky header + max-width main + section grid) |
| `frontend/src/components/TournamentLeaderboard.jsx` *(new)* | presentational component | render-only props | `frontend/src/components/KeyMetricsStrip.jsx` `Cell` + `StatusBar.jsx` `Cell` | partial (no in-repo `<table>` analog — see "No Analog Found") |
| `frontend/src/components/TournamentFilterChips.jsx` *(new)* | filter UI component | URL-state, click toggles | `frontend/src/pages/PerformanceDashboard.jsx` `PERIODS` pill group (lines 158-181) | role-match (segmented control pattern) |
| `frontend/src/components/TournamentSelector.jsx` *(new)* | dropdown component | URL-state | `frontend/src/components/StatusBar.jsx` `Cell` (style tokens) | partial (native `<select>`; only style anchors) |
| `frontend/src/components/SignificanceBadge.jsx` *(new)* | pill + hover tooltip | render-only | none — see "No Analog Found" (no in-repo hover tooltip) | no-analog |
| `frontend/src/components/ContaminatedWindowWarning.jsx` *(new)* | conditional warning strip | render-only | `frontend/src/components/TileState.jsx` `ErrorState` (lines 148-202) | role-match (palette tokens + Manrope eyebrow shape) |
| `frontend/src/hooks/useTournamentSnapshot.js` *(new)* | React Query hook | request-response, manual refetch | `frontend/src/hooks/useSafetyState.js` | exact (inversion: `staleTime: Infinity`, no `refetchInterval`) |
| `frontend/src/hooks/useTournamentList.js` *(new)* | React Query hook | request-response, manual refetch | `frontend/src/hooks/useSafetyState.js` | exact (same inversion as above) |
| `frontend/src/services/api.js` *(modify — extend)* | axios API client | request shape | self at lines 42-62 (`portfolioAPI`) | self-reference (in-place extension) |
| `frontend/src/App.jsx` *(modify)* | route + nav | route registration | self at lines 184-204 (nav `<NavLink>`s) + lines 295-313 (Routes block) | self-reference |
| `services/api-gateway/app/main.py` *(modify — 2 new routes)* | FastAPI route handler | disk-read + merge | `services/api-gateway/app/main.py` `get_safety_state` (lines 1037-1153) | role-match (graceful degradation + local autoflake import + return-dict shape; disk read itself is novel) |
| `services/api-gateway/tests/test_tournament_snapshots.py` *(new)* | pytest unit test | TestClient + filesystem fixture | `services/api-gateway/tests/test_safety_state.py` | exact (`test_client` fixture, no auth, JSONResponse mock helper structure) |
| `docker-compose.unified.yml` *(modify — api-gateway volumes)* | bind-mount declaration | RO mount | self at lines 289-293 (existing api-gateway `volumes:` block) | self-reference (extend with one RO line) |
| `tests/integration/conftest.py` *(modify — add `tournament_snapshot_seeded`)* | pytest fixture | filesystem I/O | self at lines 244-298 (`notification_received` — pathlib.Path I/O sidesteps `builtins.open` mock trap) | self-reference (pattern carry-forward) |
| `tests/fixtures/tournament/smoke-fixture.json` *(new)* | committed JSON fixture | static data | `services/tournament-harness/app/leaderboard/snapshot.py` `export_snapshot()` output (lines 48-63) | role-match (mimic the schema_version/config/rows/summary block shape) |
| `tests/integration/test_dashboard_smoke.py` *(new)* | pytest-playwright smoke | browser-driven HTTP | `tests/integration/test_fresh_clone_round_trip.py` (fixture composition pattern) + pytest-playwright docs via context7 | no-analog (pytest-playwright is net-new dep) |
| `tests/integration/requirements.txt` *(modify — add pytest-playwright)* | dep list | n/a | none (file may not exist; check before modifying) | n/a |
| `.github/workflows/integration.yml` *(modify — add playwright install step)* | CI step | n/a | self at lines 24-32 (existing `pip install` step) | self-reference (insert sibling step) |
| `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` + `.json` *(modify — add Tournament row)* | doc artifact | n/a | self (existing rows in the same files) | self-reference |

---

## Pattern Assignments

### `frontend/src/hooks/useTournamentSnapshot.js` + `useTournamentList.js` (React Query, single fetch, no polling)

**Analog:** `frontend/src/hooks/useSafetyState.js` — same `useQuery` shape, but **inverted polling semantics** per D-23 (cold data, manual refetch).

**Imports + hook structure to copy** (from `useSafetyState.js` lines 1-46):
```javascript
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

export function useTournamentSnapshot(tournamentId) {
  return useQuery({
    queryKey: ['tournament-snapshot', tournamentId],
    queryFn: async () => {
      return await api.get(`/tournament/snapshots/${tournamentId}`)
    },
    enabled: !!tournamentId,
    staleTime: Infinity,            // D-23: tournaments are cold batches, never auto-poll
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: 2,
    retryDelay: 1000,
  })
}
```
*Code comment required* (CONTEXT.md "Specifics" block): `/* Tournaments are cold batches; never auto-poll. See CONTEXT.md D-23. */` — guards against future contributors "fixing" this to a 5s poll.

`useTournamentList()` is the same shape with `queryKey: ['tournament-list']`, `queryFn: () => api.get('/tournament/snapshots')`, no `tournamentId` arg, no `enabled` gate.

**Critical detail** (from `useSafetyState.js` line 30-31): the axios response interceptor (`api.js` line 34) strips `.data` — the resolved value of `api.get(...)` IS the body, NOT `response.data.data`. Plan must not double-unwrap.

---

### `frontend/src/services/api.js` (extend `tournamentAPI` block)

**Analog:** self at lines 42-62 (`portfolioAPI`). In-place extension — append a new export block.

**Pattern to follow** (from `api.js` lines 42-62):
```javascript
// Tournament endpoints (Phase 7, DASH-04)
export const tournamentAPI = {
  // List all committed snapshots (gateway reads ./services/tournament-harness/data/snapshots/*.json)
  listSnapshots: () => api.get('/tournament/snapshots'),
  // Merged snapshot + ensemble + significance for one tournament
  getSnapshot: (tournamentId) => api.get(`/tournament/snapshots/${tournamentId}`),
}
```
Convention notes (from `api.js` lines 9-15 + line 34): `baseURL: '/api'`, 20s timeout, response interceptor strips `.data`. Path is `/tournament/snapshots` (NOT `/v1/tournament/...`) per ADR-007.

---

### `frontend/src/pages/TournamentDashboard.jsx` (page composition)

**Analog:** `frontend/src/pages/PerformanceDashboard.jsx` lines 135-205 (sticky `PerfHeader` with refresh button) + lines 1014-1126 (main with max-width 88rem).

**Sticky header shape to copy** (from `PerformanceDashboard.jsx` lines 136-208):
```jsx
<header
  style={{
    position: 'sticky',
    top: 0,
    zIndex: 40,
    background: 'rgba(10, 10, 11, 0.86)',
    backdropFilter: 'blur(14px)',
    borderBottom: '1px solid var(--perf-border)',
  }}
>
  <div className="px-6 py-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
    <div className="flex items-baseline gap-4">
      <span className="perf-eyebrow">Tournament Leaderboard</span>
      <span className="perf-mono" style={{ color: 'var(--perf-text-3)', fontSize: '0.6875rem' }}>
        {format(new Date(), "yyyy-MM-dd · HH:mm 'UTC'")}
      </span>
    </div>
    {/* Refresh button (perf-mono, transparent bg, 1px border) — see PerformanceDashboard.jsx:183-205 */}
  </div>
</header>
```

**Main layout** (from `PerformanceDashboard.jsx` lines 1024-1033):
```jsx
<main
  style={{
    maxWidth: '88rem',
    margin: '0 auto',
    padding: 'clamp(1.5rem, 3vw, 2.75rem) clamp(1rem, 3vw, 2rem) 5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: 'clamp(2rem, 4vw, 3.5rem)',
  }}
>
```
Page imports `./performance-theme.css` (PerformanceDashboard.jsx line 46) to inherit `--perf-border`, `--perf-text-3`, `.perf-eyebrow`, `.perf-mono` tokens. TournamentDashboard should do the same OR inline the `C={}` token block (see KeyMetricsStrip pattern below).

**TileState wrap** (UI-SPEC layout block):
```jsx
<TileState
  query={snapshotQuery}
  title="Tournament Leaderboard"
  isEmpty={(d) => !d || !d.snapshot || d.snapshot.rows.length === 0}
  lastUpdatedAt={snapshotQuery.data?.snapshot?.exported_at}
  staleAfterMs={Infinity}            /* D-23: never auto-stale by time */
>
  <TournamentLeaderboard rows={...} ensembleMembersBySymbol={...} perSymbolSignificance={...} />
</TileState>
```
`<TileState/>` is already imported via `import TileState from '../components/TileState'` (see KeyMetricsStrip.jsx line 3).

---

### `frontend/src/components/TournamentLeaderboard.jsx` (presentational `<table>`)

**Analog:** No direct `<table>` analog in `frontend/src/components/`. The repo uses `<div>`-based card lists for tabular data (TradeHistory.jsx, ActiveTrades.jsx) and the PerformanceDashboard's `TradeStatsTable` (line 852) is a flexbox grid, not a `<table>`. Phase 7 introduces the first true semantic `<table>`. **Anchor the styling on the editorial cell vocabulary** from KeyMetricsStrip + StatusBar.

**Color token block to copy** (from `KeyMetricsStrip.jsx` lines 46-60 — same block in `TileState.jsx` lines 34-46):
```jsx
const C = {
  bg: '#0a0a0b',
  surface: '#18181c',
  surface2: '#1f1f24',
  border: '#2a2a32',
  borderStrong: '#3a3a44',
  text: '#f5f3ee',
  text2: '#a09e98',
  text3: '#8a8982',
  gain: '#5eead4',
  loss: '#fb7185',
  gold: '#d4af6a',
}
```

**Cell + eyebrow + mono numeric pattern** (from `StatusBar.jsx` lines 31-51):
```jsx
const Cell = ({ eyebrow, value, valueStyle, accent, mono = true }) => (
  <div className="flex flex-col gap-0.5 px-4 py-1.5 min-w-0" style={{ borderRight: '1px solid #2a2a32' }}>
    <span
      className="text-[9px] uppercase tracking-[0.18em] truncate"
      style={{ color: '#65645e', fontWeight: 600 }}
    >
      {eyebrow}
    </span>
    <span
      className="text-xs truncate"
      style={{
        color: accent || '#f5f3ee',
        fontFamily: mono ? 'JetBrains Mono, monospace' : 'Manrope, system-ui, sans-serif',
        fontFeatureSettings: '"tnum" 1',
        ...valueStyle,
      }}
    >
      {value}
    </span>
  </div>
)
```

**Mono numeric cell with `tnum`** (from `KeyMetricsStrip.jsx` lines 120-130) — apply to every `<td>` rendering a number:
```jsx
style={{
  color: valueColor,                        // C.gain / C.loss / C.text
  fontFamily: 'JetBrains Mono, monospace',
  fontWeight: 600,
  fontSize: 13,
  letterSpacing: '0.01em',
  fontFeatureSettings: '"tnum" 1, "zero" 1',  // critical: digits don't dance on refetch
}}
```

**Click-to-sort header**: extend the URL-search pattern from React Router; TournamentLeaderboard's `<th>` is a `<button type="button">` inside the `<th>` (a11y) that calls `onSort(column)`. No `<th>`-onclick analog in repo — use UI-SPEC `data-testid` contract (line 217 of UI-SPEC).

**Required `data-testid` surface** (UI-SPEC line 217-232 — load-bearing for smoke):
- `data-testid="tournament-leaderboard"` on `<table>` root
- `data-testid={`tournament-row-${run_id}`}` on every `<tr>` in `<tbody>`

---

### `frontend/src/components/TournamentFilterChips.jsx` (chip + segmented control)

**Analog:** `frontend/src/pages/PerformanceDashboard.jsx` lines 158-181 (PERIODS pill group).

**Pill group / segmented control pattern to copy** (from `PerformanceDashboard.jsx` lines 158-181):
```jsx
<div
  role="group"
  aria-label="Status filter"
  className="flex"
  style={{
    border: '1px solid var(--perf-border)',
    borderRadius: 4,
    overflow: 'hidden',
  }}
>
  {['success', 'failed', 'all'].map((s) => (
    <button
      key={s}
      type="button"
      className="perf-pill"
      data-active={status === s}
      aria-pressed={status === s}
      onClick={() => setStatus(s)}
      data-testid={`tournament-filter-status-${s}`}  // UI-SPEC line 226
    >
      {s.toUpperCase()}
    </button>
  ))}
</div>
```

**URL state**: react-router-dom's `useSearchParams` — no existing usage in repo (`grep -rn "useSearchParams" frontend/src/` returns nothing). Pattern is straight from react-router-dom 6 docs. Reference: D-13 lockdown in CONTEXT.md.

---

### `frontend/src/components/SignificanceBadge.jsx` + tooltip

**No in-repo analog.** Pure CSS `:hover` + absolute-positioned `<div>` pattern. UI-SPEC line 145 locks the impl shape:
- 280px max-width
- `#18181c` background, `#3a3a44` 1px border, 8px padding, 4px radius
- z-index 50 (above StatusBar's z-30 — see `StatusBar.jsx` line 114 `z-30`)
- JetBrains Mono for inner numerics, Manrope for label

**Required `data-testid` surface** (UI-SPEC line 228-229):
- `data-testid="significance-badge-pass"` on the green pill `<span>`
- `data-testid="significance-badge-none"` on the gray `—` `<span>`

---

### `services/api-gateway/app/main.py` — 2 new routes

**Analog:** `get_safety_state` at lines 1037-1153. Same shape for **graceful degradation + local imports + return-dict** — the disk-read path itself is net-new (no other gateway route reads from disk).

**Route registration + docstring shape to follow** (from `main.py` lines 1037-1077):
```python
@app.get("/api/tournament/snapshots")
async def list_tournament_snapshots():
    """List committed tournament snapshots from the RO bind-mount.

    Reads /app/snapshots/*.json (mounted from
    ./services/tournament-harness/data/snapshots:/app/snapshots:ro per
    Phase 7 D-01). Returns each file's `summary` block + `tournament_id`
    + `exported_at` so the dashboard can populate the selector dropdown.

    Unauthenticated (D-09 carryforward from Phase 6): read-only config-
    style disclosure, no secrets, no balances, no positions.

    Graceful degradation: returns 200 with `tournaments: []` when the
    snapshots directory is absent OR empty (fresh clone path, smoke
    fixture not yet seeded). Never 500.

    Does NOT depend on `tournament-harness` service running (profile=
    tournament stays opt-in per D-02). The disk read happens entirely
    inside the gateway.
    """
    # Local import — autoflake removes unused top-level imports across
    # api-gateway/main.py refactors. Pin the use site here. (Project
    # memory: feedback_main_imports_autoflake.md.)
    from pathlib import Path
    import json

    snapshots_dir = Path("/app/snapshots")
    tournaments = []
    if snapshots_dir.exists():
        for p in sorted(snapshots_dir.glob("*.json")):
            # Skip Phase 4 sidecars (*.ensemble.json, *.significance.json).
            if p.stem.endswith((".ensemble", ".significance")):
                continue
            try:
                data = json.loads(p.read_text())
                tournaments.append({
                    "tournament_id": data.get("tournament_id"),
                    "exported_at": data.get("exported_at"),
                    **(data.get("summary") or {}),
                })
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"/api/tournament/snapshots: skipping {p.name}: {e}")
                continue
    return {"success": True, "count": len(tournaments), "tournaments": tournaments}
```

**Detail-route merge pattern** (NOT a proxy — disk-read of three files, joined in memory):
```python
@app.get("/api/tournament/snapshots/{tournament_id}")
async def get_tournament_snapshot(tournament_id: str):
    """Return merged {snapshot, ensemble|null, significance|null}.

    Filename convention (Phase 3 D-18 + Phase 4 atomic-write):
      - {tournament_id}.json              (snapshot — required)
      - {tournament_id}.ensemble.json     (Phase 4; null when Phase 4 not run)
      - {tournament_id}.significance.json (Phase 4; null when Phase 4 not run)

    Returns 404 ONLY when the snapshot file is absent. The two sidecars
    are tolerated as missing (per D-05) — frontend renders "—" in the
    significance column when null.
    """
    from pathlib import Path
    import json

    base = Path("/app/snapshots")
    snap_path = base / f"{tournament_id}.json"
    if not snap_path.exists():
        raise HTTPException(status_code=404, detail=f"snapshot {tournament_id} not found")

    snapshot = json.loads(snap_path.read_text())
    ensemble = None
    significance = None
    ens_path = base / f"{tournament_id}.ensemble.json"
    sig_path = base / f"{tournament_id}.significance.json"
    if ens_path.exists():
        try:
            ensemble = json.loads(ens_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"/api/tournament/snapshots/{tournament_id}: ensemble decode failed: {e}")
    if sig_path.exists():
        try:
            significance = json.loads(sig_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"/api/tournament/snapshots/{tournament_id}: significance decode failed: {e}")
    return {"success": True, "snapshot": snapshot, "ensemble": ensemble, "significance": significance}
```

**Critical gotcha** (CLAUDE.md): tests for this route MUST run inside the api-gateway container. Host pip ships fastapi 0.136 (HTTPBearer→401); container pins 0.109 (→403). The route is unauthenticated, but follow the in-container rule for parity per `test_safety_state.py` line 17-21 comment.

---

### `services/api-gateway/tests/test_tournament_snapshots.py` (unit tests for the new routes)

**Analog:** `services/api-gateway/tests/test_safety_state.py` lines 1-120.

**Pattern to copy** (from `test_safety_state.py` lines 1-50 — `test_client` fixture, no auth override needed since route is unauthenticated):
```python
"""
Tests for the api-gateway GET /api/tournament/snapshots[/<id>] routes (Phase 7, DASH-04).

Covers:
- Empty snapshots directory → 200 {success:True, count:0, tournaments:[]}
- List endpoint reads summary block from each *.json
- Detail endpoint returns 404 when snapshot file absent
- Detail endpoint returns ensemble/significance=null when sidecars absent (D-05)
- Detail endpoint merges all three files when present

Tests MUST run inside the api-gateway container (CLAUDE.md gotcha; same as
test_safety_state.py:17-21 — host fastapi 0.136 vs container 0.109).
"""
import json
from pathlib import Path
import pytest

def test_list_empty_directory(test_client, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
    resp = test_client.get("/api/tournament/snapshots")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "count": 0, "tournaments": []}
```
The `test_client` fixture comes from `services/api-gateway/tests/conftest.py:61-64` — no `admin_client` override needed (these routes are unauthenticated per D-09).

**Filesystem mocking note** (project memory `feedback_pathlib_mocking.md`): `Path.read_text` / `Path.exists` go through `_io.open`, NOT `builtins.open` — `mock.patch("builtins.open")` is silent no-op. Patch `pathlib.Path.read_text` / `pathlib.Path.exists` directly OR use a `tmp_path`-based fixture that writes real files.

---

### `docker-compose.unified.yml` — api-gateway volume add

**Analog:** self at lines 289-293 (existing api-gateway `volumes:` block).

**Pattern to extend** (from `docker-compose.unified.yml` lines 289-293):
```yaml
volumes:
  - ./services/api-gateway/logs:/app/logs
  # RW for the gateway: it creates/overwrites the EMERGENCY_STOP file.
  # trading-engine mounts the same host file read-only.
  - ./EMERGENCY_STOP:/app/EMERGENCY_STOP
  # Phase 7 D-01: RO bind-mount of committed tournament snapshots.
  # Gateway reads /app/snapshots/*.json for /api/tournament/snapshots[/{id}].
  # tournament-harness service writes here under profile=tournament; gateway
  # never writes. RO ensures the gateway can't corrupt the committed artifact.
  - ./services/tournament-harness/data/snapshots:/app/snapshots:ro
```
No `depends_on` change required — the bind-mount is created by Docker at gateway-start regardless of whether tournament-harness is running (profile=tournament stays opt-in per D-02).

---

### `tests/integration/conftest.py` — add `tournament_snapshot_seeded` fixture

**Analog:** self at lines 244-298 (`notification_received`) — pathlib.Path I/O, function-scoped, yields/cleans up.

**Pattern to follow** (shape mirrors `notification_received` write→yield→cleanup):
```python
@pytest.fixture(scope="function")
def tournament_snapshot_seeded():
    """Seed a deterministic tournament snapshot into the gateway's bind-mount
    source directory before each smoke test, delete on teardown (D-08).

    Source: tests/fixtures/tournament/smoke-fixture.json (committed,
    6-9 deterministic rows across {SOL, BNB, ADA} x {GRU, LSTM}; one
    failed-run row to exercise failure rendering).

    Destination: services/tournament-harness/data/snapshots/smoke-tape-fixture.json
    (gateway's RO bind-mount source per D-01).

    Uses pathlib.Path for file I/O (project memory: feedback_pathlib_mocking.md;
    Path.write_text / read_text bypass builtins.open — but that mock-trap
    matters only inside unit tests, not for real I/O like this fixture).
    """
    src = _repo_root() / "tests" / "fixtures" / "tournament" / "smoke-fixture.json"
    dst_dir = _repo_root() / "services" / "tournament-harness" / "data" / "snapshots"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "smoke-tape-fixture.json"
    dst.write_text(src.read_text())
    yield dst
    dst.unlink(missing_ok=True)
```
The `_repo_root()` helper already exists in this conftest (lines 53-60). Reuse it. Function-scope is correct for a per-test seed.

---

### `tests/fixtures/tournament/smoke-fixture.json` — committed deterministic snapshot

**Analog:** `services/tournament-harness/app/leaderboard/snapshot.py` `export_snapshot()` (lines 48-63) — fixture must mimic the output schema.

**Schema to mirror** (verbatim from `snapshot.py` lines 48-63):
```python
snapshot: Dict[str, Any] = {
    "tournament_id": tournament_id,
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "schema_version": version,
    "config": config,
    "rows": rows,
    "summary": {
        "n_rows": len(rows),
        "n_success": sum(1 for r in rows if r.get("status") == "success"),
        "n_failed": sum(1 for r in rows if r.get("status") == "failed"),
        "architectures": sorted({r.get("architecture") for r in rows if r.get("architecture")}),
        "symbols": sorted({r.get("symbol") for r in rows if r.get("symbol")}),
    },
}
```
**Row columns** to populate per row (from CONTEXT.md `<canonical_refs>` "Phase 3 / Phase 4 source code": `services/tournament-harness/migrations/0001_initial.sql`): `architecture`, `symbol`, `horizon`, `target_mode`, `r2_returns`, `dir_acc_corrected`, `oos_sharpe`, `psr`, `dsr`, `cpcv_dsr`, `train_seconds`, `git_sha`, `tournament_start_ts`, `train_window_includes_contaminated`, `status`, `failure_reason`, `failure_stderr_tail`, `run_id`, `hp_hash`.

**Fixture must set `train_window_includes_contaminated=false` on every row** so `<ContaminatedWindowWarning/>` does NOT render (UI-SPEC line 230 — smoke asserts absence of `data-testid="contaminated-warning"`).

---

### `tests/integration/test_dashboard_smoke.py` — pytest-playwright audit-driven smoke

**Analogs (partial — pytest-playwright itself is net-new):**
- Fixture composition pattern → `tests/integration/test_fresh_clone_round_trip.py` (depends on `bootstrap_stack`, `tape_reset`, optional new fixtures)
- pytest-playwright `page` fixture API → context7 docs (no in-repo consumer; pull at plan-time)

**Smoke-driver pattern** (from CONTEXT.md D-15 — read `06-TILE-AUDIT.json` at runtime, switch on `verdict`):
```python
"""Phase 7 DASH-06 — audit-driven Playwright smoke.

Reads .planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json
at runtime; per-row assertion logic switches on `verdict`:
  - FIXED          -> tile selector visible + body non-empty
  - LABELED_STALE  -> [data-testid="tile-stale-badge"] present within tile
  - REMOVED        -> component file's root selector absent

Runs against http://localhost:8000 (gateway origin per UI-SPEC Claude's
Discretion lock) — mirrors prod ingress path, not the vite dev proxy.
"""
import json
import pytest
from pathlib import Path

@pytest.fixture(scope="session")
def tile_audit():
    audit_path = (
        Path(__file__).resolve().parents[2]
        / ".planning" / "phases" / "06-dashboard-audit-safety-state"
        / "06-TILE-AUDIT.json"
    )
    return json.loads(audit_path.read_text())

def test_every_audited_tile_renders_per_verdict(
    page,                          # pytest-playwright fixture
    bootstrap_stack,               # Phase 2 fixture — stack up via bootstrap.sh
    tape_reset,                    # Phase 2 — deterministic tape position
    tournament_snapshot_seeded,    # Phase 7 — D-08 fixture
    tile_audit,                    # this file
):
    page.goto("http://localhost:8000/")  # gateway origin
    for row in tile_audit["tiles"]:
        verdict = row["verdict"]
        # ... per-verdict assertion (FIXED/LABELED_STALE/REMOVED)
```

**Required `data-testid` selectors** are the stable contract — see UI-SPEC line 217-232 + the Tournament-tile audit row to be appended at `06-TILE-AUDIT.json` per D-16.

---

### `.github/workflows/integration.yml` — add Playwright install step

**Analog:** self at lines 24-32 (existing `Install pytest dependencies` step).

**Insert this step BEFORE the existing `Run integration suite` step at line 49** (D-18 + D-20):
```yaml
      - name: Install Playwright browsers
        run: |
          pip install pytest-playwright>=0.5
          playwright install --with-deps chromium
```
The new smoke test runs as part of the existing `pytest tests/integration -v --tb=short` invocation at line 56 — no parallel job, no separate `npx playwright test` shim (D-18). Same workflow appended to `.github/workflows/integration-ml-on.yml`.

---

### `frontend/src/App.jsx` — route registration + nav link

**Analog:** self at lines 184-204 (existing `<NavLink>`s in desktop nav) + lines 295-313 (Routes block).

**Nav link addition** (insert after "Phase 3" NavLink at line 192-194):
```jsx
<NavLink to="/tournament">
  Tournament
</NavLink>
```
(Place after "Phase 3" per CONTEXT.md `<canonical_refs>` "Existing frontend" instruction.)

**Route registration** (insert in the Routes block at line 295-313):
```jsx
<Route path="/tournament" element={<TournamentDashboard />} />
```
And import at top: `import TournamentDashboard from './pages/TournamentDashboard'` (line 30-35 import block).

**Mobile menu update** (line 115-122 `navItems` array) — append `{ to: '/tournament', label: 'Tournament' }`.

---

### `frontend/vite.config.js` — NO MODIFICATION REQUIRED

The new `/api/tournament/*` routes hit the existing `/api` fallback block at lines 191-198 in `vite.config.js` — that block proxies any unmatched `/api/*` to `http://localhost:8000` (gateway). No new proxy entry needed.

Smoke test targets `http://localhost:8000` (gateway) directly per UI-SPEC's locked Claude's Discretion choice — bypasses the vite dev proxy entirely in CI.

---

### `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` + `.json` — add Tournament row

**Analog:** self (existing rows in same files).

**JSON row to append** (verbatim from UI-SPEC line 240-252):
```json
{
  "tile": "TournamentLeaderboard",
  "page": "Tournament",
  "component_file": "frontend/src/components/TournamentLeaderboard.jsx",
  "hooks": ["useTournamentList", "useTournamentSnapshot"],
  "endpoint": "/api/tournament/snapshots/{tournament_id}",
  "expected_shape": { "snapshot": "object", "ensemble": "object|null", "significance": "object|null" },
  "verdict": "FIXED",
  "last_updated_at_emitter": "yes",
  "data_testid": "tournament-leaderboard",
  "notes": "Phase 7 tile. Seeded by tests/fixtures/tournament/smoke-fixture.json via tournament_snapshot_seeded pytest fixture (D-08). exported_at drives <TileState/> last_updated_at but staleAfterMs=Infinity per D-23."
}
```

**Markdown row** (matching existing 06-TILE-AUDIT.md table style, lines 25-32) — add a new "Tournament page tiles" section to the markdown file.

---

## Shared Patterns

### Editorial Trading Floor color tokens (apply to ALL new frontend files)

**Source:** `frontend/src/components/TileState.jsx` lines 34-46 OR `frontend/src/components/KeyMetricsStrip.jsx` lines 46-60 (identical block — already lifted from `performance-theme.css`).

```jsx
const C = {
  bg: '#0a0a0b', surface: '#18181c', surface2: '#1f1f24',
  border: '#2a2a32', borderStrong: '#3a3a44',
  text: '#f5f3ee', text2: '#a09e98', text3: '#8a8982',
  gain: '#5eead4', loss: '#fb7185', gold: '#d4af6a',
}
```
Inline this block in every new component file. Do NOT create a shared tokens module (out of scope per Phase 6 06-PATTERNS.md line 612). UI-SPEC Color section locks the same hex values.

### JetBrains Mono numeric cell with tabular figures

**Source:** `frontend/src/components/KeyMetricsStrip.jsx` line 129 + `frontend/src/components/StatusBar.jsx` line 44.

```jsx
style={{
  fontFamily: 'JetBrains Mono, monospace',
  fontFeatureSettings: '"tnum" 1, "zero" 1',  // digits don't dance on refetch
  letterSpacing: '0.01em',
}}
```
Apply to every numeric `<td>` in TournamentLeaderboard (DSR, OOS Sharpe, PSR, Dir.Acc, R², Train Seconds) and every numeric inside the SignificanceBadge tooltip.

### Eyebrow label (10px Manrope, 0.18em tracking, uppercase, weight 600)

**Source:** `frontend/src/components/StatusBar.jsx` lines 33-37 + `frontend/src/components/KeyMetricsStrip.jsx` lines 102-110 + `frontend/src/components/TileState.jsx` lines 128-136.

```jsx
<span
  style={{
    color: '#65645e',  // or C.text3
    fontSize: 10,
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    fontWeight: 600,
    fontFamily: 'Manrope, system-ui, sans-serif',
  }}
>
  TOURNAMENT
</span>
```
Use for every `<th>` label, the tournament-selector label, the filter-group labels (SYMBOLS / ARCHITECTURE / STATUS).

### Graceful degradation in gateway routes (return 200 with safe defaults, never 500)

**Source:** `services/api-gateway/app/main.py` lines 1078-1108 (`get_safety_state` try/except for trading-engine proxy failures).

Apply to BOTH new tournament routes: missing snapshot file? `list` returns `tournaments: []`. Sidecars missing? `detail` returns `ensemble: null, significance: null`. Decode failure on a single file? Log + skip + continue. The dashboard `<TileState/>` carries the user-facing affordance — the gateway never 500s.

### Local autoflake-safe imports

**Source:** `services/api-gateway/app/main.py` lines 1139-1143 (`from datetime import timezone as _tz` inside the function).

Per project memory `feedback_main_imports_autoflake.md`: autoflake strips unused top-level imports during refactors. Pin use-site imports (`from pathlib import Path`, `import json`) inside the route function body for any new symbols not already used elsewhere in `main.py`.

### Pathlib I/O over `builtins.open` mocking

**Source:** project memory `feedback_pathlib_mocking.md` + `tests/integration/conftest.py` line 254 comment + line 261 `log_path.read_text()`.

`pathlib.Path.read_text` / `write_text` go through `_io.open` (C-level), NOT `builtins.open`. `mock.patch("builtins.open")` is silently a no-op. For unit tests against the new gateway routes, patch `pathlib.Path.read_text` / `pathlib.Path.exists` directly, OR (preferred) use real files in a `tmp_path` fixture.

---

## No Analog Found

Files / patterns with no close match in the codebase (planner falls back to RESEARCH.md + context7 + UI-SPEC):

| File / Pattern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| `services/api-gateway/app/main.py` (disk-read routes) | gateway route | filesystem read | Every existing gateway route either reads local env or proxies via `ServiceProxy`. Disk-reading from a bind-mount is new. **Mitigation:** mirror the graceful-degradation shape of `get_safety_state` (lines 1037-1153) — the disk-read body itself is straightforward `Path.glob` + `json.loads`. |
| `frontend/src/components/SignificanceBadge.jsx` (hover tooltip) | UI component | render-only | `grep -rn "onMouseEnter\|:hover" frontend/src/components/` returns one hit (CommandPalette.jsx line 314 — unrelated activeIdx tracking). No existing absolute-positioned hover tooltip. **Mitigation:** UI-SPEC line 145 locks the impl shape (280px max-width, z-index 50 above StatusBar's z-30, palette anchors); executor owns first impl. |
| `tests/integration/test_dashboard_smoke.py` (pytest-playwright) | smoke test | browser-driven HTTP | No existing pytest-playwright consumer. `tests/integration/test_fresh_clone_round_trip.py` carries fixture composition pattern only. **Mitigation:** pull pytest-playwright API via context7 at plan-time (`page` fixture, screenshot-on-failure config). UI-SPEC line 217-232 locks the `data-testid` contract. |
| `frontend/src/components/TournamentLeaderboard.jsx` (raw `<table>`) | presentational | render-only | No `<table>` in `frontend/src/components/`. TradeHistory.jsx / ActiveTrades.jsx use `<div>` cards; TradeStatsTable (PerformanceDashboard.jsx:852) is a flexbox grid. **Mitigation:** anchor styling on KeyMetricsStrip `Cell` + StatusBar `Cell` patterns; semantic `<table>` markup is straight HTML (no project convention to violate). |
| `frontend/src/components/TournamentFilterChips.jsx` (URL-search filter state) | filter UI | URL params | `grep -rn "useSearchParams" frontend/src/` returns zero hits. Phase 6 dashboard tiles do NOT currently use URL params — D-13 says "same React Router `useSearchParams` pattern that Phase 6 dashboard tiles use" but the pattern is in fact net-new to this repo. **Mitigation:** straight react-router-dom 6 API (`const [params, setParams] = useSearchParams()`), no project convention to follow. |

---

## Metadata

**Analog search scope:** `frontend/src/{components,hooks,pages,services}/`, `services/api-gateway/app/{main.py,services/}`, `services/api-gateway/tests/`, `services/tournament-harness/app/leaderboard/`, `tests/integration/`, `docker-compose.unified.yml`, `.github/workflows/`, `.planning/phases/06-dashboard-audit-safety-state/`

**Files scanned:** 17 source files Read in full or in targeted ranges; ~30 files surfaced via Grep.

**Project skills applicable:** None for the planning artifacts themselves. `start-system` (referenced for stack-up in smoke) is already encapsulated by Phase 2's `bootstrap_stack` fixture — no direct invocation needed.

**Project-rule guardrails carried through:**
- ADR-007: no `/v1/` prefix on gateway routes (`/api/tournament/snapshots`, NOT `/api/v1/tournament/...`)
- D-09 Phase 6 carry: new endpoints are unauthenticated read-only
- CLAUDE.md gateway test gotcha: new gateway unit tests run inside the api-gateway container (`docker exec crypto-bot-api-gateway pytest`); smoke runs outside (HTTP-driven, fastapi-version-insulated)
- Project memory `feedback_main_imports_autoflake.md`: local imports for new symbols inside route bodies
- Project memory `feedback_pathlib_mocking.md`: patch `pathlib.Path.*` directly or use `tmp_path`, never `builtins.open`

**Pattern extraction date:** 2026-05-14

---

## PATTERN MAPPING COMPLETE
