---
phase: 02-integration-test-suite-runbook
plan: 10
subsystem: infra
tags: [makefile, build, wsl2, buildkit, ergonomics]
dependency_graph:
  requires: []
  provides: [Makefile, build-no-buildkit-target]
  affects: [RUNBOOK.md § BuildKit hang (Plan 02-07 forward-reference)]
tech_stack:
  added: [GNU Make]
  patterns: [phony-target, variable-expansion]
key_files:
  created: [Makefile]
  modified: []
decisions:
  - "CD-02 (Makefile half): minimal build-no-buildkit target as ergonomic shortcut for WSL2 BuildKit hang workaround"
  - "Discriminator 4 default applied: minimal scope (1 target only); bootstrap/health-check/test-integration/iter-fix targets deferred"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-07T21:23:12Z"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Phase 02 Plan 10: Minimal Makefile (build-no-buildkit) Summary

**One-liner:** Minimal Makefile at repo root with a single `build-no-buildkit` target wrapping `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build $(SVC)` as the ergonomic WSL2 BuildKit hang workaround.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write Makefile at repo root with build-no-buildkit target | 72bd617 | Makefile (created) |

## Files Created

| File | Purpose |
|------|---------|
| `Makefile` | Ergonomic shortcut for WSL2 + Docker Desktop BuildKit hang workaround (INFRA-06 / CD-02) |

## Decisions Addressed

- **CD-02 (Makefile half):** `make build-no-buildkit SVC=<name>` wraps the `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build <name>` workaround. The RUNBOOK.md forward-reference in Plan 02-07 resolves to this target. CD-02's RUNBOOK documentation half belongs to Plan 02-07.
- **Discriminator 4 default (minimal):** Scope held to one target. The `bootstrap`, `health-check`, `test-integration`, and `iter-fix` convenience targets shown in PATTERNS.md are illustrative for a non-default path; those have direct script entry points already and are not added here.

## Acceptance Criteria Verification

All criteria passed:

```
[x] [ -f Makefile ]
[x] .PHONY: build-no-buildkit declared (line 5)
[x] build-no-buildkit: target defined (line 13)
[x] Recipe tab-indented; uses docker-compose.unified.yml (line 14)
[x] make -n build-no-buildkit SVC=sentiment-analysis → DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build sentiment-analysis
[x] No reference to non-canonical docker-compose.yml
[x] make -n build-no-buildkit (empty SVC) exits 0, emits command prefix with trailing space (builds all)
[x] wc -l Makefile = 14 (< 25 line limit)
```

## Threat Model Items Closed

| Threat ID | Category | Disposition | Notes |
|-----------|----------|-------------|-------|
| T-02-10-01 | T (command injection via SVC) | accept | Make's `$(SVC)` is local-developer scope; operator who injects `;`/`` ` ``/`$()` attacks themselves. CI does not invoke this target (Plan 02-09 uses `bash bootstrap.sh` directly). |
| T-02-10-02 | I (secrets in build context via logs) | accept | Same risk as direct `docker compose build` invocation. `.env` gitignore + `BYBIT_API_KEY=` defaults are the control; out of scope for this plan. |

## Carry-Forward Notes

- **RUNBOOK.md § BuildKit hang (Plan 02-07)** references `make build-no-buildkit` as the ergonomic shortcut — that forward-reference now resolves.
- Future plans may add convenience targets (`make bootstrap`, `make health-check`, `make test-integration`, `make iter-fix`) once usage patterns settle; scope intentionally narrow here per CD-02.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

```
FOUND: Makefile
FOUND: commit 72bd617
```
