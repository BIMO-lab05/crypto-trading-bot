# docs/archive/ — Historical Reports

Created 2026-07-30 (vault restructure, branch `docs/vault-restructure`). Point-in-time session summaries, test/coverage reports, phase completions, and superseded docs from **Nov 2025 – May 2026**. Nothing here is maintained; nothing here should be cited as current.

**Excluded from the Graphify knowledge graph** via `.graphifyignore`.
**Load-bearing facts were distilled first** into `wiki/sources/Archive-Distillation-2026-07-30.md` — check there before digging.

⚠️ **Trust warning:** most pre-2026-07-28 performance/P&L claims in these files are measurement-corrupted (broken paper accounting + testnet-polluted candles — see ADR-018/ADR-021). Many "PRODUCTION READY ✅" claims were later contradicted. Read as history, not evidence.

**Account size (2026-08-25, ADR-029):** all pre-2026-08-25 account-size statements in this archive describe the $100 era; the declared paper account is now $10,000 per `shared/account.py`.

## Layout

| Folder | Contents |
|---|---|
| `sessions-2025/` | Session summaries & point-in-time status reports (repo root + docs/, Nov 2025 – May 2026) |
| `testing-2025/` | Test sweeps, coverage reports, testing master plans |
| `strategy-2025/` | Phase 2/3 strategy research, grid-trading saga, SOL-heavy allocation, stat-arb, ensemble deployment, trade analyses |
| `infrastructure-2025/` | Infra plans/status, perf load-tests, DevOps reports, helm/monitoring completion reports |
| `audits/` | Dec-2025 security audit, accessibility audit 2026-05-02, Vault rollout checklist |
| `services/<name>/` | Per-service agent-session artifacts (COVERAGE_*, *_COMPLETE, *_SUMMARY, *_REPORT) |
| `frontend-2025/`, `scripts-2025/`, `backtesting-2025/`, `reports-2025-11/` | Same genre, by origin |
| `superseded/` | Docs replaced by better ones: `CLAUDE.original.md`, `progress.original.md`, `GETTING_STARTED.md`, `SYSTEM_ARCHITECTURE.md`, `SERVICE_CONTRACTS.md`, `TRADING_ENGINE_CAPABILITIES.md`, `TRADING_PAIRS.md`, wiki-only graph report |
| `artifacts/` | Root .txt summaries + debug screenshots |

## Policy

- Append-only. Add new dated folders as eras close; never edit contents.
- Before archiving anything new: distill still-true facts into the wiki, fix inbound links, note the move in `wiki/log.md`.
