---
phase: 03-tournament-harness-core
plan: "01"
subsystem: infra
tags: [docker, fastapi, pydantic-settings, compose-profiles, tournament-harness, sqlite, timescaledb]

# Dependency graph
requires:
  - phase: 02-integration-test-suite-runbook
    provides: bootstrap.sh canonical bring-up; --profile gating pattern; CI workflow conventions
provides:
  - services/tournament-harness/ skeleton (Dockerfile, requirements.txt, app/ module, migrations/ placeholder)
  - port 8010 allocated to tournament-harness (verified free vs existing 12 services)
  - docker-compose.unified.yml tournament-harness stanza behind profiles:[tournament] (D-01 — opt-in only)
  - /var/run/docker.sock bind-mount in compose stanza (D-02 — Docker SDK orchestration)
  - TournamentSettings (Pydantic-Settings v2 singleton) with TimescaleDB tournament_reader role config (D-09) + runner_image:latest (D-05)
  - read-only FastAPI surface per CD-07 (/health, GET /api/v1/tournaments stubs)
  - .gitignore overrides so D-18 snapshot JSON is committable while leaderboard.db / results/ are ignored
affects: [03-02, 03-03, 03-04, 03-05, 03-06, 03-07, 03-08, 03-09]

# Tech tracking
tech-stack:
  added:
    - "docker==7.0.0 (Docker SDK for Python — D-02)"
    - "pyyaml==6.0.1 (D-11 tournament.yaml parser, used in 03-04)"
    - "fastapi==0.104.1 + pydantic-settings==2.1.0 (matched ml-retraining-service stack)"
    - "tensorflow==2.15.0 + pandas==2.1.4 + numpy==1.26.2 (binary-compat lockstep with ml-retraining-service for CD-01 model-registry imports)"
  patterns:
    - "Service-per-directory under services/ (matches existing 11 services)"
    - "Pydantic-Settings v2 singleton (mirrors services/ml-retraining-service/app/config/settings.py)"
    - "FastAPI lifespan + read-only API skeleton (mirrors ml-retraining-service main.py minus mutation paths)"
    - "compose --profile <name> opt-in pattern (mirrors ml-prediction profiles:[ml] and sentiment-analysis profiles:[analytics])"
    - "Skeleton image now; build context flips to repo root in 03-06 for metrics-bridge import"

key-files:
  created:
    - "services/tournament-harness/Dockerfile (Python 3.11-slim, EXPOSE 8010, healthcheck via httpx)"
    - "services/tournament-harness/requirements.txt (TF 2.15 + docker SDK + pyyaml; no SQLAlchemy/Alembic/APScheduler/Redis per D-17/D-12)"
    - "services/tournament-harness/migrations/.gitkeep (placeholder so 03-03 can drop SQL migrations without rewriting Dockerfile)"
    - "services/tournament-harness/app/__init__.py + app/config/__init__.py (empty module stubs)"
    - "services/tournament-harness/app/config/settings.py (TournamentSettings class; service_port=8010; tournament_reader DB role; runner_image:latest)"
    - "services/tournament-harness/app/main.py (lifespan + /health + GET /api/v1/tournaments stub + GET /api/v1/tournaments/{tid} stub; NO @app.post — CD-07)"
  modified:
    - "docker-compose.unified.yml (tournament-harness stanza inserted between ml-prediction and sentiment-analysis; profiles:[tournament]; depends_on timescaledb; /var/run/docker.sock mount)"
    - ".gitignore (un-ignore overrides for snapshot dir to prevent the existing root-level `data/` rule from shadowing committable D-18 JSON snapshots; deny rules for *.db / results/)"

