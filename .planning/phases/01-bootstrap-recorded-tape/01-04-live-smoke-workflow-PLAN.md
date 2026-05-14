---
phase: 01-bootstrap-recorded-tape
plan: 04
type: execute
wave: 3
depends_on: [01-03-bootstrap-script]
files_modified:
  - .github/workflows/live-smoke.yml
autonomous: true
requirements: [INFRA-03]

must_haves:
  truths:
    - "A `live-smoke.yml` GitHub Actions workflow runs on a nightly cron AND on workflow_dispatch (manual)"
    - "The workflow does NOT trigger on push or pull_request (does NOT block the deterministic CI lane — D-16)"
    - "The workflow runs `bash bootstrap.sh` with `MARKET_DATA_SOURCE=live` exported, using BYBIT_API_KEY / BYBIT_API_SECRET from repo secrets (testnet / read-only — NOT mainnet trade-permission keys)"
    - "After bootstrap idle, the workflow sends a single curl probe to bybit-connector and asserts a non-empty `data.list`"
    - "The probe step uses `continue-on-error: true` — failure NOTIFIES (Issue / artifact upload) but does NOT mark the workflow as a hard failure for the deterministic lane"
    - "The workflow uploads service logs as artifacts on failure (per ci.yml pattern)"
    - "The workflow ends with `docker compose -f docker-compose.unified.yml down -v` cleanup"
  artifacts:
    - path: ".github/workflows/live-smoke.yml"
      provides: "Nightly + manual workflow that boots the stack against live Bybit market-data, runs a minimal probe, allowed to be flaky (D-16, INFRA-03)"
      contains: "MARKET_DATA_SOURCE: live"
  key_links:
    - from: ".github/workflows/live-smoke.yml"
      to: "bootstrap.sh"
      via: "bash bootstrap.sh"
      pattern: "bash bootstrap\\.sh"
    - from: ".github/workflows/live-smoke.yml"
      to: "secrets.BYBIT_API_KEY / BYBIT_API_SECRET"
      via: "env: BYBIT_API_KEY: ${{ secrets.BYBIT_API_KEY }}"
      pattern: "secrets\\.BYBIT_API_(KEY|SECRET)"
---

<objective>
Ship the nightly live-smoke CI lane (D-16, INFRA-03 second half). A single GitHub Actions workflow boots the stack with `MARKET_DATA_SOURCE=live`, runs a minimal probe against bybit-connector, uploads logs, and tears down. Failures are advisory (continue-on-error) so they never block the deterministic lane.

Purpose: Detects regressions in the live-API path without polluting the deterministic CI suite (which lives on the recorded tape, D-14 default).
Output: One new file `.github/workflows/live-smoke.yml`.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md
@.planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md
@.planning/phases/01-bootstrap-recorded-tape/01-03-bootstrap-script-PLAN.md

<interfaces>
<!-- Cron + workflow_dispatch header (PATTERNS analog: .github/workflows/security-scan.yml:1-22) -->
on:
  schedule:
    - cron: '0 3 * * *'      # nightly at 03:00 UTC
  workflow_dispatch:

<!-- Compose-up + health + log dump + cleanup (PATTERNS analog: .github/workflows/ci.yml:358-388) -->

