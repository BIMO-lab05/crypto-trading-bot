# Phase 2: Integration Test Suite & RUNBOOK - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-07
**Phase:** 02-integration-test-suite-runbook
**Areas discussed:** Test runner & isolation, Fresh-clone proof boundary, Iteration harness UX

---

## Test runner & isolation

### Q1 — How should pytest bring the stack up for the integration suite?

| Option | Description | Selected |
|--------|-------------|----------|
| Invoke bootstrap.sh | pytest session-fixture shells out to `./bootstrap.sh` — same script the operator runs. Matches "fresh-clone" promise; no parallel bring-up path to drift from. | ✓ |
| testcontainers-python | Use `testcontainers.compose.DockerCompose` pointed at `docker-compose.unified.yml`. Pythonic fixture API, but bypasses `bootstrap.sh` — risks drift between test path and operator path. | |
| Raw subprocess docker compose | pytest fixture shells `docker compose -f docker-compose.unified.yml up -d` directly. No new dep, full control — but also bypasses `bootstrap.sh`. | |

**User's choice:** Invoke bootstrap.sh
**Notes:** Recommended pick. Locks D-01.

### Q2 — Where does pytest run?

| Option | Description | Selected |
|--------|-------------|----------|
| On host machine | pytest runs on the operator/CI host outside compose. Matches what the operator does on a fresh clone; no docker-in-docker complexity. | ✓ |
| Inside dedicated test container in compose | Add a `test-runner` service to `docker-compose.unified.yml`. Cleaner isolation but adds a service that exists only for tests + DinD or socket-mount. | |
| Inside api-gateway container | docker exec into api-gateway. Reuses existing container but conflates app runtime with test runtime; api-gateway image would need pytest+testcontainers deps. | |

**User's choice:** On host machine
**Notes:** Locks D-02.

### Q3 — Stack lifecycle across the pytest run

| Option | Description | Selected |
|--------|-------------|----------|
| Session-scoped, one shared stack | Boot once at session start, tear down at session end. Boot is slow (~2 min); per-test isolation via DB TRUNCATE fixtures + tape replay cursor reset. | ✓ |
| Module-scoped | New stack per pytest test module. More isolation but ~2 min × N modules — suite balloons past 10 min. | |
| Per-test | Boot/teardown around every test. Honest but unworkable (>>30 min suite); test ergonomics destroyed. | |

**User's choice:** Session-scoped
**Notes:** Locks D-03.

### Q4 — How to keep tape replay deterministic across tests in a shared stack?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-test cursor reset via bybit-connector admin endpoint | Add `POST /admin/tape/reset` to `bybit-connector` (gated to tape mode). pytest fixture calls it before each test. Stack stays up; data clock rewinds. | ✓ |
| Accept tape advances; tests assert on relative deltas | Don't reset; tests written against "next 5 candles from current cursor". Less plumbing but tests become order-sensitive and fragile. | |
| Separate tape file per test | Each test points the connector at its own JSONL fixture. Strongest isolation but heavy fixture authoring + tape repo size grows. | |

**User's choice:** Per-test cursor reset
**Notes:** Locks D-04. Implies a new admin endpoint on `bybit-connector`.

---

## Fresh-clone proof boundary

### Q5 — Where does the integration suite get its "fresh clone" from?

| Option | Description | Selected |
|--------|-------------|----------|
| Local working tree via `git clone file://` | `git clone file://$(pwd) /tmp/cb-test-<sha>`. Catches uncommitted-file deps without needing network. Fast, deterministic, runs offline. | ✓ |
| `git clone` from origin/main | Network clone of the GitHub remote. Closest to "true fresh" for a new operator but flaky in CI without internet, and ignores uncommitted local changes the operator would push first. | |
| rsync working tree to tmp dir | Skip git, just copy the tree. Fastest, but doesn't exercise git resolution; uncommitted+gitignored files leak in (defeats fresh-clone semantics). | |

**User's choice:** Local working tree via `git clone file://`
**Notes:** Locks D-05.

### Q6 — What's in `.env` when the suite starts `bootstrap.sh`?

| Option | Description | Selected |
|--------|-------------|----------|
| Empty `.env` | Matches Phase 1 D-17 promise: tape mode bypasses BYBIT key validation. Phase 2 must prove this works end-to-end. If it breaks, that's a Phase 1 regression to surface. | ✓ |
| Provisioned with stub test creds | Creates `.env` from `.env.example` with placeholder keys. Sidesteps the empty-creds path — makes bootstrap green more easily but hides regressions in the documented-clean path. | |
| Both — parametrized | Run the suite twice (empty + stub). Strongest coverage but doubles runtime; the stub case is mostly redundant if empty works. | |

**User's choice:** Empty `.env`
**Notes:** Locks D-06.

### Q7 — Where does the suite run?

