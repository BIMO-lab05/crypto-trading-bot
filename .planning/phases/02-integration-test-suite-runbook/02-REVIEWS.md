---
phase: 2
reviewers: [glm-4.7]
reviewed_at: 2026-05-07T15:37:57Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md, 02-03-PLAN.md, 02-04-PLAN.md, 02-05-PLAN.md, 02-06-PLAN.md, 02-07-PLAN.md, 02-08-PLAN.md, 02-09-PLAN.md, 02-10-PLAN.md]
prompt_size_bytes: 293031
notes: |
  Cross-AI review run on 2026-05-07.
  Available CLIs on this host: claude (skipped — running inside Claude Code), ollama.
  Ollama-mounted models: kimi-k2.5:cloud (paywalled — `this model requires a subscription`), bjoernb/claude-opus-4-5:latest (routes to GLM-4.7 cloud).
  Only one external review delivered. No multi-reviewer consensus this round.
  To strengthen this in future: install gemini, codex, or qwen CLIs; or upgrade Ollama Cloud subscription to unlock kimi-k2.5.
---

# Cross-AI Plan Review — Phase 2: Integration Test Suite & RUNBOOK

## GLM-4.7 Review (via Ollama / `bjoernb/claude-opus-4-5:latest`)

# Cross-AI Plan Review: Phase 2 - Integration Test Suite & RUNBOOK

## Summary

The implementation plans for Phase 2 are **high quality**, demonstrating a deep understanding of the project context, constraints, and the specific "fresh-clone" and "anti-mock" requirements. The wave-based dependency structure (Wave 1: Primitives, Wave 2: Fixtures, Wave 3: Tests, Wave 4: CI/Bugs) is logical and minimizes circular dependencies. The plans successfully translate the abstract decisions (D-01 through D-12) into concrete, executable tasks with robust verification steps. The attention to detail regarding Docker Compose environment variable precedence (Plan 02-05) and the structural enforcement of the anti-mock guard (Plan 02-06) are particular strengths.

## Strengths

*   **Robust Security Boundaries:** Plans 02-01 and 02-02 correctly implement mode-gating (`MARKET_DATA_SOURCE=tape`, `TRADING_MODE != LIVE`) for new admin endpoints, preventing accidental execution in production environments.
*   **Structural Anti-Pattern Enforcement:** Plan 02-06 implements the "no silent mocks/skips" rule (D-12) as a shell script gate, making it a structural failure point rather than a code review guideline. This is effectively carried forward into CI (Plan 02-09).
*   **Docker Compose Environment Handling:** Plan 02-05 correctly identifies and solves the "Blocker #1" issue where `env_file` settings would otherwise override host environment variables in CI. The explicit `${VAR:-}` passthrough in the `environment` block is the correct solution.
*   **Deterministic Test Strategy:** The use of a "fresh clone" (Plan 02-03) and recorded tape (Plan 02-01) ensures the integration suite is deterministic and does not rely on flaky external APIs or live market data.
*   **Comprehensive Bug Triage:** Plan 02-08 addresses the INFRA-06 bugs with a balanced approach—fixing the code issues (stale ML, confidence=0) with regression tests while correctly documenting the environmental issue (WSL2 BuildKit) in the RUNBOOK.

## Concerns

*   **Complexity of `notification_received` Fixture (Plan 02-03):** The fixture implements two distinct verification paths (file tailing vs. API polling) based on an environment variable. While necessary for CD-01, this dual-path logic increases the risk of flakiness. If the "record" mode file write is buffered or delayed, the polling loop might fail despite the notification being sent.
*   **Reliance on Operator Configuration for CI Security (Plan 02-09):** The anti-mock guard in CI is gated to `pull_request` events. The plan correctly identifies that direct pushes to `main` bypass this guard. While the plan documents the need for GitHub Branch Protection, this remains a "human-in-the-loop" risk—if the operator forgets to configure it, the structural enforcement is void.
*   **ML Model Reload Reliability (Plan 02-08):** The `ModelLoader` relies on `st_mtime` to detect changes. While this works for most "write in place" or "copy" operations, some training pipelines might use atomic renames (`mv`) where mtime behavior can vary depending on the filesystem (though usually preserved or updated). If the file is replaced via a hard link or specific `mv` flags that preserve metadata, the reload might not trigger.
*   **Port Mapping Bug Fix (Plan 02-03):** The plan fixes a known port-mapping inversion in `conftest.py`. While the fix is correct, it highlights a fragility in the existing test setup where service URLs were hardcoded incorrectly. The fix is good, but the existence of the bug suggests a need for better validation of service discovery in the future.

## Suggestions