<!-- Required secrets (operator must add to GitHub repo secrets BEFORE first cron run): -->
<!--   BYBIT_API_KEY     — Bybit testnet OR read-only mainnet key. Never a key with trade permissions. -->
<!--   BYBIT_API_SECRET  — matching secret. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create .github/workflows/live-smoke.yml (D-16, INFRA-03)</name>
  <files>.github/workflows/live-smoke.yml</files>
  <read_first>
    - .github/workflows/security-scan.yml (analog: cron + workflow_dispatch trigger structure, env block — lines 1-22)
    - .github/workflows/ci.yml (analog: docker compose up + health-loop + log dump + cleanup — lines 358-388)
    - bootstrap.sh (just created in plan 03 — the workflow shells out to it)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-16: same compose, MARKET_DATA_SOURCE=live, separate nightly CI workflow, allowed-to-be-flaky, does NOT block deterministic lane)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section ".github/workflows/live-smoke.yml" — patch shape; cron `0 3 * * *`, workflow_dispatch, continue-on-error on probe, NO push/PR triggers)
  </read_first>
  <action>
    Create `.github/workflows/live-smoke.yml` with the following EXACT structure:

    ```yaml
    # Live Smoke Test (Bybit mainnet/testnet REST + WS)
    # Triggers: nightly cron + manual dispatch ONLY.
    # NEVER on push/PR — must not block the deterministic CI lane (D-16).
    # Probe failures are advisory (continue-on-error) per INFRA-03 — "allowed to be flaky".

    name: Live Smoke (Bybit)

    on:
      schedule:
        - cron: '0 3 * * *'   # nightly at 03:00 UTC
      workflow_dispatch:

    jobs:
      live-smoke:
        runs-on: ubuntu-latest
        timeout-minutes: 30

        steps:
          - name: Checkout
            uses: actions/checkout@v4

          - name: Boot stack via bootstrap.sh in LIVE mode
            env:
              MARKET_DATA_SOURCE: live
              BYBIT_TESTNET: 'true'                                  # testnet keys only — never trade-permission mainnet keys
              BYBIT_API_KEY: ${{ secrets.BYBIT_API_KEY }}
              BYBIT_API_SECRET: ${{ secrets.BYBIT_API_SECRET }}
              # Trading SAFETY in CI: even with valid keys, force paper + emergency-stop.
              PAPER_TRADING_MODE: 'true'
              TRADING_MODE: PAPER
              AUTO_TRADING_ENABLED: 'false'
              ENABLE_ML_PREDICTIONS: 'false'
              ENABLE_SENTIMENT_ANALYSIS: 'false'
            run: |
              # Write the env into .env so bootstrap.sh / compose pick it up.
              cp .env.example .env
              {
                echo "MARKET_DATA_SOURCE=$MARKET_DATA_SOURCE"
                echo "BYBIT_TESTNET=$BYBIT_TESTNET"
                echo "BYBIT_API_KEY=$BYBIT_API_KEY"
                echo "BYBIT_API_SECRET=$BYBIT_API_SECRET"
                echo "PAPER_TRADING_MODE=$PAPER_TRADING_MODE"
                echo "TRADING_MODE=$TRADING_MODE"
                echo "AUTO_TRADING_ENABLED=$AUTO_TRADING_ENABLED"
                echo "ENABLE_ML_PREDICTIONS=$ENABLE_ML_PREDICTIONS"
                echo "ENABLE_SENTIMENT_ANALYSIS=$ENABLE_SENTIMENT_ANALYSIS"
              } >> .env
              bash bootstrap.sh

          - name: Probe — live ticker via bybit-connector
            id: probe
            continue-on-error: true                                  # D-16 — advisory, must NOT fail the workflow
            run: |
              set -e
              # bybit-connector should now be hitting real Bybit testnet REST.
              RESP=$(curl -fsS 'http://localhost:8001/api/v1/market/kline?category=linear&symbol=SOLUSDT&interval=5&limit=5')
              echo "$RESP" | head -c 500
              echo "$RESP" | python3 -c "import sys, json; d = json.load(sys.stdin); assert d.get('success') is True; lst = d.get('data', {}); lst = lst.get('list', lst) if isinstance(lst, dict) else lst; assert isinstance(lst, list) and len(lst) > 0, 'empty list'; print('OK live SOLUSDT klines:', len(lst))"
              # Also confirm the connector logs report mode=live (not stuck on tape)
              docker compose -f docker-compose.unified.yml logs bybit-connector | grep 'BYBIT_PRICE_SOURCE: mode=live' || (echo "ERROR: connector did not log mode=live"; exit 1)

          - name: Collect service logs
            if: always()
            run: |
              docker compose -f docker-compose.unified.yml logs > live-smoke-logs.txt 2>&1 || true

          - name: Upload service logs
            if: always()
            uses: actions/upload-artifact@v4
            with:
              name: live-smoke-logs
              path: live-smoke-logs.txt
              retention-days: 14

          - name: Cleanup
            if: always()
            run: |
              docker compose -f docker-compose.unified.yml down -v || true

          - name: Surface probe result (advisory)
            if: always()
            run: |
              if [ "${{ steps.probe.outcome }}" = "success" ]; then
                echo "::notice title=Live Smoke::PASS"
              else
                echo "::warning title=Live Smoke::FAILED — investigate logs artifact (does NOT block deterministic CI)"
              fi
    ```

    Hard rules (verify by grep):
    - `on:` block contains `schedule:` and `workflow_dispatch:` ONLY. NO `push:` or `pull_request:` triggers.
    - The probe step has `continue-on-error: true`.
    - `BYBIT_TESTNET: 'true'` is hardcoded — operators provide testnet keys only via secrets. Mainnet trade-permission keys MUST NEVER be used in CI.
    - `PAPER_TRADING_MODE: 'true'` and `TRADING_MODE: PAPER` are also hardcoded — even if the keys were mainnet, paper-mode prevents order execution.
    - `AUTO_TRADING_ENABLED: 'false'` — auto-trader is OFF in CI (extra safety belt).
    - `down -v` is in `if: always()` cleanup.
    - The workflow references `docker-compose.unified.yml` (NOT `docker-compose.yml`).
  </action>
  <verify>
    <automated>python3 -c "import yaml; w = yaml.safe_load(open('.github/workflows/live-smoke.yml')); assert 'schedule' in w['on']; assert 'workflow_dispatch' in w['on']; assert 'push' not in w['on']; assert 'pull_request' not in w['on']; print('triggers OK')" && grep -q "continue-on-error: true" .github/workflows/live-smoke.yml && grep -q "MARKET_DATA_SOURCE: live" .github/workflows/live-smoke.yml && grep -q "BYBIT_TESTNET: 'true'" .github/workflows/live-smoke.yml && grep -q "PAPER_TRADING_MODE: 'true'" .github/workflows/live-smoke.yml && grep -q "AUTO_TRADING_ENABLED: 'false'" .github/workflows/live-smoke.yml && grep -q "docker-compose.unified.yml" .github/workflows/live-smoke.yml && grep -q "secrets.BYBIT_API_KEY" .github/workflows/live-smoke.yml</automated>
  </verify>
  <done>
    `.github/workflows/live-smoke.yml` parses as valid YAML; triggers on cron + workflow_dispatch ONLY (no push/PR); the probe step is advisory (`continue-on-error: true`); environment hardcodes testnet + paper-mode + auto-trader-off; secrets pulled from `secrets.BYBIT_API_KEY` / `secrets.BYBIT_API_SECRET`; logs uploaded as artifact on every run.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner -> Bybit testnet REST | Nightly outbound HTTP via bybit-connector live branch; uses repo-stored secrets |
