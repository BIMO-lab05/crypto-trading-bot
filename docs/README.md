# docs/ — Living Documentation

Reorganized 2026-07-30. Everything here is a **living** guide or reference. Point-in-time reports (session summaries, phase completions, coverage pushes) go to `docs/archive/` — never to this level. Architecture decisions are ADRs in `wiki/decisions/` (single ADR home).

## Map

| Folder | What lives here |
|---|---|
| `architecture/` | `SYSTEM_OVERVIEW.md` (mirror of wiki Architecture-Overview), `DATA_PROFILE_KLINES.md` |
| `setup/` | Bybit API keys, Telegram notifications |
| `development/` | Dev environment `SETUP.md`, `TESTING.md`, `E2E_TESTING_GUIDE.md` |
| `testing/` | Test DB setup + quick ref, testing commands, test-quality checklist & remediation guide |
| `operations/` | Nominal-ops `RUNBOOK.md`, monitoring & alerting guides, disaster recovery, Docker reference, signal diagnostics, HashiCorp Vault quick ref, weekly reports |
| `runbooks/` | One-shot / evidence-loop runbooks (`forward-paper-test.md`, `LIVECLOSE-05.md`) |
| `deploy/` | Deploy options index, Oracle free-tier quickstart + headless deploy, `KUBERNETES_RUNBOOK.md` |
| `security/` | Secrets management, Vault integration, password rotation, hardening, best practices, pre-deploy checklist |
| `reference/` | Performance-metric definitions, portfolio optimization module |
| `ml/` | **Removed** — emptied by the 2026-08-03 archive batch and the directory no longer exists. `ML_DATA_COLLECTION_GUIDE.md` lives in `archive/2026-08-03/docs/ml/`. ML status of record: CLAUDE.md §3 + [[wiki/concepts/ML-Status]] |
| `strategy/` | Research artifacts only (`research-2026-04-29/`, `research-2026-05-21/`: scripts + result JSON). Narrative docs incl. `RESEARCH_PLAN_2026-04-29.md` moved to `archive/2026-08-03/docs/strategy/`; strategy authority is CLAUDE.md §2 + ADR-013. **Current edge results are not here** — the kill-test batteries live in `backtesting/edge_lab/` with verdicts in `.planning/evidence/killtests/` |
| `archive/` | **Historical** reports Nov 2025 – May 2026, by theme — excluded from the Graphify graph. See `archive/README.md` |

## Failure triage

Symptom-indexed failure triage lives at repo root: `/RUNBOOK.md` (kept at root deliberately — first thing an operator greps for).

## Rules

1. New doc? Ask: is it a guide someone follows repeatedly (→ here), a decision (→ `wiki/decisions/` ADR), knowledge/context (→ `wiki/`), or a one-time report (→ `docs/archive/` with a date in the filename).
2. Date-stamp point-in-time claims ("as of 2026-07-30 …") so staleness is detectable.
3. When a doc supersedes another, move the loser to `archive/superseded/` and note the successor in its first line.
