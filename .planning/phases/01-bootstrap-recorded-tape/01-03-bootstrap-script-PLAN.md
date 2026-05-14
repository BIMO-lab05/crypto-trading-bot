---
phase: 01-bootstrap-recorded-tape
plan: 03
type: execute
wave: 2
depends_on: [01-01-tape-fixtures-capture, 01-02-bybit-connector-tape-mode]
files_modified:
  - bootstrap.sh
  - docker-compose.unified.yml
  - .env.example
autonomous: false
requirements: [INFRA-02, INFRA-03]

must_haves:
  truths:
    - "An operator can run `bash bootstrap.sh` against an empty `.env` and the script provisions `.env` from `.env.example` without manual editing"
    - "bootstrap.sh exits 0 reproducibly across two consecutive runs in a fresh tmp clone"
    - "After bootstrap.sh exit 0, all 15 services pass `GET /health` (verified by reusing health_check.sh)"
    - "After bootstrap.sh exit 0, EMERGENCY_STOP is touched at repo root (auto-trader armed but holding at STEP-0)"
    - "bootstrap.sh defaults DOCKER_BUILDKIT=0 on Linux/WSL2 (CLAUDE.md gotcha) before `docker compose up`"
    - "bootstrap.sh references `docker-compose.unified.yml` explicitly (NOT `docker-compose.yml` — the latter is incomplete; CLAUDE.md gotcha)"
    - "bootstrap.sh contains NO call to `git clean -fdx` (would delete real .env keys; CLAUDE.md hard rule)"
    - "bootstrap.sh uses `cp -n` (no-clobber) when provisioning .env so an existing operator-edited .env is preserved"
    - "On failure, bootstrap.sh exits non-zero, leaves the stack up, and prints last 50 log lines per failed service (D-13 fail-loud-leave-stack-up; no auto-retry)"
    - "D-09: idle bar at bootstrap exit = all 15 services /health=200 within timeout (no paper-trade round-trip asserted; Phase 2 owns that)"
    - "D-10: flag state at bootstrap exit = PAPER_TRADING_MODE=true, TRADING_MODE=PAPER, AUTO_TRADING_ENABLED=true (operator override per CLAUDE.md), ENABLE_ML_PREDICTIONS=false, ENABLE_SENTIMENT_ANALYSIS=false"
    - "D-11: bootstrap.sh touches EMERGENCY_STOP at repo root by default — auto-trader armed but loop holds at STEP-0 until operator removes the file"
    - "D-12: health probe = reuse existing health_check.sh pattern (curl /health per service port with retry/backoff, ~120s timeout); no new probe stack"
    - "D-14 + D-17 (consumer side): bootstrap defaults MARKET_DATA_SOURCE=tape and runs with empty BYBIT_API_KEY / BYBIT_API_SECRET (auth bypass in tape mode is honored end-to-end)"
    - "D-15 (consumer side): bootstrap relies on bybit-connector branching behind MARKET_DATA_SOURCE; market-data-service / downstream services receive the same HTTP/WS contract on port 8001 in either mode"
  artifacts:
    - path: "bootstrap.sh"
      provides: "Operator entrypoint: provisions .env, brings up stack against tape, health-probes, leaves running"
      contains: "docker-compose.unified.yml"
    - path: "docker-compose.unified.yml"
      provides: "Bybit-connector block extended with MARKET_DATA_SOURCE env + tape fixtures bind-mount"
      contains: "MARKET_DATA_SOURCE"
    - path: ".env.example"
      provides: "Template with MARKET_DATA_SOURCE=tape and LIVE_TRADING_ACK keys present"
      contains: "MARKET_DATA_SOURCE=tape"
  key_links:
    - from: "bootstrap.sh"
      to: ".env"
      via: "cp -n .env.example .env (no-clobber)"
      pattern: "cp -n.*\\.env\\.example"
    - from: "bootstrap.sh"
      to: "EMERGENCY_STOP"
      via: "touch \"$REPO_ROOT/EMERGENCY_STOP\""
      pattern: "touch.*EMERGENCY_STOP"
    - from: "bootstrap.sh"
      to: "health_check.sh"
      via: "bash \"$SCRIPT_DIR/health_check.sh\" or curl loop reusing the same port table"
      pattern: "health_check\\.sh|/health"
    - from: "docker-compose.unified.yml (bybit-connector)"
      to: "tests/fixtures/tape/"
      via: "volumes: - ./tests/fixtures/tape:/app/tests/fixtures/tape:ro"
      pattern: "tests/fixtures/tape:/app/tests/fixtures/tape:ro"
