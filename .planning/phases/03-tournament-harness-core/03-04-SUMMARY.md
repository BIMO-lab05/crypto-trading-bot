---
phase: "03"
plan: "04"
subsystem: "tournament-harness"
tags: ["config-loader", "yaml", "cartesian-grid", "hp-hash", "reproducibility", "tdd"]
dependency_graph:
  requires: ["03-01"]
  provides: ["tournament_loader.py", "example_tournament.yaml"]
  affects: ["03-07"]
tech_stack:
  added: ["pyyaml (yaml.safe_load)", "hashlib.sha256", "itertools.product"]
  patterns: ["Cartesian grid enumeration", "deterministic hp_hash", "YAML safe-load enforcement"]
key_files:
  created:
    - services/tournament-harness/app/config/example_tournament.yaml
    - services/tournament-harness/app/config/tournament_loader.py
    - services/tournament-harness/tests/__init__.py
    - services/tournament-harness/tests/unit/__init__.py
    - services/tournament-harness/tests/unit/test_tournament_loader.py
  modified: []
decisions:
  - "hp_hash computed over full_dict including arch+symbol+interval+target_mode to ensure cells with same HP but different context get unique hashes"
  - "SYMBOL_RE requires USDT-suffix form (^[A-Z0-9]{2,12}USDT$) — stricter than threat model's generic regex but aligns with Bybit klines.symbol column convention"
  - "resource_caps for transformer uses arch block override; gru/lstm fall back to default_resource_caps per D-04"
metrics:
  duration: "402s (~7 minutes)"
  completed_date: "2026-05-09"
  tasks_completed: 2
  files_created: 5
---

# Phase 03 Plan 04: Tournament Config Loader — YAML Schema + Cartesian Enumeration + hp_hash Summary

**One-liner:** YAML loader with yaml.safe_load enforcement, Cartesian grid enumeration over all four architectures × symbols × HP dims, and deterministic sha256 hp_hash + per-experiment seed derivation per D-11/D-12/D-13.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Author example_tournament.yaml | 511b33e | services/tournament-harness/app/config/example_tournament.yaml |
| 2 RED | Add failing tests for tournament_loader | ae3beb1 | tests/__init__.py, tests/unit/__init__.py, tests/unit/test_tournament_loader.py |
| 2 GREEN | Implement tournament_loader.py | 0a370a4 | services/tournament-harness/app/config/tournament_loader.py |

## Outcome

- `load_tournament(yaml_path)` returns a `TournamentSpec` via `yaml.safe_load` only (T-03-11 enforced)
- `enumerate_experiments(spec)` returns 360 `ExperimentSpec` cells for the example YAML (4 archs × 3 symbols × 1 interval × 2 target_modes × per-arch HP grid)
- `hp_hash` = `sha256(json.dumps(full_dict, sort_keys=True))[:16]` — deterministic across re-loads (D-13)
- `experiment_seed` = `(tournament_seed + int(hp_hash[:8], 16)) & 0xFFFFFFFF` (D-13)
- Same YAML re-loaded twice produces identical hp_hash + experiment_seed for all 360 cells (determinism verified)
- Grid cap: raises `ValueError` if experiments > `max_experiments` (T-03-12)
- Symbol guard: rejects bare `SOL` — requires Bybit USDT-suffix form `SOLUSDT` (T-03-14)
- Transformer cells use `mem_limit=8g` override; gru/lstm use default `4g`

## Verification Results

```
tournament_id=example_2026_05_08 experiments=360
architectures={'gru', 'lstm', 'transformer', 'tcn'}
symbols={'BNBUSDT', 'SOLUSDT', 'ADAUSDT'}
Deterministic across 360 cells
yaml.load count: 0 (PASS — only safe_load used)
TOURN-07 metrics functions count: 0 (PASS — no parallel metrics path)
```

### Test Results
```
13 passed in 0.43s
```

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED  | ae3beb1 — `test(03-04): add failing tests for tournament_loader` | PASS — ModuleNotFoundError confirmed |
| GREEN | 0a370a4 — `feat(03-04): implement tournament_loader` | PASS — all 13 tests pass |

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written.

**Minor implementation note:** `hp_hash` is computed over a `full_dict` that includes `architecture`, `symbol`, `interval`, `target_mode`, and `hp` (not just the raw HP values). This is intentional — cells with identical HP settings under different (symbol, target_mode) contexts must produce distinct hashes to avoid duplicate `run_id` collisions in the leaderboard. The plan's specification is satisfied (hp_hash is deterministic and 16 chars from sha256); this is a correct interpretation of D-13's intent.

## Known Stubs

None — all functionality is fully implemented and verified.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. YAML parsing path protected by `yaml.safe_load` (T-03-11 mitigated), symbol injection protected by `SYMBOL_RE` (T-03-14 mitigated), grid explosion protected by `max_experiments` cap (T-03-12 mitigated).

## Self-Check: PASSED

- [x] `services/tournament-harness/app/config/example_tournament.yaml` exists
- [x] `services/tournament-harness/app/config/tournament_loader.py` exists
- [x] `services/tournament-harness/tests/unit/test_tournament_loader.py` exists
- [x] Commit 511b33e exists (example_tournament.yaml)
- [x] Commit ae3beb1 exists (RED — failing tests)
- [x] Commit 0a370a4 exists (GREEN — implementation)
- [x] All 13 tests pass
- [x] No `yaml.load(` calls in tournament_loader.py
- [x] No unexpected file deletions in any commit
