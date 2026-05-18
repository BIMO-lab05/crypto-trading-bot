#!/usr/bin/env bash
set -euo pipefail
# ============================================================================
# LIVECLOSE-01 fresh-clone harness (Phase 11.1, Plan 02).
#
# Closes carry-in INFRA-02: the operator-runnable, idempotent path that
# clones the repo into a freshly-allocated temp directory, runs the
# project bootstrap twice (idempotency check), confirms the recorded
# tape source is wired in by scanning bybit-connector logs for the
# canonical "mode=tape" marker, snapshots the 15-service stack via
# docker compose ps, and writes a schema-validated evidence JSON file
# back into the operator's actual repo via the Plan-1 shared helper.
#
# After this harness exits successfully, two operator wall-clock actions
# remain (status is AWAITING_HUMAN on success):
#   1. Inspect the evidence file under .planning/evidence/LIVECLOSE-01/
#      and commit it on the operator branch.
#   2. Flip the LIVECLOSE-01 row in .planning/state/carry_ins.json from
#      state: open to state: closed (DASHLIVE-02 contract from Phase 10).
#
# Project rules respected: never run a blanket working-tree purge against
# the operator working tree; the temp directory is always freshly
# allocated; .env is never committed (bootstrap provisions its own copy
# from .env.example via cp -n).
#
# Test surface: set LIVECLOSE_01_DRY_RUN=1 to print the 12-line stdout
# contract template (no docker, no git, no clone) and exit 0 — used by
# tests/integration/test_liveclose_01_harness.py.
# Refuse to run under TRADING_MODE=LIVE — this is a paper-only closure
# harness; mirrors run_evidence_loop.py.
# ============================================================================

# ---------------------------------------------------------------------------
# Step 0 — Paper-only guard. MUST come before any other env access so the
# refusal surfaces even when the harness is invoked with a stripped env.
# ---------------------------------------------------------------------------
if [[ "${TRADING_MODE:-}" == "LIVE" ]]; then
    echo "ERROR: refusing to run with TRADING_MODE=LIVE (paper-only harness)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1 — Dry-run branch. Prints the 12-line stdout contract verbatim
# (no docker, no git). The fixture at
# tests/closure/fixtures/liveclose_01_expected_stdout.txt is the source
# of truth; this heredoc MUST stay in sync with it.
# ---------------------------------------------------------------------------
if [[ "${LIVECLOSE_01_DRY_RUN:-}" == "1" ]]; then
    cat <<'DRYRUN_EOF'
LIVECLOSE-01 fresh-clone harness starting
TMP_CLONE_DIR=<dir>
REPO_URL=<url>
Run 1: bootstrap.sh exit=<rc>
Run 1: BYBIT_PRICE_SOURCE: mode=tape <details> (match=<yes|no>)
Run 1: compose ps running_count=<n>
Run 2: bootstrap.sh exit=<rc>
Run 2: BYBIT_PRICE_SOURCE: mode=tape <details> (match=<yes|no>)
Run 2: compose ps running_count=<n>
Evidence written: <path>
Status: <COMPLETE|AWAITING_HUMAN|FAILED>
LIVECLOSE-01 harness exit=<0|1>
DRYRUN_EOF
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 2 — Resolve original repo root (where we'll write the evidence
# file). We rely on the operator running the script from inside a
# checkout of the repo; the clone is to a temp dir, but evidence is
# written back into the operator's actual repo so it can be committed.
# ---------------------------------------------------------------------------
ORIG_REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ORIG_REPO_ROOT}" ]]; then
    echo "ERROR: must be run from inside a git checkout (need original repo root for evidence target)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 3 — Resolve repo URL. Prefer first positional arg if provided,
# otherwise read the operator's origin remote. Validated with
# `git ls-remote` to catch typos / SSH host substitution before clone.
# ---------------------------------------------------------------------------
REPO_URL="${1:-}"
if [[ -z "${REPO_URL}" ]]; then
    REPO_URL="$(git -C "${ORIG_REPO_ROOT}" remote get-url origin 2>/dev/null || true)"
fi
if [[ -z "${REPO_URL}" ]]; then
    echo "ERROR: could not resolve repo URL (no arg, no origin remote)" >&2
    exit 1