| Option | Description | Selected |
|--------|-------------|----------|
| Local + CI, same pytest invocation | `pytest tests/integration` works on operator machine and on GitHub Actions. Single source of truth; operator can reproduce every CI failure locally. | ✓ |
| CI-only | Suite assumes a clean Linux runner. Operator can't run locally without setup gymnastics — violates Phase 2 goal of operator-debuggable iteration. | |
| Local-only, CI smoke is separate | Heavy suite local; CI runs a thin subset. Risks CI/local drift over time. | |

**User's choice:** Local + CI, same pytest invocation
**Notes:** Locks D-07.

### Q8 — What happens to the `/tmp` clone after a test run?

| Option | Description | Selected |
|--------|-------------|----------|
| Delete on success, keep on failure | Matches Phase 1 D-13 "fail loud, leave artifacts". Operator can `cd /tmp/cb-test-<sha>` post-mortem with logs intact. Auto-clean keeps disk in check on green runs. | ✓ |
| Always delete | Clean state always. Faster disk reclaim but kills postmortem workflow; logs gone. | |
| Never delete | Tmp pile-up. Operator manages. Bad default. | |

**User's choice:** Delete on success, keep on failure
**Notes:** Locks D-08.

---

## Iteration harness UX

### Q9 — How should the iteration harness present a fix for review?

| Option | Description | Selected |
|--------|-------------|----------|
| Terminal `git diff` + inline Y/N | Harness prints `git diff --staged`, asks `Apply? [y/N]` at the prompt. Simplest; works in any shell; no Claude/IDE dep. | ✓ |
| Diff to file + separate `/iter approve|reject` command | Writes patch to `.planning/iter/pending.patch`, operator runs `/iter approve` or edits before applying. Persistent record but two-step UX. | |
| Pause inside pytest with `--iter` flag | Pytest plugin pauses on failure, presents diff, resumes on approve. Tight loop but conflates pytest with mutation. | |

**User's choice:** Terminal `git diff` + inline Y/N
**Notes:** Locks D-09.

### Q10 — What invokes the harness?

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone `scripts/iter-fix.sh` | Plain shell/python entrypoint at repo root. Doesn't conflate with pytest; can be wrapped by an outer driver. | ✓ |
| Pytest plugin / `pytest --iter` | Lives inside pytest invocation. Tight integration but couples test runner to mutation logic. | |
| Slash command in this Claude session only | Custom `/iter` Claude command. Convenient when working through Claude Code, useless in CI or for the operator using bare shell. | |

**User's choice:** Standalone `scripts/iter-fix.sh`
**Notes:** Locks D-10.

### Q11 — Approval granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Per-fix | Operator approves every individual diff. Catches drift before it compounds; explicit anti-Goodhart safeguard. | ✓ |
| Per-iteration round (multi-file batch) | Harness collects all changes for one test-fix attempt, presents as a unit. Faster but a single bad change can hide inside the batch. | |
| Auto-apply when green, review when red | Honor-system: silently keep fixes that pass tests. Violates the project rule against unattended loops. | |

**User's choice:** Per-fix
**Notes:** Locks D-11.

### Q12 — Where does "no silent mock / no skip / no threshold lowering" enforcement live?

| Option | Description | Selected |
|--------|-------------|----------|
| Inside the harness script + CI guard | Script greps the proposed diff for `unittest.mock`, `pytest.skip`, `xfail`, threshold edits in test files. Hard-refuses to apply matching diffs. CI repeats the check on PR. | ✓ |
| Pre-commit hook only | Runs at `git commit` time. Catches the offence later than the harness. | |
| CI only | Caught at PR. No protection during local iteration. | |
| Trust + manual review | Pure honor system. Loses the "iteration harness REFUSES to mock" INFRA-04 promise. | |

**User's choice:** Inside the harness script + CI guard
**Notes:** Locks D-12.

---

## Claude's Discretion

User selected "Ready for context" without deep-diving the following gray areas. CONTEXT.md `<decisions>` § "Claude's Discretion" captures default stances (CD-01 .. CD-05). Operator may override during plan-phase.

- CD-01: Notification verification (mock vs real test bot) — defaulted to dedicated Telegram test bot in private channel; record-only locally, live in CI.
- CD-02: INFRA-06 pre-existing bug triage — defaulted to fix all 3 with 1-day-cost cap per bug; over-cap → defer with written decision.
- CD-03: RUNBOOK.md scope — defaulted to failure-triage-first (Symptom → Diagnose → Action → Verification per section).
- CD-04: Paper-trade <60s assertion mechanics — defaulted to admin force-signal endpoint + DB-row timing.
- CD-05: ML-models-loaded variant — defaulted to nightly + manual; default suite stays ML-off (matches Phase 1 D-10).

## Deferred Ideas

- Tape grow / refresh policy beyond v1 (Phase 1 D-06 left at "manual on demand"; revisit Phase 5 if 7-day window too tight).
- Parallel test-run isolation across concurrent devs (port-prefix env var if collisions surface).
- Notification, INFRA-06 triage, RUNBOOK, paper-trade <60s, ML-on variant deep dives — see CD-01..CD-05 for default stances.
