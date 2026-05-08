#!/bin/bash
# ============================================================================
# Bootstrap Script for Crypto Trading Bot
# Purpose: Provision .env, bring stack up against recorded tape, health-probe.
# Usage: bash bootstrap.sh [--no-build]
# Idempotent: safe to re-run. cp -n preserves operator-edited .env.
#
# Landmine §9 (CLAUDE.md): sentiment-analysis-service image has historically
# failed pip build (PyPI read timeouts). If docker compose up fails on that
# service, retry the build separately:
#   DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build sentiment-analysis
# Then re-run bootstrap.sh. Per D-13: NO auto-retry inside this script.
# Full triage guide: see RUNBOOK.md (Phase 2 INFRA-05).
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
    docker compose -f "$COMPOSE_FILE" --profile ml --profile analytics up -d
else
    docker compose -f "$COMPOSE_FILE" --profile ml --profile analytics up -d --build
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