---

<objective>
Ship the operator entrypoint (`bootstrap.sh`), wire the bybit-connector compose block to mount tape fixtures + read `MARKET_DATA_SOURCE`, and ensure `.env.example` has the two new keys (`MARKET_DATA_SOURCE=tape`, `LIVE_TRADING_ACK=`). After this plan: a fresh `git clone` of the repo into a tmp directory + `bash bootstrap.sh` brings up all 15 services healthy against tape fixtures, EMERGENCY_STOP touched, no live API call required, no manual editing required.

Purpose: Closes INFRA-02 (template-based .env + compose-up + healthy idle) and the `MARKET_DATA_SOURCE=tape` half of INFRA-03 (default deterministic path).
Output: `bootstrap.sh` (NEW), modified `docker-compose.unified.yml` bybit-connector block, modified `.env.example` (additive only).
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
@.planning/phases/01-bootstrap-recorded-tape/01-01-tape-fixtures-capture-PLAN.md
@.planning/phases/01-bootstrap-recorded-tape/01-02-bybit-connector-tape-mode-PLAN.md

<interfaces>
<!-- Service port table (PATTERNS bootstrap.sh / health_check.sh:17-29) -->
<!-- bootstrap.sh either reuses health_check.sh OR replicates this table verbatim. -->
declare -A SERVICES=(
    ["api-gateway"]=8000
    ["bybit-connector"]=8001
    ["market-data"]=8002
    ["portfolio"]=8003
    ["technical-analysis"]=8004
    ["trading-engine"]=8005
    ["notification"]=8006
    ["ml-prediction"]=8007
    ["sentiment"]=8008
    ["risk-metrics"]=8009
)
<!-- Plus 5 infra services (postgres, timescaledb, redis, rabbitmq, frontend) — total 15 -->

<!-- Required .env keys at bootstrap exit (CONTEXT.md D-10, D-14, CLAUDE.md "Trading-mode flags"): -->
BYBIT_TESTNET=false
PAPER_TRADING_MODE=true
TRADING_MODE=PAPER
AUTO_TRADING_ENABLED=true
ENABLE_ML_PREDICTIONS=false
ENABLE_SENTIMENT_ANALYSIS=false
MARKET_DATA_SOURCE=tape
LIVE_TRADING_ACK=                   # empty — required only in LIVE; bootstrap leaves blank
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Append MARKET_DATA_SOURCE=tape and LIVE_TRADING_ACK to .env.example (D-14, CLAUDE.md trading-mode flags, landmine §1)</name>
  <files>.env.example</files>
  <read_first>
    - .env.example (read first; per landmine §1 do NOT regenerate; only add missing keys)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-14: env var name `MARKET_DATA_SOURCE=tape|live`, default `tape`)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (landmine §1 — verify template baseline, only edit if a key is missing)
    - crypto-trading-bot/CLAUDE.md (Project rules → Trading-mode flags — `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` required in LIVE)
  </read_first>
  <action>
    Read `.env.example` first.

    For each of these two keys, run `grep -q '^<KEY>=' .env.example`:
      - `MARKET_DATA_SOURCE`
      - `LIVE_TRADING_ACK`

    If `MARKET_DATA_SOURCE` is NOT present, append at end of file:
      ```
      # Market data source: 'tape' (default — replays JSONL fixtures from tests/fixtures/tape/)
      # or 'live' (hits real Bybit REST/WS — requires BYBIT_API_KEY + BYBIT_API_SECRET).
      MARKET_DATA_SOURCE=tape
      ```

    If `LIVE_TRADING_ACK` is NOT present, append at end of file:
      ```
      # Required only when TRADING_MODE=LIVE — set to literal string 'I_UNDERSTAND_REAL_MONEY'.
      # Trading-engine refuses to boot in LIVE without this. Leave EMPTY for paper trading.
      LIVE_TRADING_ACK=
      ```

    DO NOT modify any existing line — additive only. DO NOT add real API keys, real secrets, or any value that would commit a credential. The `.env.example` file is committed.

    Verify each key now exists with `grep -q '^MARKET_DATA_SOURCE=tape' .env.example` and `grep -q '^LIVE_TRADING_ACK=' .env.example`.
  </action>
  <verify>
    <automated>grep -q '^MARKET_DATA_SOURCE=tape' .env.example && grep -q '^LIVE_TRADING_ACK=' .env.example && ! grep -E '^BYBIT_API_KEY=[^\s$]+' .env.example | grep -vE '^BYBIT_API_KEY=$|^BYBIT_API_KEY=your_'</automated>
  </verify>
  <done>
    `.env.example` has both new keys present; existing keys are unchanged; no real API key value was added.
  </done>