fi
if ! git ls-remote "${REPO_URL}" >/dev/null 2>&1; then
    echo "ERROR: git ls-remote failed against ${REPO_URL}; refusing to clone" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 4 — Allocate a fresh temp directory + register cleanup trap.
# The trap tears down the stack started inside the clone directory and
# (unless LIVECLOSE_01_KEEP_TMP=1) removes the temp dir on EXIT. The trap
# guards the path explicitly against the operator's working tree:
# never invoked against ${ORIG_REPO_ROOT}.
# ---------------------------------------------------------------------------
TMP_CLONE_DIR="$(mktemp -d -t liveclose-01.XXXXXX)"
cleanup() {
    local clone_root="${TMP_CLONE_DIR}/repo"
    if [[ -d "${clone_root}" && -f "${clone_root}/docker-compose.unified.yml" ]]; then
        ( cd "${clone_root}" && \
          docker compose -f docker-compose.unified.yml down -v --remove-orphans 2>/dev/null || true )
    fi
    if [[ "${LIVECLOSE_01_KEEP_TMP:-}" != "1" ]]; then
        # Defense-in-depth: ensure we only remove paths under the system
        # temp root; never touch the operator's working tree.
        case "${TMP_CLONE_DIR}" in
            /tmp/liveclose-01.*|/var/tmp/liveclose-01.*)
                rm -rf "${TMP_CLONE_DIR}"
                ;;
            *)
                echo "WARN: unexpected TMP_CLONE_DIR=${TMP_CLONE_DIR}; not removing" >&2
                ;;
        esac
    fi
}
trap cleanup EXIT

# Defensive guard: refuse to continue if PWD somehow equals the original
# repo root (we would never `docker compose down` against the operator's
# real stack from within this harness — clones run in TMP_CLONE_DIR).
if [[ "$(pwd)" == "${ORIG_REPO_ROOT}" && -z "${TMP_CLONE_DIR}" ]]; then
    echo "ERROR: refusing to run with TMP_CLONE_DIR unset against operator working tree" >&2
    exit 1
fi

echo "LIVECLOSE-01 fresh-clone harness starting"
echo "TMP_CLONE_DIR=${TMP_CLONE_DIR}"
echo "REPO_URL=${REPO_URL}"

# ---------------------------------------------------------------------------
# Step 5 — Shallow clone into the temp directory. Operators can opt into
# full-history clones via LIVECLOSE_01_CLONE_DEPTH=0.
# ---------------------------------------------------------------------------
CLONE_DEPTH="${LIVECLOSE_01_CLONE_DEPTH:-1}"
if [[ "${CLONE_DEPTH}" == "0" ]]; then
    git clone "${REPO_URL}" "${TMP_CLONE_DIR}/repo"
else
    git clone --depth "${CLONE_DEPTH}" "${REPO_URL}" "${TMP_CLONE_DIR}/repo"
fi

# ---------------------------------------------------------------------------
# Step 6 — Run 1: bootstrap the stack inside the clone, capture exit
# code + logs, scan for the canonical bybit price-source marker,
# snapshot compose ps.
# ---------------------------------------------------------------------------
cd "${TMP_CLONE_DIR}/repo"

RUN_1_RC=0
bash bootstrap.sh 2>&1 | tee "${TMP_CLONE_DIR}/bootstrap-run-1.log" || RUN_1_RC=$?

# Brief startup wait — service emits the marker promptly after lifespan
# start, so a fixed sleep is acceptable here and shorter than the
# operator-friendliness threshold.
sleep 8

BYBIT_RUN_1_MATCH="$(docker compose -f docker-compose.unified.yml logs bybit-connector 2>&1 \
    | grep -m1 'BYBIT_PRICE_SOURCE: mode=tape' || true)"

docker compose -f docker-compose.unified.yml ps --format json \
    > "${TMP_CLONE_DIR}/compose-ps-run-1.json" 2>/dev/null || true

RUNNING_COUNT_RUN_1="$(python3 -c "
import json, sys
try:
    raw = open('${TMP_CLONE_DIR}/compose-ps-run-1.json').read().strip()
