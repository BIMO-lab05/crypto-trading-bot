# LIVECLOSE-05 — LIVE-flip Manual Smoke Runbook

**Audience:** Operator running the Phase 11.1 LIVECLOSE-05 carry-in closure
(`OP-01` DASH-03 LIVE-flip manual smoke).
**Scope:** One supervised attended-session smoke test that temporarily flips
the api-gateway container to `TRADING_MODE=LIVE`, captures a dashboard
screenshot showing the LIVE-mode visual treatment (rose viewport outline,
red MODE pill, KILL-SWITCH state), then reverts to `TRADING_MODE=PAPER`.
**Tooling:** `scripts/closure/liveclose-05-live-flip-smoke.sh` (operator-
runnable bash harness with EXIT-trap revert and two-key authorization).

---

## Goal

Produce screenshot evidence proving that the dashboard renders the LIVE-mode
visual treatment correctly when api-gateway is flipped to `TRADING_MODE=LIVE`.
This is one of the five LIVECLOSE carry-in closures gating the Phase 11
"Path-to-LIVE Tile" milestone (DASH-03 carry-forward).

**Why this is operator-only:** the visual smoke itself — confirming the rose
viewport outline, red MODE pill, and KILL-SWITCH state actually render on
the running React frontend — cannot be asserted programmatically by pytest
without a full Playwright browser session. The decision recorded in the plan
threat-model (T-11.1-06-04) accepts that "screenshot is operator-only" with
no programmatic anti-fabrication mitigation in scope. The harness exists to
lock the docker-compose recipe + curl probe contract, run the revert step
reliably, and emit machine-readable evidence — NOT to replace the human
visual inspection.

---

## Safety preconditions

1. **No destructive working-tree wipe** anywhere near the source tree
   (project rule, from CLAUDE.md "Security" — see the prohibited-commands
   list under "Security"). Use targeted `git restore <path>` if you need
   to discard a file.