</task>

<task type="auto">
  <name>Task 2: Extend bybit-connector block in docker-compose.unified.yml (D-14, D-15, D-17)</name>
  <files>docker-compose.unified.yml</files>
  <read_first>
    - docker-compose.unified.yml (lines 342-368 — existing bybit-connector block; lines 282-287 — existing EMERGENCY_STOP RW bind-mount pattern at api-gateway)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-14 default tape; D-15 tape-mode replay inside bybit-connector; D-17 empty creds OK in tape)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section "docker-compose.unified.yml" — patch shape; CLAUDE.md gotcha — this file is canonical, NOT docker-compose.yml)
  </read_first>
  <action>
    Edit `docker-compose.unified.yml` — modify ONLY the `bybit-connector:` service block (around lines 342-368). Two changes:

    1. Inside the `environment:` list, ADD these two lines (place them next to BYBIT_TESTNET):
        ```yaml
              - MARKET_DATA_SOURCE=${MARKET_DATA_SOURCE:-tape}
              - TAPE_FIXTURES_PATH=/app/tests/fixtures/tape
        ```

    2. Inside the `volumes:` list, ADD this read-only bind-mount BELOW the existing `./services/bybit-connector/logs:/app/logs` line:
        ```yaml
              # Tape fixtures for MARKET_DATA_SOURCE=tape mode (D-15). Read-only — never mutated by the connector.
              - ./tests/fixtures/tape:/app/tests/fixtures/tape:ro
        ```

    Do NOT change `BYBIT_API_KEY=${BYBIT_API_KEY:-}` or `BYBIT_API_SECRET=${BYBIT_API_SECRET:-}` lines — they already default to empty, which the new model_validator in plan 02 accepts in tape mode.

    Do NOT modify any other service block.

    Do NOT touch `docker-compose.yml` (the incomplete one, CLAUDE.md gotcha).
  </action>
  <verify>
    <automated>grep -A 30 'bybit-connector:' docker-compose.unified.yml | grep -q 'MARKET_DATA_SOURCE=\${MARKET_DATA_SOURCE:-tape}' && grep -A 30 'bybit-connector:' docker-compose.unified.yml | grep -q 'TAPE_FIXTURES_PATH=/app/tests/fixtures/tape' && grep -A 40 'bybit-connector:' docker-compose.unified.yml | grep -q 'tests/fixtures/tape:/app/tests/fixtures/tape:ro' && docker compose -f docker-compose.unified.yml config >/dev/null 2>&1 || python3 -c "import yaml; yaml.safe_load(open('docker-compose.unified.yml'))"</automated>
  </verify>
  <done>
    `bybit-connector:` block now exports `MARKET_DATA_SOURCE` (default tape) and `TAPE_FIXTURES_PATH`, and bind-mounts `tests/fixtures/tape/` into the container at the matching path read-only. Compose file still parses as valid YAML.
  </done>
</task>

