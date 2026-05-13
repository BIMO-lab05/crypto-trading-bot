# 05-03 Decision: Disposition of scripts/monitoring/* Autonomous Tier-2 System

**Decision ID:** MLCL-03
**Date:** 2026-05-13
**Status:** Accepted (operator pre-confirmed `keep_tier1_delete_tier2`)
**Decided by:** Operator (pre-confirmation on plan execution prompt)

---

## Context

### MLCL-03 Background

Phase 5 requirement MLCL-03 ("SC-3") specifies: "`scripts/monitoring/*` is either removed or
wired with documented blast-radius bounds — no `claude -p` PR-opening from CI without human
review — and the decision is committed." This requirement was parked at the end of Phase 4
(2026-04-27) pending a binding written decision. That decision is made here.

### Current System State

The `scripts/monitoring/` directory implements a two-tier autonomous monitoring loop:

| File | Role | Auto-trigger? | Uses `claude -p`? |
|------|------|---------------|--------------------|
| `run_monitor.sh` | Cron entry (every 15 min) | Yes | No (delegates) |
| `tier1_monitor.py` | Health checks (curl + Prometheus + price divergence) | Yes (via cron) | No |
| `tier2_escalate.sh` | Tier-2 escalator — diagnose + fix + open PR | Yes (on tier-1 fail) | **YES — line 102** |
| `tier2_mission.md` | Mission prompt fed to claude subprocess | Referenced by tier2_escalate | N/A |
| `auto_pr_janitor.sh` | Closes stale auto-monitor PRs | Yes (cron) | No (uses `gh` CLI) |
| `start_monitoring.sh` | Operator helper — start monitoring | Manual | No |
| `stop_monitoring.sh` | Operator helper — stop monitoring | Manual | No |
| `monitoring_logs.sh` | Operator helper — tail logs | Manual | No |
| `monitoring_status.sh` | Operator helper — check status | Manual | No |

**The critical facts for this decision:**
- `tier2_escalate.sh` line 102 invokes `"$CLAUDE_BIN" -p "$mission" --max-turns 40`
- The subprocess inherits full repo write access and the `GH_TOKEN` environment variable
- Cron fires the chain every 15 minutes unattended, including overnight
- The tier-2 system has been **parked (never activated)** since 2026-04-27

### CLAUDE.md Load-Bearing Rule

CLAUDE.md states: "No unattended loops that can weaken tests, mock failing pieces, or
commit/push without checkpoint review." Cron is unattended. Even with the tier-2 guards
(single-flight flock, DAILY_BUDGET=8, MAX_OPEN_AUTO_PRS=1, BACKTEST_CMD gate), the loop
violates this rule because:

1. No human is in the loop between tier-1 failure detection and PR creation.
2. The `claude` subprocess has full filesystem write access — any file in the repo can
   be modified before the PR is opened.
3. The backtest gate checks Sharpe ratio but does NOT verify test correctness, mock
   integrity, or whether tests were silently weakened to pass.

This project is solo-founder with no overnight operator. The autonomous-fix dream is fictional
for the current operational context.

---

## STRIDE Threat Enumeration of Current Tier-2 System (Pre-Disposition Baseline)

The following threats are enumerated against the current system BEFORE any disposition is
applied. All six are active threats while `tier2_escalate.sh` exists and is callable from cron.

| Threat ID | STRIDE Category | Component at Risk | Description | Current Mitigation | Residual Risk |
|-----------|-----------------|-------------------|-------------|-------------------|---------------|
| T-05-03-01 | **Spoofing** | `$FAILURE_JSON` forwarded to `claude -p` prompt | `tier1_monitor.py` sources data from CoinGecko (public API), Prometheus alerts (which can include attacker-influenced metric labels), and Docker log lines. If any of these sources contain prompt-injection payloads, the content crosses the trust boundary into the claude subprocess and can redirect its behavior. | None — content flows directly from HTTP response → JSON → mission prompt env var | HIGH: prompt injection is possible given the data flow |
| T-05-03-02 | **Tampering** | Filesystem — entire repo root | The `claude -p` subprocess is spawned with `REPO_ROOT` exported and has the operator's filesystem permissions. It can read, write, or delete any file in the repo including test files, configuration, and CI workflows. | None — no sandbox, no chroot, no write-allowlist | HIGH: any file reachable by the cron user is reachable by claude |
| T-05-03-03 | **Repudiation** | Audit trail | Activity logs go to `logs/monitor_tier2.log` (plain text). Claude's writes within the session are not signed. There is no way to prove after the fact which file changes came from the claude session vs. a human commit. | None | MEDIUM: accepted for solo-founder project; no regulatory requirement |
| T-05-03-04 | **Information disclosure** | `GH_TOKEN` | The cron environment inherits `GH_TOKEN` (GitHub Personal Access Token or App token). This env var is available to the claude subprocess. A sufficiently persuasive prompt (injected or adversarially crafted) could coax claude into exfiltrating the token via a network call or embedding it in a log. | None — token available in subprocess env | HIGH: token has repo write scope |
| T-05-03-05 | **Denial of service** | Cron / GitHub API | Uncontrolled tier-2 firing could exhaust GitHub API rate limits, create dozens of draft PRs, or fill logs. | DAILY_BUDGET=8 cap, MAX_OPEN_AUTO_PRS=1 cap, single-flight flock | LOW: adequately mitigated in current code |
| T-05-03-06 | **Elevation of Privilege** | CI pipeline | Auto-created PRs trigger CI workflows. CI workflows have access to additional repository secrets (e.g., `CODECOV_TOKEN`, deploy keys). A maliciously crafted PR (via prompt injection or hallucinated fix) could exfiltrate these secrets through CI log output or side channels. | No auto-merge; PR requires human review | MEDIUM: human review is a gate but the PR runs CI before review |