except Exception:
    print(0); sys.exit(0)
# 'docker compose ps --format json' historically emits either JSON-Lines
# or a single JSON array — accept both.
rows = []
if raw.startswith('['):
    try: rows = json.loads(raw)
    except Exception: rows = []
else:
    for line in raw.splitlines():
        line = line.strip()
        if not line: continue
        try: rows.append(json.loads(line))
        except Exception: pass
count = sum(1 for r in rows if isinstance(r, dict) and r.get('State', '').lower() == 'running')
print(count)
")"

echo "Run 1: bootstrap.sh exit=${RUN_1_RC}"
if [[ -n "${BYBIT_RUN_1_MATCH}" ]]; then
    echo "Run 1: ${BYBIT_RUN_1_MATCH} (match=yes)"
else
    echo "Run 1: BYBIT_PRICE_SOURCE: mode=tape <not found> (match=no)"
fi
echo "Run 1: compose ps running_count=${RUNNING_COUNT_RUN_1}"

# ---------------------------------------------------------------------------
# Step 7 — Tear down the stack between runs so Run 2 starts from a
# clean slate (idempotency check needs a real second bring-up, not a
# no-op against an already-running stack).
# ---------------------------------------------------------------------------
docker compose -f docker-compose.unified.yml down 2>&1 || true

# ---------------------------------------------------------------------------
# Step 8 — Run 2: identical to Run 1; confirms the bootstrap path is
# safe to re-run.
# ---------------------------------------------------------------------------
RUN_2_RC=0
bash bootstrap.sh 2>&1 | tee "${TMP_CLONE_DIR}/bootstrap-run-2.log" || RUN_2_RC=$?

sleep 8

BYBIT_RUN_2_MATCH="$(docker compose -f docker-compose.unified.yml logs bybit-connector 2>&1 \
    | grep -m1 'BYBIT_PRICE_SOURCE: mode=tape' || true)"

docker compose -f docker-compose.unified.yml ps --format json \
    > "${TMP_CLONE_DIR}/compose-ps-run-2.json" 2>/dev/null || true

RUNNING_COUNT_RUN_2="$(python3 -c "
import json, sys
try:
    raw = open('${TMP_CLONE_DIR}/compose-ps-run-2.json').read().strip()
except Exception:
    print(0); sys.exit(0)
rows = []
if raw.startswith('['):
    try: rows = json.loads(raw)
    except Exception: rows = []
else:
    for line in raw.splitlines():
        line = line.strip()
        if not line: continue
        try: rows.append(json.loads(line))
        except Exception: pass
count = sum(1 for r in rows if isinstance(r, dict) and r.get('State', '').lower() == 'running')
print(count)
")"

echo "Run 2: bootstrap.sh exit=${RUN_2_RC}"
if [[ -n "${BYBIT_RUN_2_MATCH}" ]]; then
    echo "Run 2: ${BYBIT_RUN_2_MATCH} (match=yes)"
else
    echo "Run 2: BYBIT_PRICE_SOURCE: mode=tape <not found> (match=no)"
fi
echo "Run 2: compose ps running_count=${RUNNING_COUNT_RUN_2}"

# ---------------------------------------------------------------------------
# Step 9 — Decide overall status. AWAITING_HUMAN on success because the
# operator still needs to commit the evidence and flip carry_ins.json
# (LIVECLOSE-01 keeps human_needed=true per ROADMAP success criterion).
# FAILED otherwise.
# ---------------------------------------------------------------------------
STATUS="FAILED"
FAILURE_REASON=""
if [[ "${RUN_1_RC}" -ne 0 ]]; then
    FAILURE_REASON="bootstrap run 1 exited ${RUN_1_RC}"
elif [[ "${RUN_2_RC}" -ne 0 ]]; then
    FAILURE_REASON="bootstrap run 2 exited ${RUN_2_RC}"
elif [[ -z "${BYBIT_RUN_1_MATCH}" ]]; then
    FAILURE_REASON="run 1 missing BYBIT_PRICE_SOURCE: mode=tape log line"
elif [[ -z "${BYBIT_RUN_2_MATCH}" ]]; then
    FAILURE_REASON="run 2 missing BYBIT_PRICE_SOURCE: mode=tape log line"