<task type="auto">
  <name>Task 3: Create bootstrap.sh (D-09..D-13, landmines §5, §7, §8, §9)</name>
  <files>bootstrap.sh</files>
  <read_first>
    - health_check.sh (analog: bash header + SCRIPT_DIR + service port table + curl /health probe loop + status parsing — lines 1-29 + 39-63 + 194-209)
    - build-all.sh (analog: CLI flag parse + colored output + summary block + exit-on-failure — lines 36-60 + 172-193)
    - docker-compose.unified.yml (canonical compose file; reference it via `-f docker-compose.unified.yml` per CLAUDE.md gotcha)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-09 healthy-idle = 15 services /health=200; D-10 flag state at exit; D-11 touch EMERGENCY_STOP; D-12 reuse health_check.sh; D-13 fail-loud-leave-stack-up)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section "bootstrap.sh" with quoted analogs; landmines §5 BuildKit, §7 two compose files, §8 EMERGENCY_STOP semantics, §9 sentiment pip flake)
    - crypto-trading-bot/CLAUDE.md (Environment section — DOCKER_BUILDKIT=0 on WSL2; Gotchas — sentiment pip flakiness, two compose files; Project rules — never `git clean -fdx`)
  </read_first>
  <action>
    Create `bootstrap.sh` at repo root. Make executable (`chmod +x bootstrap.sh`). Mirror the bash style of `health_check.sh` + `build-all.sh`:

    EXACT structure (do NOT deviate from this skeleton — additions OK, removals NOT):

    ```bash
    #!/bin/bash
    # ============================================================================
    # Bootstrap Script for Crypto Trading Bot
    # Purpose: Provision .env, bring stack up against recorded tape, health-probe.
    # Usage: bash bootstrap.sh [--no-build]
    # Idempotent: safe to re-run. cp -n preserves operator-edited .env.
    # ============================================================================

    set -e

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    REPO_ROOT="$SCRIPT_DIR"
    cd "$REPO_ROOT"

    # ---- Colors --------------------------------------------------------------
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

    # ---- Args ----------------------------------------------------------------
    SKIP_BUILD=false
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-build) SKIP_BUILD=true; shift ;;
            *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
        esac
    done

    # ---- Step 1: Provision .env (no-clobber) ---------------------------------
    if [ ! -f "$REPO_ROOT/.env" ]; then
        cp -n "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
        echo -e "${GREEN}[1/6] Provisioned .env from .env.example${NC}"
    else
        echo -e "${YELLOW}[1/6] .env already exists — preserving operator edits${NC}"
    fi

    # ---- Step 2: WSL2 BuildKit guard (CLAUDE.md gotcha) ----------------------
    # WSL2 + Docker Desktop hangs on BuildKit. Default off unless operator overrides.
    if [ -z "${DOCKER_BUILDKIT+x}" ]; then
        if grep -qi microsoft /proc/version 2>/dev/null || [ "$(uname)" = "Linux" ]; then
            export DOCKER_BUILDKIT=0
            echo -e "${GREEN}[2/6] DOCKER_BUILDKIT=0 (WSL2 buildkit-hang workaround)${NC}"
        fi
    fi

    # ---- Step 3: Touch EMERGENCY_STOP (D-11) ---------------------------------
    # Bootstrap arms the auto-trader with EMERGENCY_STOP present so the loop holds at STEP-0.
    # Operator removes the file when ready to start trading.
    touch "$REPO_ROOT/EMERGENCY_STOP"
    echo -e "${GREEN}[3/6] EMERGENCY_STOP touched at $REPO_ROOT/EMERGENCY_STOP${NC}"

    # ---- Step 4: docker compose up (canonical compose; CLAUDE.md gotcha) -----
    COMPOSE_FILE="docker-compose.unified.yml"
    if [ "$SKIP_BUILD" = true ]; then
        docker compose -f "$COMPOSE_FILE" up -d
    else
        docker compose -f "$COMPOSE_FILE" up -d --build
    fi
    echo -e "${GREEN}[4/6] docker compose up -d completed${NC}"

    # ---- Step 5: Health probe (D-12 — reuse health_check.sh pattern) --------
    declare -A SERVICES=(
        ["api-gateway"]=8000
        ["bybit-connector"]=8001
        ["market-data"]=8002
        ["portfolio"]=8003
        ["technical-analysis"]=8004
        ["trading-engine"]=8005
        ["notification"]=8006
        ["ml-prediction"]=8007
        ["sentiment"]=8008
        ["risk-metrics"]=8009
    )
    DEADLINE=$(( $(date +%s) + 120 ))
    FAILED=()
    for svc in "${!SERVICES[@]}"; do
        port=${SERVICES[$svc]}
        ok=false
        while [ "$(date +%s)" -lt "$DEADLINE" ]; do
            if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
                ok=true; break
            fi
            sleep 2
        done
        if [ "$ok" = true ]; then
            echo -e "${GREEN}  HEALTHY  $svc:$port${NC}"
        else
            echo -e "${RED}  UNHEALTHY $svc:$port${NC}"
            FAILED+=("$svc")
        fi
    done
    # Probe DBs + queue (mirror health_check.sh:194-209)
    for ck in \
        "postgres:docker exec crypto-bot-postgres pg_isready -U postgres" \
        "timescaledb:docker exec crypto-bot-timescaledb pg_isready -U postgres" \
        "redis:docker exec crypto-bot-redis redis-cli ping" \
        "rabbitmq:curl -s http://localhost:15672/api/health/checks/alarms -u guest:guest"; do
        name=${ck%%:*}; cmd=${ck#*:}
        if eval "$cmd" >/dev/null 2>&1; then
            echo -e "${GREEN}  HEALTHY  $name${NC}"
        else
            echo -e "${RED}  UNHEALTHY $name${NC}"
            FAILED+=("$name")
        fi
    done
    # Frontend on 3000 (HTML 200 is enough — no /health route)
    if curl -sf -o /dev/null "http://localhost:3000"; then
        echo -e "${GREEN}  HEALTHY  frontend:3000${NC}"
    else
        echo -e "${RED}  UNHEALTHY frontend:3000${NC}"
        FAILED+=("frontend")
    fi
    echo -e "${GREEN}[5/6] Health probe complete — failed=${#FAILED[@]}${NC}"

    # ---- Step 6: Summary + fail-loud-leave-stack-up (D-13) -------------------
    if [ "${#FAILED[@]}" -eq 0 ]; then
        echo -e "${GREEN}[6/6] Bootstrap complete — all services healthy. EMERGENCY_STOP is in place; remove it to arm trading.${NC}"
        exit 0
    fi

    echo -e "${RED}[6/6] Bootstrap FAILED — ${#FAILED[@]} services unhealthy. Stack left running for triage.${NC}"
    for svc in "${FAILED[@]}"; do
        echo -e "${YELLOW}--- last 50 log lines: $svc ---${NC}"
        # Use `docker compose logs` (service name) as primary form — container_name in
        # docker-compose.unified.yml uses non-uniform suffixes (e.g. bybit-connector =>
        # crypto-bot-bybit, NOT crypto-bot-bybit-connector). Compose maps service name
        # to whatever container_name is configured.
        docker compose -f "$COMPOSE_FILE" logs --tail 50 "$svc" 2>&1 || true
    done
    # D-13: NO auto-teardown, NO auto-retry. Operator decides next move.
    exit 1
    ```

    Hard rules (verify in CI / by grep):
    - The script MUST NOT contain `git clean -fdx` anywhere.
    - The script MUST reference `docker-compose.unified.yml` (the canonical file).
    - The script MUST set `DOCKER_BUILDKIT=0` on Linux/WSL2.
    - The script MUST `touch` EMERGENCY_STOP at repo root.
    - The script MUST use `cp -n` (no-clobber) for `.env`.
    - The script MUST NOT print or echo BYBIT_API_KEY / BYBIT_API_SECRET (no `echo $BYBIT_*` lines).
    - On failure, the script MUST exit non-zero AND leave containers running (no `docker compose down` in the failure path).

    Inline-comment the §9 sentiment pip flake workaround (per PATTERNS landmine §9): note that if sentiment-analysis fails to build, the operator can re-run `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build sentiment-analysis` separately. Do NOT auto-retry.

    `chmod +x bootstrap.sh` after writing.
  </action>
  <verify>
    <automated>bash -n bootstrap.sh && grep -q 'docker-compose.unified.yml' bootstrap.sh && grep -q 'DOCKER_BUILDKIT=0' bootstrap.sh && grep -q 'touch.*EMERGENCY_STOP' bootstrap.sh && grep -q 'cp -n' bootstrap.sh && ! grep -q 'git clean -fdx' bootstrap.sh && ! grep -E 'echo.*\$BYBIT_(API_KEY|API_SECRET)' bootstrap.sh && grep -q 'declare -A SERVICES' bootstrap.sh && [ -x bootstrap.sh ]</automated>
  </verify>
  <done>
    `bootstrap.sh` parses as valid bash, references the canonical compose file, sets DOCKER_BUILDKIT=0 on Linux/WSL2, touches EMERGENCY_STOP, uses cp -n for .env, contains zero references to `git clean -fdx`, never echoes BYBIT credentials, defines the same 10-service port table as health_check.sh, and is executable.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Operator verifies bootstrap-against-fresh-clone (must-have: 15 services healthy + idempotent re-run)</name>
  <what-built>
    bootstrap.sh + docker-compose.unified.yml mods + .env.example mods + (from plans 01 & 02) tape fixtures + tape-mode bybit-connector. Auto verification covered syntax + grep gates + YAML validity. End-to-end runtime verification requires a Docker daemon + a fresh clone, which can't be automated in this plan-execution context.
  </what-built>
  <how-to-verify>
    On the operator's WSL2 box with Docker Desktop running.

    **Timing:** `bootstrap.sh` self-terminates at the health-probe deadline (~120s) — if it has not returned by then, treat it as a FAILURE (not a hang). Per D-13 the script never auto-retries; on timeout, exit non-zero with last 50 log lines per failed service and leave the stack up for `docker logs` post-mortem.


    1. Make a fresh tmp clone (per PROJECT.md Constraints — bootstrap-tests run against fresh clone, not working tree):
       ```
       cd /tmp && rm -rf crypto-bot-bootstrap-test && \
         git clone /mnt/d/Bimo_max/crypto-trading-bot crypto-bot-bootstrap-test && \
         cd crypto-bot-bootstrap-test
       ```

    2. Run bootstrap.sh against an EMPTY .env (test the fresh-clone path):
       ```
       rm -f .env  # ensure no .env from working tree carried over
       bash bootstrap.sh 2>&1 | tee bootstrap-run-1.log
       echo "Exit: $?"
       ```
       EXPECT: exit 0; log shows `[6/6] Bootstrap complete — all services healthy.`; .env created (with MARKET_DATA_SOURCE=tape); EMERGENCY_STOP file present at repo root.

    3. Run a SECOND time WITHOUT teardown (idempotent check — must-have):
       ```
       bash bootstrap.sh 2>&1 | tee bootstrap-run-2.log
       echo "Exit: $?"
       ```
       EXPECT: exit 0; log shows `[1/6] .env already exists — preserving operator edits`.

    4. Verify tape mode is actually active (no live API call) by grepping the bybit-connector startup log:
       ```
       docker compose -f docker-compose.unified.yml logs bybit-connector | grep BYBIT_PRICE_SOURCE
       ```
       EXPECT: at least one line `BYBIT_PRICE_SOURCE: mode=tape source_dir=/app/tests/fixtures/tape tape_version=1`. NO `mode=live` line.

    5. Confirm a SOLUSDT ticker request via the connector returns tape data:
       ```
       curl -s 'http://localhost:8001/api/v1/market/kline?category=linear&symbol=SOLUSDT&interval=5&limit=5' | head -c 500
       ```
       EXPECT: JSON with `"success": true` and a non-empty `data` array.

    6. Confirm an UNKNOWN-symbol request (XRPUSDT — not in v1 tape) does NOT 500:
       ```
       curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8001/api/v1/market/kline?category=linear&symbol=XRPUSDT&interval=5&limit=5'
       ```
       EXPECT: 200 (with empty/short data), NOT 500.

    7. Confirm EMERGENCY_STOP is in place (D-11):
       ```
       ls -la EMERGENCY_STOP
       ```
       EXPECT: file exists.

    8. Tear down for cleanup:
       ```
       docker compose -f docker-compose.unified.yml down -v
       cd /tmp && rm -rf crypto-bot-bootstrap-test
       ```
  </how-to-verify>
  <resume-signal>Type "approved" if all 8 checks pass, or paste the specific failed step + log excerpt.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| operator -> bootstrap.sh | Local shell execution; reads env, writes `.env` and EMERGENCY_STOP, no network beyond docker-compose pulls |
