---
type: decision
title: "ADR-026: Disposition of scripts/monitoring Autonomous Tier-2 System"
status: accepted
created: 2026-05-13
updated: 2026-07-30
renumbered_from: docs/decisions/ADR-011
tags: [decision, adr, monitoring, ops]
---

# ADR-026: Disposition of scripts/monitoring Autonomous Tier-2 System

**Status:** Accepted
**Date:** 2026-05-13
**Deciders:** Operator (solo-founder)
**Phase:** 05 (ml-cleanup-post-v0), Plan 03 (MLCL-03)
**Supersedes:** None — this is the first formal decision on `scripts/monitoring/`.

> **Renumbered ADR-011 → ADR-026 and moved `docs/decisions/` → `wiki/decisions/` on 2026-07-30.**
> The docs/decisions side-channel collided with the wiki ADR namespace (two different ADR-011s).
> Per the wiki namespace policy (decisions/_index, 2026-05-15) the wiki is the single ADR home.
> Historical references to "docs ADR-011 (monitoring disposition)" mean this document.

---

## Context

The `scripts/monitoring/` directory was introduced to provide autonomous health monitoring
for the trading bot. It implemented a two-tier design:

**Tier 1** (`tier1_monitor.py`) runs cheap, deterministic health checks every 15 minutes
via cron: service `/health` endpoint polling, Prometheus alert scraping, CoinGecko price
divergence check, and notification cadence check. It writes a JSON failure report and logs
a one-line summary. No LLM calls. No network writes. No git access.

**Tier 2** (`tier2_escalate.sh`, `tier2_mission.md`, `auto_pr_janitor.sh`) was an
autonomous escalation system that fired when tier-1 reported failures. It invoked
`claude -p "$mission" --max-turns 40` with full filesystem write access and `GH_TOKEN`
available in the subprocess environment. The claude session was expected to diagnose the
failure, write a regression test, implement a fix, run a backtest gate, and open a PR.
`auto_pr_janitor.sh` closed stale auto-generated PRs.

The tier-2 system was built but never activated — it has been parked since 2026-04-27
pending a binding disposition decision (tracked as Phase 5 MLCL-03, SC-3).

**The binding constraint:** CLAUDE.md states: "No unattended loops that can weaken tests,
mock failing pieces, or commit/push without checkpoint review." Cron is unattended. The
tier-2 escalator ran fully unattended, with the only human gate being PR review after the
code was already written, tested, and pushed. A STRIDE threat analysis identified six open
threats (T-05-03-01 through T-05-03-06), five of which were HIGH or MEDIUM severity with
no technical defense beyond human PR review. See the full threat analysis in
`.planning/phases/05-ml-cleanup-post-v0/05-03-DECISION.md`.

---

## Decision

**Chosen disposition: `keep_tier1_delete_tier2`**

Delete `tier2_escalate.sh`, `tier2_mission.md`, and `auto_pr_janitor.sh`. Retain
`tier1_monitor.py`, `run_monitor.sh` (edited to remove tier-2 calls), and all operator
helper scripts (`start_monitoring.sh`, `stop_monitoring.sh`, `monitoring_logs.sh`,
`monitoring_status.sh`).

Modify `run_monitor.sh` to replace the call to `tier2_escalate.sh` with a
`notify_operator_only()` function that:
1. Appends a structured JSONL entry to `logs/monitor_tier1_failures.jsonl`.
2. Optionally POSTs a plain-text notification to `TELEGRAM_WEBHOOK_URL` if set.

Rewrite `scripts/monitoring/README.md` to document the tier-1-only shape and include an
explicit "Blast-radius bounds" section.

A pytest gate (`tests/security/test_no_unattended_claude_p_in_ci.py`) is added to prevent
`claude -p` from silently re-entering CI workflows or monitoring scripts in the future.

---

## Consequences

**Positive:**
- All six tier-2 STRIDE threats (T-05-03-01..06) are closed by deletion.
- The project's CLAUDE.md "no unattended loops" rule is satisfied.
- Tier-1 monitoring is preserved: the operator gets a 15-minute-cadence failure signal
  and optional Telegram notification. Service outages surface within one cron tick.
- Maintenance burden is reduced — no LLM CLI version pinning, no BACKTEST_CMD wiring,
  no GitHub App dependency for the monitoring path.
- The blast radius of the remaining monitoring system is bounded and documented:
  curl reads, log appends, optional HTTP POST. No `claude`, no `gh`, no `git`.

**Negative:**
- Autonomous diagnosis and fix are no longer available from the monitoring path.
- Overnight failures require operator triage the next morning (acceptable for solo-founder
  project with no overnight operator).
- The tier-2 design (including the agentic mission prompt) is preserved only in git history.

**Regression prevention:**
- `tests/security/test_no_unattended_claude_p_in_ci.py` asserts zero `claude -p` matches
  across CI workflows, monitoring scripts, and the broad repo (excluding documentation paths).
  This test runs as part of `pytest tests/` — any re-introduction of `claude -p` in an
  executable path will fail CI.

---

## Reference

Full threat analysis (STRIDE table, two-option analysis, excluded-option note for
`wire_with_bounds`): `.planning/phases/05-ml-cleanup-post-v0/05-03-DECISION.md`

Plan that executed this ADR: `.planning/phases/05-ml-cleanup-post-v0/05-03-PLAN.md`