2. **`PAPER_TRADING_MODE` may remain `true`** on the trading-engine for the
   duration of this smoke — no real orders go out (CLAUDE.md "Trading-mode
   flags"). This harness exercises the dashboard's LIVE-mode rendering,
   NOT real order placement.
3. **Two-key authorization** is enforced before the flip: the operator
   must set BOTH `LIVECLOSE_05_SUPERVISED_RUN=1` AND
   `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`. Missing either exits the
   harness with a clear error code (1 or 2).
4. **EXIT trap revert** restores `TRADING_MODE=PAPER` on every supervised
   run regardless of outcome (script success, error, SIGTERM, SIGINT).
   SIGKILL bypasses the trap by kernel design — the script header documents
   this corner case.

---

## Pre-flip Diagnose / Action / Verification table

| Symptom | Action | Verification |
|---|---|---|
| Trading-engine boots with `LIVE_PREFLIGHT_REJECTED reason=cap_too_high` | Pre-LIVE checklist incomplete — RESTORE per-trade cap to 2% per `RUNBOOK.md` "Pre-LIVE Operator Checklist" Precondition 1 (paper-relaxed cap is 10% per ADR-010) | Re-run `python3 scripts/preflight_live.py --check=cap` exits 0 |
| `curl /api/preflight/live-readiness` returns `"overall": "UNKNOWN"` with all checks UNKNOWN | api-gateway cannot reach trading-engine | `docker compose -f docker-compose.unified.yml ps trading-engine` shows healthy; if not, `docker compose ... restart trading-engine` then re-probe |
| `docker compose ... up -d --force-recreate api-gateway` hangs | WSL2 BuildKit issue documented in CLAUDE.md "Environment" | `export DOCKER_BUILDKIT=0` before re-running the harness |
| Dashboard screenshot doesn't show rose viewport outline | `PathToLiveTile.jsx` didn't load OR Phase 10 DASHLIVE-01 regressed | Inspect `frontend/src/components/PathToLiveTile.jsx` for the `bg-rose-700` Tailwind class on the banner when `overall === "DO_NOT_FLIP"` |
| Probe returns 404 | api-gateway container predates Phase 8 PREFLIGHT-01 deployment (route added at `services/api-gateway/app/main.py:1168`) | `docker compose -f docker-compose.unified.yml build --no-cache api-gateway && docker compose ... up -d --force-recreate api-gateway` |
| Revert step fails or times out (30s ceiling) | Compose daemon unhealthy or stuck | Manually run: `TRADING_MODE=PAPER docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway` |

---

## 5-step Operator Workflow

This is the canonical 5-step path. Run each step in order; do NOT skip the
pre-flip probe (Step 1) — the harness refuses to flip without a known
PAPER baseline.

### Step 1 — Confirm starting PAPER state

```bash
# Should return JSON with schema_version=1, 6 checks, trading_mode + paper_mode present.
curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool
```

Expected: top-level keys `schema_version`, `overall`, `evaluated_at`, `checks`;
exactly 6 entries in `checks` with names `cap`, `paper_mode`, `trading_mode`,
`ack`, `emergency_stop`, `dsr_evidence`. The harness performs the same probe
internally and exits with code 3 (`PRE_FLIP_PROBE_FAILED`) if the shape is
wrong.

If you get a 404 here, your api-gateway container predates Phase 8
PREFLIGHT-01 — rebuild + redeploy per the Diagnose/Action table above.

### Step 2 — Export the four flags + supervised-run acknowledgement

```bash
# Four-flag friction for LIVE (CLAUDE.md "Trading-mode flags"). All four must
# be exported in the shell that runs the harness; the harness only sets the
# api-gateway env (TRADING_MODE=LIVE + LIVE_TRADING_ACK) on the compose
# call — PAPER_TRADING_MODE and BYBIT_TESTNET stay as configured in .env.
export LIVECLOSE_05_SUPERVISED_RUN=1
export LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY

# Optional override (default http://localhost:8000):
# export LIVECLOSE_05_GATEWAY_URL=http://localhost:8000
```

The harness exits 1 if `LIVECLOSE_05_SUPERVISED_RUN` is unset, and exits 2 if
`LIVE_TRADING_ACK` is missing or has the wrong value.

### Step 3 — Run the harness

```bash
bash scripts/closure/liveclose-05-live-flip-smoke.sh
```

The script:

1. Pre-flip probe — confirms PAPER baseline (exits 3 on failure).
2. Registers the EXIT trap (revert always runs from this point on).
3. Flips api-gateway via env-prefix compose: `TRADING_MODE=LIVE LIVE_TRADING_ACK=... docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway`.
4. Waits 10s for healthcheck; probes again under LIVE.
5. Prints `OPERATOR ACTION` lines and waits up to 120s for ENTER (or auto-reverts after timeout).

### Step 4 — Visual inspection + screenshot (operator-only)

While api-gateway is in LIVE mode (between the LIVE probe and ENTER):

1. Open `http://localhost:3000` in your browser (Vite dev origin OR the
   gateway origin at `:8000` — both serve the same React app; the gateway
   origin exercises the production ingress path).
2. Confirm the dashboard is rendering the LIVE-mode visual treatment:
   - **Rose viewport outline** — the `PathToLiveTile.jsx` banner has the
     `bg-rose-700` Tailwind class when `overall === "DO_NOT_FLIP"` (Phase 10
     DASHLIVE-01).
   - **Red MODE pill** — `StatusBar.jsx` uses `modeAccent = '#fb7185'`
     (rose-400 hex) when `tradingMode === "LIVE"`.
   - **KILL-SWITCH state** — visible in the StatusBar; consult Phase 10
     DASHLIVE-02 for the expected indicator.
3. Capture a screenshot of the full dashboard showing all three elements.
   Save as `.planning/evidence/LIVECLOSE-05/screenshot-<utc_ts>.png` using
   a UTC timestamp in `YYYYMMDDTHHMMSSZ` format to match the harness
   evidence-JSON naming convention.

### Step 5 — Trigger revert + commit evidence

Back in the harness terminal, press ENTER. The EXIT trap runs:

1. `TRADING_MODE=PAPER docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway` (timeout 30s).
2. Waits 10s, probes `/api/preflight/live-readiness` again, asserts
   the response matches the documented shape (schema_version=1 +
   trading_mode + paper_mode).
3. Writes evidence JSON via `python3 -m scripts.closure._common write-evidence` with `--status AWAITING_HUMAN --human-needed`.

Then commit:

```bash
git add .planning/evidence/LIVECLOSE-05/
git commit -m "evidence(LIVECLOSE-05): LIVE-flip smoke screenshot + harness evidence"
```

Finally, flip the LIVECLOSE-05 row in `.planning/state/carry_ins.json` from
`open` to `closed` and commit.

---

## Cross-references

- [RUNBOOK.md "Pre-LIVE Operator Checklist"](../../RUNBOOK.md#pre-live-operator-checklist) — the six preconditions
  the operator works through before any LIVE-flip. This LIVECLOSE-05 smoke
  is downstream of all six.
- `.planning/PROJECT.md` — "Out of Scope" LIVE-default note: paper trading
  is the default mode; LIVE requires four-flag friction.
- Phase 8 `PREFLIGHT-01` / `PREFLIGHT-02` — the `/api/preflight/live-readiness`
  endpoint shipped here. Trading-engine boot-time guard enforces
  `LIVE_TRADING_ACK == "I_UNDERSTAND_REAL_MONEY"` (PREFLIGHT-02).
- Phase 10 `DASHLIVE-01` / `DASHLIVE-04` — the dashboard's Path-to-LIVE
  tile + rose-outline visual treatment.
- `scripts/closure/_common.py` — shared `write_evidence()` helper (Phase
  11.1 Plan 01 foundation).

---

## Safety notes

- **NEVER** run a destructive working-tree wipe (the prohibited git
  commands documented in CLAUDE.md "Security" — including the `clean`
  family with destructive flags). Use targeted `git restore <path>`
  if needed.
- **EXIT trap revert** runs on every supervised flip path. The only way to
  end up stranded in `TRADING_MODE=LIVE` is SIGKILL or a daemon crash mid-
  flip. Recovery: run `bash scripts/closure/liveclose-05-live-flip-smoke.sh --revert-only`
  which bypasses the supervised-run guard (revert IS the safety op) and
  restores `TRADING_MODE=PAPER`.
- **`PAPER_TRADING_MODE` is NOT flipped by this harness.** `TRADING_MODE=LIVE`
  on api-gateway alone is a "half-state" — the dashboard renders LIVE-mode
  visuals but the trading-engine still refuses to place real orders
  because `PAPER_TRADING_MODE=true` (and the trading-engine's PREFLIGHT-02
  boot guard requires the full four-flag combo to actually trade real
  money). This is INTENTIONAL — it gives operators a safe visual-only
  smoke without ever risking real capital. CLAUDE.md "Trading-mode flags"
  documents the four-flag friction.
- **30s timeout** on the revert step bounds DoS risk from a hung docker
  daemon (threat T-11.1-06-06). If the revert times out, the operator
  must manually re-run the revert recipe shown in the harness `--help`
  output.
- **Two-key authorization** (`LIVECLOSE_05_SUPERVISED_RUN` +
  `LIVE_TRADING_ACK`) mitigates threat T-11.1-06-01 (elevation of
  privilege via unsupervised LIVE flip). Both must be present; either
  missing is a hard exit BEFORE any docker invocation.
- **TRADING_MODE=PAPER must be observable** in the post-revert probe
  response — the harness asserts the response shape but does NOT
  programmatically parse the `trading_mode` check's status field (that
  is an integration-test responsibility owned by
  `tests/e2e/test_liveclose_05_smoke.py`).
- The harness is **idempotent on `--revert-only`** — operators can re-run
  it as many times as needed if a previous run was interrupted at any
  point after the initial `--force-recreate api-gateway` call.