| bootstrap.sh -> .env | `cp -n` no-clobber preserves any operator-edited `.env` (which may contain real BYBIT keys); never overwritten |
| bootstrap.sh -> docker-compose.unified.yml -> services | Brings up containers; tape-mode default means no outbound auth; fixtures bind-mount is RO |
| bootstrap.sh stdout/stderr -> tee log | Must NEVER include BYBIT_API_KEY or BYBIT_API_SECRET in any echo / set -x trace |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | T (Tampering) | operator's .env | mitigate | `cp -n` (no-clobber) preserves any existing `.env`. Verify gate: `grep -q 'cp -n' bootstrap.sh`. NEVER `cp -f` or `>` redirect to `.env`. |
| T-03-02 | I (Information disclosure) | bootstrap.sh stdout | mitigate | No `echo $BYBIT_API_KEY` / `echo $BYBIT_API_SECRET` / `set -x` in script. Verify gate: `! grep -E 'echo.*\$BYBIT_(API_KEY\|API_SECRET)' bootstrap.sh`. |
| T-03-03 | E (Elevation of privilege) | bootstrap.sh | mitigate | Script does NOT chain into trading mode. EMERGENCY_STOP touch keeps trading-engine loop at STEP-0 (D-11). PAPER_TRADING_MODE=true + TRADING_MODE=PAPER set in .env.example, never overwritten. Bootstrap CANNOT promote to LIVE. |
| T-03-04 | D (Denial of service) | failure path | mitigate | D-13 fail-loud-leave-stack-up: on health-probe failure, exit non-zero, NO `docker compose down`, NO retry loop. Operator decides triage path. Verify gate: `! grep -E 'docker compose.*down\|while.*HEALTHY' bootstrap.sh` (the only `down` reference is in operator-runs commands, not the script). |
| T-03-05 | T (Tampering — destructive) | working tree | mitigate | Script does NOT call `git clean -fdx`. Verify gate: `! grep -q 'git clean' bootstrap.sh`. CLAUDE.md hard rule. |
</threat_model>