key-decisions:
  - "Skeleton image build context = ./services/tournament-harness for now; flips to repo root in 03-06 for metrics-bridge COPY (per plan output note — do NOT claim end-to-end image-build verification at this stage)"
  - "migrations/ created as empty dir with .gitkeep so Dockerfile COPY layer ordering is stable across 03-01 -> 03-03 (Rule 3 inline fix — the COPY would otherwise break docker compose build before 03-03 lands)"
  - ".gitignore needs un-ignore overrides because the existing root-level `data/` rule (line 120) was shadowing the entire services/tournament-harness/data/ tree, including committable snapshots (Rule 2 fix — D-18 mandates snapshot JSON be committable)"
  - "CORS allow_origins=['*'] kept as project-wide pattern match (ml-retraining + ml-prediction both ship this); semgrep WARNING acknowledged as informational (severity below config.json security_block_on=high threshold); service is profile-gated read-only with no auth flow"

patterns-established:
  - "Profile-gated tournament services follow ml-prediction's profiles:[ml] / sentiment-analysis's profiles:[analytics] template — keep default bootstrap.sh up lean; operator opts in with --profile tournament"
  - "Read-only API + CLI mutation split (CD-07): main.py has zero @app.post; mutation flows live in app/cli.py landing in 03-08"
  - "Pin lockstep with ml-retraining-service for ML libs (TF 2.15, pandas 2.1.4, numpy 1.26.2) so CD-01 model-registry imports stay binary-compatible — bumping one without the other breaks the registry import path"

requirements-completed: [TOURN-01]

# Metrics
duration: 20min
completed: 2026-05-08
---

# Phase 3 Plan 03-01: Service skeleton + compose profile Summary

**tournament-harness service skeleton (FastAPI + Pydantic-Settings + Dockerfile) with profile-gated docker-compose stanza on port 8010 and gitignore overrides preserving D-18 snapshot commit-ability.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-05-08T23:23:45Z
- **Completed:** 2026-05-08T23:44:17Z
- **Tasks:** 3 of 3
- **Files modified:** 9 (7 new, 2 modified)

## Accomplishments

- Stood up `services/tournament-harness/` directory matching the 11-existing-service convention — Dockerfile, requirements.txt, app/ module skeleton, migrations/ placeholder
- Port 8010 allocated and verified free against existing 12 services in `docker-compose.unified.yml` (8000-8009 + 5432/5433/6379/15672/9090/3001/3000)
- `tournament-harness` compose stanza wired behind `profiles: [tournament]` so default `bootstrap.sh up` ignores it (D-01 contract holds: 0 occurrences in default `compose config`, 7 occurrences with `--profile tournament`)
- `/var/run/docker.sock` bind-mount in place (D-02) with documented privilege-boundary header comment in the compose stanza
- TournamentSettings Pydantic-Settings v2 singleton loads TimescaleDB connection params via `tournament_reader` read-only role (D-09) and exposes `runner_image='crypto-bot-tournament-harness:latest'` for D-05 single-image runner pattern
- FastAPI surface boots cleanly: in-process TestClient verified `GET /health` returns `{status:healthy, service:tournament-harness, timestamp:...}`, `GET /api/v1/tournaments` returns `{success:true, count:0, tournaments:[]}` (CD-07 read-only stubs; full LeaderboardDB wiring lands in 03-08)
- `.gitignore` un-ignore overrides preserve D-18 snapshot commit-ability (without them, the existing root-level `data/` rule on line 120 would silently shadow the entire snapshot tree)
- TOURN-07 grep gate (`grep -r 'def directional_accuracy|def sharpe|def deflated' services/tournament-harness/`) returns 0 matches — gate green at this skeleton stage

## Task Commits

Each task committed atomically on `worktree-agent-a559742729f9e9155`:

1. **Task 1: Dockerfile + requirements.txt + migrations placeholder** - `7000433` (feat)
2. **Task 2: FastAPI status app + Pydantic settings** - `b7f61ba` (feat)
3. **Task 3: compose stanza + gitignore overrides** - `a0ca58b` (feat)

## Files Created/Modified

