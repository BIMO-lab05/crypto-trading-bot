#!/usr/bin/env bash
# =============================================================================
# repair_testnet_pollution.sh
# =============================================================================
# Runs scripts/repair_testnet_pollution.sql against the TimescaleDB container
# to demote testnet-polluted kline/ticker rows (is_mainnet=false).
#
# Container / credentials come from docker-compose.unified.yml:
#   service:   timescaledb
#   container: crypto-bot-timescaledb
#   user:      ${TIMESCALE_USER:-cryptobot}
#   database:  ${TIMESCALE_DB:-market_data}
# Auth: psql runs INSIDE the container over the local socket (trust auth in
# the official timescale/timescaledb image), so no password is needed.
#
# Usage:
#   ./scripts/repair_testnet_pollution.sh            # uses defaults
#   TIMESCALE_CONTAINER=my-db ./scripts/repair_testnet_pollution.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/repair_testnet_pollution.sql"

CONTAINER="${TIMESCALE_CONTAINER:-crypto-bot-timescaledb}"
DB_USER="${TIMESCALE_USER:-cryptobot}"
DB_NAME="${TIMESCALE_DB:-market_data}"

if [[ ! -f "${SQL_FILE}" ]]; then
    echo "ERROR: SQL file not found: ${SQL_FILE}" >&2
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    echo "ERROR: container '${CONTAINER}' is not running." >&2
    echo "Start it first: docker compose -f docker-compose.unified.yml up -d timescaledb" >&2
    exit 1
fi

echo ">>> Running testnet-pollution repair against ${CONTAINER} (db=${DB_NAME}, user=${DB_USER})"
echo ">>> The script is transactional and idempotent; re-running is safe."

# Pipe the SQL into psql inside the container. -v ON_ERROR_STOP=1 aborts (and
# rolls back the wrapping transaction) on the first error.
docker exec -i "${CONTAINER}" psql \
    -v ON_ERROR_STOP=1 \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    < "${SQL_FILE}"

echo ">>> Repair complete. Review the BEFORE/AFTER counts above."