| repo secrets BYBIT_API_KEY / SECRET -> live-smoke.yml env | Cron-triggered injection into runner env; never logged in plain text |
| live-smoke.yml -> deterministic CI lane (ci.yml) | NONE — separate workflow, no shared state, no dependency edge |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01 | E (Elevation of privilege) | secrets.BYBIT_API_KEY scope | mitigate | Workflow hardcodes `BYBIT_TESTNET: 'true'` so even a mainnet trade-permission key would point at testnet. PAPER_TRADING_MODE + TRADING_MODE=PAPER + AUTO_TRADING_ENABLED=false means trading-engine cannot place orders even if connector reaches mainnet. Triple-belt safety. Verify gate: 3 grep checks above. |
| T-04-02 | I (Information disclosure) | secrets in workflow logs | mitigate | Secrets injected ONLY via `${{ secrets.* }}` substitution; no `echo $BYBIT_API_KEY` in any step. The bootstrap.sh writes to `.env` via redirected echo, but `.env` is never `cat`-ed back to stdout. GitHub Actions auto-redacts secret values in logs. |
| T-04-03 | D (Denial of service) | deterministic CI lane | mitigate | live-smoke.yml triggers ONLY on `schedule` and `workflow_dispatch`. Verify gate: yaml asserts `'push' not in w['on']` and `'pull_request' not in w['on']`. Probe step has `continue-on-error: true` so a flaky run cannot mark the workflow as failed and trip required-status-check on PRs (no PR trigger anyway). |
| T-04-04 | T (Tampering) | service logs artifact | accept | Logs uploaded via `actions/upload-artifact@v4` with 14-day retention; visible to repo collaborators; could contain operational noise but no secrets (auto-redacted). |
</threat_model>

<verification>
- YAML parses (`yaml.safe_load`).
- All 7 grep gates in Task 1 pass.
- The workflow file exists at the conventional path GitHub expects (`.github/workflows/live-smoke.yml`).
</verification>

<success_criteria>
- INFRA-03 (live-smoke half): A separate nightly path is documented and explicitly out-of-scope for the deterministic suite (allowed to be flaky, runs nightly only).
- D-16: Same compose, `MARKET_DATA_SOURCE=live`, separate nightly CI workflow; failure notifies but does NOT block the deterministic CI lane.
- The workflow is wired but does not run until the operator adds the two repo secrets (`BYBIT_API_KEY`, `BYBIT_API_SECRET` for testnet) — the missing-secret state is benign (workflow runs and the probe step fails advisory; deterministic lane unaffected).
</success_criteria>

<user_setup>
- service: GitHub repo secrets
  why: "live-smoke workflow needs Bybit testnet credentials to drive the live REST path"
  env_vars:
    - name: BYBIT_API_KEY
      source: "GitHub repo Settings -> Secrets and variables -> Actions -> New repository secret. Use a Bybit TESTNET key (https://testnet.bybit.com/app/user/api-management)."
    - name: BYBIT_API_SECRET
      source: "Same dashboard. Read-only or no-trade-permission permissions only — workflow hardcodes paper mode but defense in depth."
  dashboard_config:
    - task: "Confirm the testnet API key has NO 'Trade' permission box checked"
      location: "Bybit testnet -> API Management -> Permissions"
</user_setup>

<output>
After completion, create `.planning/phases/01-bootstrap-recorded-tape/01-04-SUMMARY.md` noting the cron schedule, the workflow URL once secrets are added (e.g. `gh workflow list`), and a manual dispatch dry-run if the operator triggered one.
</output>