- `services/tournament-harness/Dockerfile` - Python 3.11-slim base with libpq-dev/gcc system deps; resilient pip env vars (PIP_DEFAULT_TIMEOUT=600, PIP_RETRIES=10); EXPOSE 8010; httpx healthcheck; CMD launches `uvicorn app.main:app`
- `services/tournament-harness/requirements.txt` - TF 2.15 / pandas 2.1.4 / numpy 1.26.2 in lockstep with ml-retraining-service; docker==7.0.0 SDK; pyyaml==6.0.1; asyncpg==0.29.0; explicitly NO SQLAlchemy/Alembic/APScheduler/Redis (D-17, D-12)
- `services/tournament-harness/migrations/.gitkeep` - placeholder so Dockerfile `COPY migrations/ ./migrations/` layer is stable; SQL files land here in 03-03
- `services/tournament-harness/app/__init__.py` - empty package marker
- `services/tournament-harness/app/config/__init__.py` - empty package marker
- `services/tournament-harness/app/config/settings.py` - TournamentSettings (Pydantic-Settings v2) with service config, default resource caps (D-04), storage paths, TimescaleDB tournament_reader role, runner_image:latest, get_settings() singleton
- `services/tournament-harness/app/main.py` - FastAPI app with lifespan (no scheduler — D-12; no DB-init on boot), /health endpoint, /api/v1/tournaments + /api/v1/tournaments/{tid} read-only stubs (CD-07); NO @app.post endpoints
- `docker-compose.unified.yml` - tournament-harness stanza inserted between ml-prediction (line ~728) and sentiment-analysis (line ~768); 56 lines added including the privilege-boundary comment block; depends_on timescaledb service_healthy; /var/run/docker.sock bind-mount; profiles:[tournament]; deploy.resources cpus=2.0/memory=4G
- `.gitignore` - 22 lines added at end: un-ignore overrides for `services/tournament-harness/data/` and `services/tournament-harness/data/snapshots/` precede the deny rules for `*.db` / results/ / logs / snapshots/*.db

## Decisions Made

- **Skeleton image build context** = `./services/tournament-harness` for now; will flip to repo root in 03-06 so the orchestrator can `COPY services/ml-retraining-service/app /opt/ml_retraining/app` for the metrics-bridge import (TOURN-07). Per plan output note, this SUMMARY does NOT claim "end-to-end image build verified" — only that the structural acceptance gates pass (`docker compose config` profile gating; in-process FastAPI TestClient smoke).
- **migrations/.gitkeep placeholder** added inline (Rule 3 — blocking issue auto-fix). Without it, `docker compose --profile tournament build tournament-harness` would fail at the `COPY migrations/ ./migrations/` layer because 03-03 hasn't dropped SQL files yet. Document for 03-03 that the dir is already in place.
- **`.gitignore` un-ignore overrides** added inline (Rule 2 — missing critical functionality for D-18 correctness). Empirical `git check-ignore -v services/tournament-harness/data/snapshots/abc.json` against the plan-only entries showed `.gitignore:120:data/` shadowing the snapshot tree. Without the un-ignore lines, D-18's commit-able snapshot artifact contract silently fails when a future plan tries to commit one.
- **CORS** kept at `allow_origins=["*"]` to match project-wide pattern (ml-retraining-service main.py:99-105, ml-prediction-service same shape). Semgrep WARNING (CWE-942) acknowledged as informational — severity below `config.json` `workflow.security_block_on=high` threshold. Service is profile-gated default-off + read-only + no auth flow, so the warning is intent-signal not exploitability.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added `migrations/.gitkeep` placeholder so Dockerfile COPY layer is stable**
- **Found during:** Task 1 (Dockerfile creation)
- **Issue:** Plan instructs `COPY migrations/ ./migrations/` line in Dockerfile so 03-03 can drop SQL files in. Without an actual `migrations/` dir, `docker compose build tournament-harness` would fail at that layer — the literal acceptance command in Task 3 (`docker compose -f docker-compose.unified.yml --profile tournament build tournament-harness`) would not execute cleanly, and 03-02 cannot start its image-dependent work.
- **Fix:** Created `services/tournament-harness/migrations/.gitkeep` with a 2-line comment explaining the placeholder role. 03-03 drops `0001_initial.sql` etc. into the same dir without a Dockerfile rewrite.
- **Files modified:** services/tournament-harness/migrations/.gitkeep (new)
- **Verification:** Dir exists with the placeholder file; the Dockerfile COPY directive resolves; structural grep tests in Task 1 acceptance pass.
- **Committed in:** 7000433 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added `.gitignore` un-ignore overrides so D-18 snapshot JSON stays committable**
- **Found during:** Task 3 (.gitignore modification)
- **Issue:** Empirical `git check-ignore -v services/tournament-harness/data/snapshots/abc.json` against the plan's specified entries returned `.gitignore:120:data/`. The pre-existing root-level `data/` rule (added long before this phase) matches any directory named `data` anywhere in the tree, silently shadowing the entire `services/tournament-harness/data/` subtree — including the snapshot JSON D-18 mandates be committable. Plan-as-written would let a future plan `git add data/snapshots/{tournament_id}.json` and have git silently drop the file, breaking the Phase 4 (TOURN-05) and Phase 7 (DASH-04) consumer contract.
- **Fix:** Added `!services/tournament-harness/data/` and `!services/tournament-harness/data/snapshots/` un-ignore lines BEFORE the deny rules (`*.db`, results/, logs/, snapshots/*.db). git evaluates rules in order; the un-ignore must precede the parent deny to take effect.
- **Files modified:** .gitignore
- **Verification:** Functional probe with `git check-ignore -v` against four representative paths confirmed: snapshot JSON commit-able, leaderboard.db ignored, results/ ignored, snapshot stray .db ignored.
- **Committed in:** a0ca58b (Task 3 commit)

**3. [Rule 1 - Bug] Reworded requirements.txt comment to satisfy literal acceptance grep**
- **Found during:** Task 1 (requirements.txt creation)
- **Issue:** PATTERNS.md and the plan both specify the comment text "NB: NO sqlalchemy here — leaderboard uses stdlib sqlite3 (D-17)". The plan's literal acceptance check `grep -c 'sqlalchemy\|alembic' services/tournament-harness/requirements.txt` returns 0 — but the comment text itself contains the literal word "sqlalchemy", so the literal grep matches the comment line and counts 1. Plan was internally inconsistent (the comment IS the documentation of D-17, but the gate as written forbids the substring entirely).
- **Fix:** Reworded the comment to "NB: leaderboard uses stdlib sqlite3 only (D-17) — no ORM, no migration tool deps." Same intent (D-17 is documented in the file), no contradicting substrings, literal grep returns 0.
- **Files modified:** services/tournament-harness/requirements.txt
- **Verification:** `grep -c -E 'sqlalchemy|alembic' services/tournament-harness/requirements.txt` returns 0; the actual dependency list is unchanged.
- **Committed in:** 7000433 (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing critical, 1 bug)
**Impact on plan:** All three are inline corrections to make the plan's acceptance contracts internally consistent and the build path actually work. None changes the architectural intent of the plan; none expands scope. The skeleton remains structural-only as the plan output note requires.

## Issues Encountered

- `docker compose config` initially failed with `env file services/notification-service/.env not found`. The compose file references this gitignored file via `env_file:` for an unrelated service. To run the structural acceptance checks, I created an empty `.env` at `services/notification-service/.env` (gitignored — never reaches a commit) so `compose config` resolves and the profile-gating greps run. This is a pre-existing worktree-state issue, not introduced by this plan; the parent repo presumably has a real `.env` there for the operator's Telegram/Slack/SMTP creds.
- Pre-existing semgrep WARNING-severity findings on `docker-compose.unified.yml` lines 33/70/105/139/177/209 (no-new-privileges + read_only on postgres/timescaledb/redis/rabbitmq/prometheus/grafana). Out of scope per `<deviation_rules>` SCOPE BOUNDARY — these are pre-existing on services unrelated to this task. Logged for future hardening.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: docker-socket-bind-mount | docker-compose.unified.yml:~770 | tournament-harness mounts `/var/run/docker.sock` (D-02 — Docker SDK orchestration). Acknowledged in the plan's threat_model as T-03-01. Mitigations in place: (a) `profiles: [tournament]` keeps service off by default — operator must explicitly `--profile tournament up`; (b) D-05 single-image runner pattern means the orchestrator only ever launches `crypto-bot-tournament-harness:latest`, never user-supplied images. Documented inline in the compose stanza header comment block. Semgrep WARNING (CWE-250) acknowledged as known privilege-boundary intentionally accepted for the harness use case. |
| threat_flag: cors-wildcard-origin | services/tournament-harness/app/main.py:55 | CORSMiddleware uses `allow_origins=["*"]` matching project-wide pattern (ml-retraining-service, ml-prediction-service). Semgrep WARNING (CWE-942) acknowledged as informational. Service is profile-gated default-off + read-only + no auth; no real attack surface change vs the existing pattern. Future hardening: narrow to localhost dashboard + gateway origins when the dashboard's tournament view (DASH-04, Phase 7) ships. |

## User Setup Required

None — no external service configuration required at this skeleton stage. When 03-04+ wires actual tournament runs, the operator will need to: (a) set `TOURNAMENT_READER_PASSWORD` in `.env`, (b) ensure infrastructure migration creating the `tournament_reader` Postgres role has been applied (lands in 03-02 / 03-04), (c) run `docker compose -f docker-compose.unified.yml --profile tournament up tournament-harness`. None of those steps are required to merge this plan.

## Next Phase Readiness

- **03-02 (model registry refactor — services/ml-retraining-service/app/core/models/{gru,lstm,transformer,tcn}.py):** ready. The image is structural-only; 03-02 either lives in ml-retraining-service or imports through tournament-harness's PYTHONPATH path that 03-06 wires. No blockers.
- **03-03 (SQLite leaderboard schema + migrations):** ready. `services/tournament-harness/migrations/` directory is already in place from this plan's `.gitkeep` placeholder; 03-03 drops `0001_initial.sql` in without rewriting the Dockerfile.
- **03-04+ (tournament_loader, orchestrator, runner):** ready. The settings class is in place; the FastAPI surface is honest (stubs, not silently empty); the compose stanza will accept a flipped build context in 03-06 without any tournament-harness/Dockerfile rewrite at the file level (only the `build.context` value in the compose stanza changes — already noted in the plan's output block).

## Self-Check: PASSED

**Files verified:**
- FOUND: services/tournament-harness/Dockerfile
- FOUND: services/tournament-harness/requirements.txt
- FOUND: services/tournament-harness/migrations/.gitkeep
- FOUND: services/tournament-harness/app/__init__.py
- FOUND: services/tournament-harness/app/config/__init__.py
- FOUND: services/tournament-harness/app/config/settings.py
- FOUND: services/tournament-harness/app/main.py
- MODIFIED: docker-compose.unified.yml (tournament-harness stanza present, profile gating verified)
- MODIFIED: .gitignore (un-ignore overrides + deny rules verified via git check-ignore)

**Commits verified:**
- FOUND: 7000433 feat(03-01): add tournament-harness Dockerfile + requirements skeleton
- FOUND: b7f61ba feat(03-01): add tournament-harness FastAPI status app + Pydantic settings
- FOUND: a0ca58b feat(03-01): add tournament-harness compose stanza + gitignore overrides

**Plan must_haves.truths verified:**
- (1) tournament-harness service directory with Dockerfile + requirements.txt + app/ module — VERIFIED
- (2) docker-compose.unified.yml has tournament-harness stanza behind profile: tournament — VERIFIED (default 0, --profile tournament 7)
- (3) GET /health returns 200 from running tournament-harness app — VERIFIED via in-process TestClient (full container build deferred to phase end per plan output note)
- (4) Settings load TimescaleDB connection params + Docker SDK runner image config from env — VERIFIED via Python import test
- (5) .gitignore prevents committing leaderboard.db / data/results / data/snapshots/*.db — VERIFIED via git check-ignore -v on representative paths

**TOURN-07 grep gate verified:** 0 matches at this stage.

---
*Phase: 03-tournament-harness-core*
*Completed: 2026-05-08*