elif [[ "${RUNNING_COUNT_RUN_1}" -lt 15 ]]; then
    FAILURE_REASON="run 1 compose ps running_count=${RUNNING_COUNT_RUN_1} (<15)"
elif [[ "${RUNNING_COUNT_RUN_2}" -lt 15 ]]; then
    FAILURE_REASON="run 2 compose ps running_count=${RUNNING_COUNT_RUN_2} (<15)"
else
    STATUS="AWAITING_HUMAN"
fi

# ---------------------------------------------------------------------------
# Step 10 — Compose evidence JSON path under the original repo root and
# invoke the Plan-1 shared helper via its CLI surface.
# ---------------------------------------------------------------------------
TARGET_TS="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET_REL=".planning/evidence/LIVECLOSE-01/run-${TARGET_TS}.json"
TARGET_ABS="${ORIG_REPO_ROOT}/${TARGET_REL}"
mkdir -p "$(dirname "${TARGET_ABS}")"

# Build the extra-payload JSON with python3 so we don't have to worry
# about embedded quotes / backslashes in the bybit log line. printf with
# %s placeholders is too fragile for arbitrary log content.
EXTRA_JSON="$(python3 -c "
import json, os, sys
print(json.dumps({
    'bootstrap_run_1_rc': int(os.environ.get('RUN_1_RC', '0')),
    'bootstrap_run_2_rc': int(os.environ.get('RUN_2_RC', '0')),
    'bybit_price_source_run_1': os.environ.get('BYBIT_RUN_1_MATCH', ''),
    'bybit_price_source_run_2': os.environ.get('BYBIT_RUN_2_MATCH', ''),
    'compose_ps_running_count_run_1': int(os.environ.get('RUNNING_COUNT_RUN_1', '0')),
    'compose_ps_running_count_run_2': int(os.environ.get('RUNNING_COUNT_RUN_2', '0')),
    'tmp_clone_dir': os.environ.get('TMP_CLONE_DIR', ''),
    'failure_reason': os.environ.get('FAILURE_REASON', ''),
}))
" RUN_1_RC="${RUN_1_RC}" RUN_2_RC="${RUN_2_RC}" \
    BYBIT_RUN_1_MATCH="${BYBIT_RUN_1_MATCH}" BYBIT_RUN_2_MATCH="${BYBIT_RUN_2_MATCH}" \
    RUNNING_COUNT_RUN_1="${RUNNING_COUNT_RUN_1}" RUNNING_COUNT_RUN_2="${RUNNING_COUNT_RUN_2}" \
    TMP_CLONE_DIR="${TMP_CLONE_DIR}" FAILURE_REASON="${FAILURE_REASON}")"

# Run the helper from the original repo root so its relative-path
# resolution (parents[2]) lands on the operator's checkout.
cd "${ORIG_REPO_ROOT}"
python -m scripts.closure._common write-evidence --liveclose-id LIVECLOSE-01 \
    --status "${STATUS}" \
    --human-needed \
    --evidence-path "${TMP_CLONE_DIR}/bootstrap-run-1.log" \
    --evidence-path "${TMP_CLONE_DIR}/bootstrap-run-2.log" \
    --evidence-path "${TMP_CLONE_DIR}/compose-ps-run-1.json" \
    --evidence-path "${TMP_CLONE_DIR}/compose-ps-run-2.json" \
    --extra-json "${EXTRA_JSON}" \
    --target-path "${TARGET_ABS}"

echo "Evidence written: ${TARGET_REL}"
echo "Status: ${STATUS}"

# ---------------------------------------------------------------------------
# Step 11 — Final exit. 0 on AWAITING_HUMAN (technical success; operator
# still has wall-clock work), 1 on FAILED.
# ---------------------------------------------------------------------------
if [[ "${STATUS}" == "AWAITING_HUMAN" || "${STATUS}" == "COMPLETE" ]]; then
    HARNESS_EXIT=0
else
    HARNESS_EXIT=1
fi
echo "LIVECLOSE-01 harness exit=${HARNESS_EXIT}"
exit "${HARNESS_EXIT}"