**Summary:** 5 of 6 threats (T-01, T-02, T-04, T-05, T-06) are HIGH or MEDIUM with no
technical defense beyond the human review gate on PR merge. T-05-03-05 (DoS) is adequately
mitigated. T-05-03-03 (Repudiation) is accepted as a solo-founder project constraint.

---

## Options Analysis

### Option 1: `delete_all`

**What specifically changes:**
- `git rm -r scripts/monitoring/` — all files in the directory are deleted and removed from
  version history tracking
- No cron entry to remove from system crontab (the cron line was never committed to the repo;
  it exists only in the operator's crontab, which must be manually removed regardless)
- No monitoring of any kind remains at the cron level

**Which threats are closed vs. which remain:**
- T-05-03-01 through T-05-03-06: ALL CLOSED by deletion. No tier-2 file, no claude invocation,
  no GH_TOKEN exposure, no auto-PR pipeline.
- No residual threats from the monitoring system.

**Operator ergonomics impact:**
- Negative: operator must manually check service health, or wire Prometheus alertmanager, or
  use a separate uptime-monitoring tool. There is no cheap automated health signal.
- No `logs/monitor_tier1.log` written. No failure notification.
- Monitoring can be re-introduced from scratch with a clean design if needed.

**Reversibility:**
- Fully reversible via git history. `git checkout <sha> -- scripts/monitoring/` restores all
  files. The agentic tier-2 design is preserved in git history for reference.

---

### Option 2: `keep_tier1_delete_tier2` (CHOSEN)

**What specifically changes:**
- DELETE: `tier2_escalate.sh`, `tier2_mission.md`, `auto_pr_janitor.sh`
- RETAIN: `tier1_monitor.py`, `run_monitor.sh`, `start_monitoring.sh`, `stop_monitoring.sh`,
  `monitoring_logs.sh`, `monitoring_status.sh`
- EDIT `run_monitor.sh`: remove call to `tier2_escalate.sh` (line 21) and `auto_pr_janitor.sh`
  (line 26); replace with `notify_operator_only()` function that writes a structured JSONL
  entry to `logs/monitor_tier1_failures.jsonl` and optionally POSTs to a Telegram webhook
  if `TELEGRAM_WEBHOOK_URL` is set
- REWRITE `README.md`: tier-1-only shape, explicit "Blast-radius bounds" section

**Which threats are closed vs. which remain:**
- T-05-03-01 (Spoofing/prompt-injection): CLOSED — no claude subprocess, no prompt
- T-05-03-02 (Tampering/filesystem write): CLOSED — tier-1 and notify function have no `git`
  write, no `gh` invocation; only appends to log files
- T-05-03-03 (Repudiation): ACCEPTED — tier-1 logs to `logs/monitor_tier1.log`;
  `logs/monitor_tier1_failures.jsonl` provides structured failure record
- T-05-03-04 (Information disclosure/GH_TOKEN): CLOSED — no subprocess that inherits env;
  `notify_operator_only()` uses only `TELEGRAM_WEBHOOK_URL` (operator-controlled)
- T-05-03-05 (DoS): CLOSED — no GitHub API calls, no PR creation
- T-05-03-06 (Privilege escalation/CI pipeline): CLOSED — no auto-PR, no CI trigger

**Operator ergonomics impact:**
- Positive: tier-1 health checks (service health, Prometheus alerts, price divergence,
  notification cadence) continue running every 15 minutes. Operator gets structured failure
  log and optional Telegram notification. Failure is surfaced within 15 minutes, not hours.
- Negative: operator must diagnose and fix manually. No autonomous PR creation. Solo-founder
  project with no overnight operator — this latency penalty is minimal in practice.

**Reversibility:**
- `tier2_escalate.sh` and `tier2_mission.md` preserved in git history. Re-introduction
  requires explicit decision + new plan (the Task 3 grep gate would fail, providing an
  intentional friction point).

---

## Excluded Option Note: `wire_with_bounds`

During plan revision, a third option was surfaced: gate `tier2_escalate.sh` behind an
`ALLOW_TIER2=true` environment variable, document blast-radius bounds in the README, and
retain the full tier-2 system as an opt-in feature. This option was **dropped during plan
revision** for a specific technical reason: adding only a runtime guard (an `if [ "${ALLOW_TIER2:-false}" != "true" ]; then exit 0; fi` check) does NOT remove the `claude -p`
invocation at `scripts/monitoring/tier2_escalate.sh` line 102. Task 2 of this plan includes
a grep gate (`grep -rEn 'claude\s+-p' scripts/monitoring/ .github/workflows/`) that must
return zero matches for the plan to pass its acceptance criteria. Under `wire_with_bounds`,
the grep gate would deterministically fail because the literal invocation remains in the
file. Removing the literal `claude -p` invocation (while keeping the file's surrounding
logic) would require a substantial rewrite that redesigns the tier-2 system — work that is
outside this plan's scope. Therefore only the two options that fully close the grep gate
(`delete_all` and `keep_tier1_delete_tier2`) are viable within this plan's scope.
Future contributors who want to re-introduce a bounded tier-2 system should start from
a new plan with a fresh design and an explicit ADR review.

---

## Decision: keep_tier1_delete_tier2

The chosen disposition is **`keep_tier1_delete_tier2`**.

---

## Rationale

The `keep_tier1_delete_tier2` disposition closes all six STRIDE threats (T-05-03-01 through
T-05-03-06) that arise from the `claude -p` invocation, GH_TOKEN exposure, and auto-PR
pipeline, while preserving the operationally-valuable tier-1 health checks that run via cron
every 15 minutes. The tier-1 system (curl health checks, Prometheus alert scraping, price
divergence check, notification cadence check) has no `claude` invocation, no `gh` invocation,
and no `git` write — its blast radius is bounded to local log writes and optional HTTP POSTs
to a Telegram webhook. This aligns directly with CLAUDE.md's load-bearing rule: "No unattended
loops that can weaken tests, mock failing pieces, or commit/push without checkpoint review."
The tier-2 escalator was the unattended loop; the tier-1 health monitor is not — it is
read-only against external services and append-only against local log files. Deleting the
tier-2 layer is also consistent with the project's Phase 4 pattern ("PR is the gate, not the
auto-promotion") where human review is the decision point. For a solo-founder project with no
overnight operator, the autonomous-fix latency advantage is fictional: the operator reviews
the failure notification the next morning either way. The `delete_all` option was rejected
because it throws away genuinely useful operational signal (15-minute health checks) for no
security benefit — the same threat closure is achieved by removing only the tier-2 files.

---

## Implementation Notes

Tasks 2 and 3 will perform the following operations:

**Task 2 — Execute disposition + write ADR-011:**

Files to delete (via `git rm`):
- `scripts/monitoring/tier2_escalate.sh` — the file containing `claude -p` at line 102
- `scripts/monitoring/tier2_mission.md` — the mission prompt fed to the claude subprocess
- `scripts/monitoring/auto_pr_janitor.sh` — the stale-PR janitor (uses `gh` CLI; tier-2 component)

Files to edit:
- `scripts/monitoring/run_monitor.sh` — remove call to `tier2_escalate.sh` (line 21) and
  `auto_pr_janitor.sh` (line 26); add `notify_operator_only()` function that writes
  structured JSONL to `logs/monitor_tier1_failures.jsonl` and optionally POSTs to
  `TELEGRAM_WEBHOOK_URL` if set
- `scripts/monitoring/README.md` — full rewrite to document tier-1-only shape, include
  explicit "Blast-radius bounds" section (curl + sqlite read + log append only; no `claude`,
  no `gh`, no `git` write)

Files to create:
- `docs/decisions/ADR-011-monitoring-disposition.md` — standard ADR codifying the choice

State to update:
- `.planning/STATE.md` — update Blockers/Concerns line referencing `scripts/monitoring/*`
  to: "scripts/monitoring/ tier-2 deleted per ADR-011 (Phase 5 MLCL-03); tier-1 retained
  as cheap health monitor"

**Task 3 — Pytest grep gate:**

File to create:
- `tests/security/__init__.py` — package marker
- `tests/security/test_no_unattended_claude_p_in_ci.py` — 4-test grep gate enforcing that
  `claude -p` cannot appear in CI workflows, monitoring scripts, or any non-allowlisted
  executable path in the repo

The grep gate uses three regex patterns: shell form `claude\s+-p\b`, Python list-arg form
`"claude"\s*,\s*"-p"`, and subprocess invocation form. Allowlisted paths (documentation):
`.planning/`, `docs/`, `wiki/`, `.git/`, `node_modules/`, `_archive_lstm/`, `__pycache__/`.
The test file self-excludes from its own grep output.
