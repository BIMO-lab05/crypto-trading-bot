---
phase: 08-pre-live-preflight
plan: 04
type: execute
wave: 3
depends_on:
  - 08-02
  - 08-03
files_modified:
  - .github/workflows/preflight-live-readiness.yml
autonomous: true
requirements:
  - PREFLIGHT-03
tags:
  - preflight
  - ci
  - github-actions

must_haves:
  truths:
    - "The workflow file exists at `.github/workflows/preflight-live-readiness.yml` and parses as valid GitHub Actions YAML (actionlint exit 0)."
    - "Triggers on `pull_request` to main/develop branches."
    - "Job `unit-tests` always runs: lint + `pytest services/trading-engine/tests/test_preflight_*.py` + `pytest tests/integration/test_preflight_grep_gates.py`."
    - "Job `gate` runs ONLY when the PR carries the label `live: requested`; executes `python3 scripts/preflight_live.py --dry-run --target=HEAD --json` and fails the check on non-zero exit."
    - "`gate` job has `needs: unit-tests` — a unit-test failure short-circuits the gate even on labelled PRs."
    - "`pull_request` events for unlabelled PRs still run `unit-tests` (cheap regression net) — only `gate` is label-gated."
  artifacts:
    - path: ".github/workflows/preflight-live-readiness.yml"
      provides: "PR gate enforcing preflight on `live: requested` PRs; unit-test regression net on all PRs"
      contains: "live: requested"
  key_links:
    - from: ".github/workflows/preflight-live-readiness.yml"
      to: "scripts/preflight_live.py"
      via: "python3 invocation with --dry-run --target=HEAD"
      pattern: "preflight_live\\.py.*--dry-run"
    - from: ".github/workflows/preflight-live-readiness.yml"
      to: "tests/integration/test_preflight_grep_gates.py"
      via: "pytest invocation"
      pattern: "test_preflight_grep_gates"
    - from: ".github/workflows/preflight-live-readiness.yml"
      to: "services/trading-engine/tests/test_preflight_*.py"
      via: "pytest invocation"
      pattern: "test_preflight_"
---

<objective>
Add the CI workflow that runs the preflight unit-test bundle on every PR and, when a PR is labelled `live: requested`, additionally executes the `preflight_live.py --dry-run --target=HEAD` gate that blocks the merge if any of the 6 checks fail.

Purpose: Per CLAUDE.md "every PR runs unit tests; the gate enforces only on labelled PRs" — minimum CI cost for unlabelled PRs, hard block for labelled ones. Plus this is the surface that hosts the two grep-gate tests from 08-03 — so silent removal of the LIVE_PREFLIGHT_REJECTED literal or the `from app.preflight` import is caught at PR review time, before merge.

Output:
- `.github/workflows/preflight-live-readiness.yml` (single file, ~50 lines)
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/08-pre-live-preflight/08-CONTEXT.md
@.planning/phases/08-pre-live-preflight/08-PATTERNS.md
@.planning/phases/08-pre-live-preflight/08-01-SUMMARY.md
@.planning/phases/08-pre-live-preflight/08-02-SUMMARY.md
@.planning/phases/08-pre-live-preflight/08-03-SUMMARY.md

<!-- Existing workflow analogs -->
@.github/workflows/tournament-harness.yml
@.github/workflows/integration.yml

<!-- Targets invoked by this workflow -->
@scripts/preflight_live.py
@tests/integration/test_preflight_grep_gates.py
@services/trading-engine/tests/test_preflight_checks.py
@services/trading-engine/tests/test_preflight_route.py
@services/trading-engine/tests/test_preflight_lifespan.py

<interfaces>
<!-- Pinned workflow structure from 08-PATTERNS.md lines 384-432 -->

Trigger:
  pull_request: branches [main, develop]

Job 1: unit-tests (always runs)
  - actions/checkout@v4
  - actions/setup-python@v5 with python-version "3.12"
  - pip install requirements
  - pytest services/trading-engine/tests/test_preflight_*.py
  - pytest tests/integration/test_preflight_grep_gates.py