*   **Plan 02-03 (Notification Fixture):** In the `notification_received` fixture for "record" mode, consider adding a small `fsync` or explicit flush logic in the `telegram_notifier.py` write path (Plan 02-05) to ensure the data is physically written to disk before the test fixture attempts to read it, reducing the likelihood of a race condition in the polling loop.
*   **Plan 02-08 (ML Reload):** In the `ModelLoader`, consider adding a fallback check for `st_ino` (inode number) in addition to `st_mtime`. If the inode changes but the path remains the same (e.g., atomic swap), it indicates a file replacement even if mtime is somehow preserved or identical. This adds robustness for different training script implementations.
*   **Plan 02-09 (CI):** To mitigate the branch protection risk, consider adding a "pre-flight" check in the `integration.yml` workflow that runs on `push` to `main` (if allowed) or simply logs a warning if the workflow detects it is running on a direct push, reminding the operator that the anti-mock guard was skipped. (Note: This is hard to enforce purely via code without repo permissions, so the current documentation approach is likely the best available).

## Risk Assessment

**Overall Risk Level: MEDIUM**

**Justification:**
The plans are technically sound and well-architected. The "Medium" risk rating stems primarily from the complexity introduced by the dual-mode notification testing and the reliance on operator discipline for CI security policies. The code changes themselves (admin endpoints, fixtures, shell scripts) are low-risk. The highest risk area is the integration test suite's reliability (Plan 02-03/02-04), as a flaky test suite undermines the "fresh-clone" value proposition. However, the use of deterministic tape data and session-scoped fixtures significantly mitigates this risk. The security risks are well-managed via mode-gating and the documented dependency on Branch Protection.

---

## Consensus Summary

> **Caveat:** Only one external reviewer (GLM-4.7) was reachable during this run. There is no cross-reviewer consensus to triangulate. Treat the verdict below as a single perspective, not a chorus.

### Top concerns to fold back into planning

1. **Plan 02-03 — Notification fixture race risk (MEDIUM).** The `notification_received` fixture polls a log file that `telegram_notifier.py` writes asynchronously; without explicit `flush()` / `fsync()` after each record-mode write the test can poll a stale-cache view of the file. Add the flush in Plan 02-05's writer or extend the fixture to retry with a backoff that explicitly tolerates kernel page-cache lag.
2. **Plan 02-09 — Anti-mock guard scope (MEDIUM).** Direct pushes to `main` bypass the PR-time guard. The plan acknowledges this as an operator-policy item. Cheapest structural mitigation: also run the guard on `push` events with a non-blocking warning log, and document branch protection as a Phase 2 acceptance gate.
3. **Plan 02-08 — `st_mtime` reload trigger (LOW–MEDIUM).** mtime alone misses some atomic-replace patterns (`mv -T`, hardlink swap with preserved mtime). Cheap fix: combine mtime with `st_ino`/`st_size` check; reload when any of (mtime, inode, size) changes.

### Strengths called out by GLM-4.7 worth preserving

- Wave 1→4 dependency structure is sound; do not flatten waves under schedule pressure.
- Mode-gating on `/admin/tape/reset` and `/admin/force-signal` (Plans 02-01 and 02-02) is the right primary defense — keep the explicit refusal tests in CI.
- Anti-mock enforcement as a structural shell gate (Plan 02-06) is the correct level — not a code-review note.
- `${VAR:-}` env passthrough in compose (Plan 02-05) is the right way to keep CI overrides from being clobbered by `env_file`.

### Divergent views

None — single reviewer.

### Items NOT raised by the reviewer (reviewer blind spots / future runs to probe)

These were not flagged by GLM-4.7; flagging them as worth a second-reviewer pass:

- **Plan 02-04 — host-side `pytest -m ml_on` invocation when ML model files require docker volumes.** The default suite is ML-off; the ML-on variant assumes model files are reachable by the host pytest process. Phase 2 host pytest may not see the docker-mounted model directory.
- **Plan 02-05 — `getUpdates` long-polling vs single-shot.** The Telegram `getUpdates` endpoint advances its `update_id` cursor on each successful read. If two parallel CI runs hit the same test bot, they race for the latest message. No reviewer flagged this; consider per-run dedicated bots or message-id-tagged assertions.
- **Plan 02-06 — `iter-fix.sh` interaction with pre-commit hooks.** `git commit` inside the harness may invoke project pre-commit hooks that themselves run pytest; this can produce a recursive loop if a hook fires the same suite the harness is iterating over.

---

## How to incorporate

To fold these reviews back into planning, run:

```
/gsd-plan-phase 2 --reviews
```

The `--reviews` flag tells the planner to read this file and produce a revision PLAN updating the affected plans (notably 02-03, 02-05, 02-08, 02-09).