<verification>
- `bash -n bootstrap.sh` returns success (syntactically valid bash).
- All grep gates in T-03-01 through T-03-05 pass.
- `.env.example` includes `MARKET_DATA_SOURCE=tape` and `LIVE_TRADING_ACK=` lines.
- `docker-compose.unified.yml` parses (yaml.safe_load), and the bybit-connector block contains the new env vars + tape-fixtures bind-mount.
- Operator checkpoint Task 4 passes all 8 manual verification steps (or returns specific failures).
</verification>

<success_criteria>
- INFRA-02: `bootstrap.sh` provisions `.env` from `.env.example` (no manual edit), brings up the docker-compose stack, no `git clean -fdx`, exits 0 idempotently across two runs.
- INFRA-03 (deterministic half): The default path (`MARKET_DATA_SOURCE=tape`) brings up the stack against on-disk fixtures, no live Bybit API call, all 15 services /health=200 (verified by reused health_check.sh pattern).
- D-09 (15 services /health=200), D-10 (flag state), D-11 (EMERGENCY_STOP touched), D-12 (reused health probe), D-13 (fail-loud-leave-stack-up) — all met.
- Operator checkpoint provides empirical proof.
</success_criteria>

<output>
After completion, create `.planning/phases/01-bootstrap-recorded-tape/01-03-SUMMARY.md` capturing the bootstrap-run-1.log + bootstrap-run-2.log timings and any service that failed first probe but recovered within the 120s deadline (signal for tightening or loosening D-09 timeout in Phase 2).
</output>
