# Phase 12: CI Recovery — Context

**Gathered:** 2026-05-18
**Status:** Ready for planning
**Source:** ROADMAP.md success criteria + REQUIREMENTS.md (no discuss-phase run; derived inline given small phase scope)

<domain>
## Phase Boundary

Phase 12 ships the `billing-failure-detector.yml` workflow + its unit test (code work, unblocked). Phase 12 also holds the evidence rows for two operator wall-clock carry-ins (CIRESTORE-01 + CIRESTORE-02) that close only after operator resolves **OP-04** (GitHub Actions billing). The detector ships regardless of OP-04 state.

**In scope (code):**
- `.github/workflows/billing-failure-detector.yml` — cron every 6h, runs `gh run list --status failure --limit 5`, filters for `billing` substring, posts to Telegram + opens GitHub Issue with `ops: billing` label.
- Mocked unit test asserting the detector's behavior on a fixture `gh run list` payload containing `billing`.
- `.planning/evidence/CIRESTORE-01/` + `.planning/evidence/CIRESTORE-02/` directory README scaffolds (placeholders that the operator fills upon OP-04 close).

**Out of scope (operator wall-clock, human_needed):**
- Actually resolving OP-04 billing (operator action).
- Capturing the 3 green CI run URLs (CIRESTORE-02 — happens after OP-04).
- Committing the billing-page screenshot (CIRESTORE-01).

## Locked Decisions

1. **Telegram path reuses existing `services/notification-service/app/telegram_notifier.py`** — workflow should NOT re-implement Telegram HTTP. Workflow invokes the notification-service REST endpoint (or shells curl against the bot's chat ID via env-injected secret) — choose the minimum-coupling option that doesn't require running the full container in CI.
2. **Cron schedule fixed at `'0 */6 * * *'`** (every 6 hours, on the hour).
3. **GitHub Issue label fixed at `ops: billing`** — used by the existing alerting taxonomy.
4. **Detection substring: literal `billing`** in failure reason (per ROADMAP success criterion 3). Case-insensitive match.
5. **No shell-interpolated `${{ github.event.* }}` user-controllable fields** in workflow run steps — follows the security pattern documented in `preflight-live-readiness.yml` header comments (no command-injection surface).
6. **Unit test mocks `gh run list` output** (subprocess.run or fixture file) — does NOT execute the real `gh` CLI in CI.
7. **CIRESTORE-01/02 evidence directories are scaffolds only** — README files documenting the schema the operator fills + a `.gitkeep` for the directory to exist in git.
8. **No `bash scripts/closure/*` harness required** for CIRESTORE — pure evidence-row carry-in, not a re-runnable script. Differs from Phase 11.1 LIVECLOSE-0X pattern by design.

## Canonical Refs

- `.planning/REQUIREMENTS.md` — CIRESTORE-01, CIRESTORE-02, CIRESTORE-03 definitions
- `.planning/ROADMAP.md` — Phase 12 section (goal + 3 success criteria)
- `.github/workflows/preflight-live-readiness.yml` — security pattern reference (no event-payload interpolation; `concurrency.group`; `if: contains()`)
- `services/notification-service/app/telegram_notifier.py` — existing Telegram notifier surface
- `.planning/evidence/OP-04/` — destination for CIRESTORE-01 billing screenshot
- `.planning/evidence/CIRESTORE-02/` — destination for 3 green CI run URLs

## Cross-phase relationships

- **CIRESTORE-01 ↔ LIVECLOSE-02** (Phase 11.1): both close on the same OP-04 resolution event. Kept as separate REQs per v1.1-init decision (logged in STATE.md).
- **Phase 12 unblocks no other phase** — CI Recovery is terminal in v1.1.

## Threat surface

| Risk | Mitigation |
|---|---|
| Workflow command injection via GH event payload | Do not interpolate user-controllable fields into shell steps; follow `preflight-live-readiness.yml` pattern (boolean `if:` only, no `bash -c "${{ ... }}"`). |
| False-positive billing alert (any failure containing word "billing") | Substring filter is intentional per ROADMAP; tightening regex is OUT OF SCOPE — fix in v1.2 if alert fatigue materializes. |
| Telegram secret leak in workflow logs | Use `${{ secrets.TELEGRAM_BOT_TOKEN }}` via env-injection only; never echo to stdout; mask via `add-mask` if substring appears in output. |
| Detector misses billing failure during cron skew | Acceptable — 6h window matches the operator-monitored cadence; tighter cron is OUT OF SCOPE. |

## Planning notes for `gsd-planner`

- 2 plans likely (1 detector workflow + 1 evidence-scaffold), OR 1 combined plan if dependency analysis favors it.
- Detector workflow is the only meaningful code surface; evidence scaffolds are 5-line READMEs.
- Verify the workflow file lints clean via `actionlint` if available locally; otherwise rely on the unit-test path to catch behavior bugs.
- No new Python service or DB migration. Pure CI plumbing.
</domain>