Job 2: gate (label-gated)
  needs: unit-tests
  if: contains(github.event.pull_request.labels.*.name, 'live: requested')
  - actions/checkout@v4 with fetch-depth: 0
  - actions/setup-python@v5
  - python3 scripts/preflight_live.py --dry-run --target=HEAD --json
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Author the workflow YAML</name>
  <files>.github/workflows/preflight-live-readiness.yml</files>
  <read_first>
    - .github/workflows/tournament-harness.yml (lines 1-62 — two-job structure analog: grep-gate + unit-tests; trigger pattern; concurrency block; action versions pinned)
    - .github/workflows/integration.yml (lines 1-7 — `on: pull_request: branches:` trigger pattern)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 377-434 — copy-ready workflow + the "No internal analog" note for the PR-label conditional; falls back to GitHub Actions stdlib `contains(github.event.pull_request.labels.*.name, 'live: requested')`)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 88-95 — CI workflow decision)
  </read_first>
  <action>
    1. Create `.github/workflows/preflight-live-readiness.yml` with the structure pinned in 08-PATTERNS.md lines 384-432:

       ```yaml
       name: Preflight Live-Readiness Gate

       on:
         pull_request:
           branches: [main, develop]

       concurrency:
         group: preflight-${{ github.ref }}
         cancel-in-progress: true

       jobs:
         unit-tests:
           name: Preflight unit tests (always)
           runs-on: ubuntu-latest
           steps:
             - uses: actions/checkout@v4
             - uses: actions/setup-python@v5
               with:
                 python-version: "3.12"
             - name: Install trading-engine deps
               run: |
                 pip install --upgrade pip
                 pip install -r services/trading-engine/requirements.txt
             - name: Preflight unit tests
               working-directory: services/trading-engine
               run: pytest tests/test_preflight_checks.py tests/test_preflight_route.py tests/test_preflight_lifespan.py -v
             - name: Grep gates
               run: pytest tests/integration/test_preflight_grep_gates.py -v

         gate:
           name: Live-readiness gate (labelled PRs only)
           needs: unit-tests
           if: contains(github.event.pull_request.labels.*.name, 'live: requested')
           runs-on: ubuntu-latest
           steps:
             - uses: actions/checkout@v4
               with:
                 fetch-depth: 0  # required for `git show <ref>:.env.example` to resolve
             - uses: actions/setup-python@v5
               with:
                 python-version: "3.12"
             - name: Install trading-engine deps
               run: |
                 pip install --upgrade pip
                 pip install -r services/trading-engine/requirements.txt
             - name: Run preflight gate
               run: python3 scripts/preflight_live.py --dry-run --target=HEAD --json
       ```

       Pin both action versions (`actions/checkout@v4`, `actions/setup-python@v5`) — supply-chain mitigation per threat model T-08-04-01.

    2. The `gate` job depends on `unit-tests` (via `needs:`); if unit-tests fails, the gate never runs even on a labelled PR.

    3. The `if: contains(...)` expression is GitHub Actions stdlib — no internal repo precedent (per 08-PATTERNS.md "No Analog Found"). The literal label string is `live: requested` (lowercase, single space, colon). Document this in a workflow-file comment near the `if:` line so the reviewer doesn't need to consult CONTEXT.md.

    4. Add a comment at the top of the file:
       ```yaml
       # Phase 8 PREFLIGHT-03 — Pre-LIVE preflight gate.
       # Every PR runs unit tests + grep gates (cheap regression net).
       # PRs labelled `live: requested` additionally run the preflight CLI in
       # --dry-run mode against HEAD; gate fails if any of the 6 checks FAIL.
       # See .planning/phases/08-pre-live-preflight/08-CONTEXT.md decision lines 88-95.
       ```
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; (actionlint .github/workflows/preflight-live-readiness.yml 2&gt;/dev/null || (python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/preflight-live-readiness.yml')); assert 'jobs' in d; assert 'unit-tests' in d['jobs']; assert 'gate' in d['jobs']; assert d['jobs']['gate'].get('needs') == 'unit-tests'; assert \"live: requested\" in d['jobs']['gate']['if']; print('YAML schema OK')"))</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "name: Preflight Live-Readiness Gate" .github/workflows/preflight-live-readiness.yml` returns 1.
    - Source assertion: `grep -c "actions/checkout@v4" .github/workflows/preflight-live-readiness.yml` returns ≥1 (pinned version per supply-chain mitigation).
    - Source assertion: `grep -c "actions/setup-python@v5" .github/workflows/preflight-live-readiness.yml` returns ≥1.
    - Source assertion: `grep -c "live: requested" .github/workflows/preflight-live-readiness.yml` returns ≥1.
    - Source assertion: `grep -c "needs: unit-tests" .github/workflows/preflight-live-readiness.yml` returns 1.
    - Source assertion: `grep -c "test_preflight_grep_gates" .github/workflows/preflight-live-readiness.yml` returns ≥1 (the grep-gate test is wired into CI).
    - Source assertion: `grep -c "preflight_live.py --dry-run --target=HEAD" .github/workflows/preflight-live-readiness.yml` returns ≥1.
    - Source assertion: `grep -c "fetch-depth: 0" .github/workflows/preflight-live-readiness.yml` returns ≥1 (required for `git show HEAD:.env.example` to work in CI shallow clones).
    - YAML validation: `actionlint .github/workflows/preflight-live-readiness.yml` exits 0 if actionlint is installed; ELSE the fallback python yaml.safe_load + structural assertions exit 0. (One MUST pass — the `<verify>` block runs both.)
    - Manual CLI assertion: `python3 scripts/preflight_live.py --dry-run --target=HEAD --json` (run locally) exits 0 or 1 (not 2 — meaning the dry-run path works), with valid JSON output. Record outcome in SUMMARY.
  </acceptance_criteria>
  <done>Workflow file exists, passes actionlint OR yaml.safe_load + structural checks, pins action versions, label-gated `gate` job invokes `preflight_live.py --dry-run --target=HEAD`, unit-tests job invokes grep-gate tests + 3 preflight test files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner → repo (`actions/checkout`) | upstream action; pinned to major version `@v4` to avoid supply-chain drift |
| PR labels → CI gate decision | label set by repo maintainers/operators; gate enforces on `live: requested` only |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-04-01 | T (Tampering) / supply-chain | `actions/checkout`, `actions/setup-python` upstream actions | mitigate | Pin to major versions (`@v4`, `@v5`) — matches existing pattern in tournament-harness.yml. Major-version pins receive security patches but block silent breaking changes. Stricter SHA pinning is a v1.x candidate; not required by ASVS L1 for an unauthenticated read-only CI workflow. |
| T-08-04-02 | E (Elevation) | label-bypass — a PR author with label-set permission could remove `live: requested` to skip the gate | accept | This is the intended contract: only PRs explicitly opting into a LIVE deploy carry the label. Unlabelled PRs are not heading to production; the gate is voluntary participation. The grep-gate job still runs on unlabelled PRs (in `unit-tests`), so silent removal of `LIVE_PREFLIGHT_REJECTED` is still caught regardless of label. |
| T-08-04-03 | T (Tampering) | adversary pushes a PR that mutates `preflight-live-readiness.yml` itself (e.g. removes the `gate` job) | mitigate | GitHub repo's branch-protection rules require CODEOWNERS review on `.github/workflows/`. Out-of-scope for Phase 8 to configure (operator concern); flag in SUMMARY as a follow-up if not already enforced. |
| T-08-04-04 | I (Info disclosure) | workflow logs `preflight_live.py --json` output | accept | Output contains only schema_version=1 JSON with PASS/FAIL/UNKNOWN per check + detail strings. Same disclosure level as the unauthenticated HTTP endpoint (D-09). No secrets in workflow logs. |
| T-08-04-05 | D (DoS) | concurrent PRs each consume an Actions runner minute | mitigate | `concurrency: group: preflight-${{ github.ref }} cancel-in-progress: true` — newer pushes to the same PR cancel in-flight runs. Matches tournament-harness.yml pattern. |

(No HIGH-severity threats.)
</threat_model>

<verification>
- `actionlint .github/workflows/preflight-live-readiness.yml` exits 0 (or the python yaml fallback in `<verify>` exits 0).
- `grep -c "live: requested" .github/workflows/preflight-live-readiness.yml` returns ≥1.
- `grep -c "needs: unit-tests" .github/workflows/preflight-live-readiness.yml` returns 1.
- `grep -c "fetch-depth: 0" .github/workflows/preflight-live-readiness.yml` returns ≥1.
- Manual local-CLI smoke: `python3 scripts/preflight_live.py --dry-run --target=HEAD --json` exits 0 or 1 (not 2) with valid JSON; record exit code + sample line in SUMMARY.
- Post-merge runtime smoke (record in SUMMARY when first PR runs): the workflow appears under PR Checks tab in GitHub UI; `unit-tests` runs on the PR, `gate` runs only after adding the `live: requested` label.
- **Note:** CIRESTORE-01/02 (Phase 12) is on the operator path — until OP-04 (GH Actions billing) is resolved, the workflow may not execute on push. Phase 8's deliverable is the file existence + local-CLI smoke; first green CI run is part of Phase 12 evidence (CIRESTORE-02). Document this dependency in SUMMARY.
</verification>

<success_criteria>
- Workflow file at exactly `.github/workflows/preflight-live-readiness.yml`.
- YAML parses (actionlint OR yaml.safe_load structural validation).
- Triggers on `pull_request` to main/develop.
- Both jobs present: `unit-tests` always runs, `gate` runs only on labelled PRs.
- `gate` has `needs: unit-tests` (test-failure short-circuits the gate).
- Action versions pinned (`@v4`, `@v5`).
- Local-CLI manual smoke: `python3 scripts/preflight_live.py --dry-run --target=HEAD --json` works (exit 0 or 1, valid JSON, not exit 2).
- Notes Phase 12 dependency in SUMMARY (first green run waits on OP-04).
</success_criteria>

<output>
After completion, create `.planning/phases/08-pre-live-preflight/08-04-SUMMARY.md` capturing:
- The workflow file's final form (size, line count).
- actionlint output (or python yaml fallback output).
- Local-CLI smoke result: `python3 scripts/preflight_live.py --dry-run --target=HEAD --json` exit code + first-line snippet.
- Note: first green CI run is contingent on Phase 12 OP-04 (billing). The workflow is committed and ready; CI invocation evidence belongs to CIRESTORE-02 (Phase 12), not Phase 8.
- Optional follow-up: CODEOWNERS rule for `.github/workflows/` (out of scope for Phase 8 — flag in v1.2 backlog if not already enforced).
</output>
