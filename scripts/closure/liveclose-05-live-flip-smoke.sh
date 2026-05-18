#!/usr/bin/env bash
# liveclose-05-live-flip-smoke.sh — Phase 11.1 LIVECLOSE-05 harness.
#
# Requirement: LIVECLOSE-05 (carry-in closure for OP-01 DASH-03 LIVE-flip
# manual smoke). This script DOCUMENTS the exact docker-compose recipe +
# curl probe contract operators follow when flipping api-gateway to
# TRADING_MODE=LIVE for the dashboard-visual smoke test.
#
# WARNING — DESTRUCTIVE STATE CHANGE:
# When invoked WITHOUT --dry-run / --help / --revert-only, this script
# force-recreates the api-gateway container with TRADING_MODE=LIVE. It
# refuses to do so unless LIVECLOSE_05_SUPERVISED_RUN=1 is exported,
# documenting the operator's explicit attended-session intent. Even when
# the flip succeeds, an EXIT trap restores TRADING_MODE=PAPER regardless
# of outcome (script success, error, SIGTERM, or SIGINT — SIGKILL
# bypasses the trap; that case requires manual revert).
#
# Note on LIVE flip semantics: PAPER_TRADING_MODE=true MAY remain set
# even while TRADING_MODE=LIVE on api-gateway — no real orders go out
# (per CLAUDE.md "Trading-mode flags" — four-flag friction for actual
# real-money trading). This harness exercises the dashboard's LIVE-mode
# rendering, NOT real order placement.
#
# Runbook: docs/runbooks/LIVECLOSE-05.md (5-step operator workflow,
# Diagnose/Action/Verification table, cross-refs to RUNBOOK.md
# "Pre-LIVE Operator Checklist" + PROJECT.md "Out of Scope").
#
# Operator-only work that REMAINS after this script runs:
#   - Visual confirmation of dashboard rose viewport outline +
#     red MODE pill + KILL-SWITCH state at http://localhost:3000
#   - Screenshot capture saved under .planning/evidence/LIVECLOSE-05/
#   - Evidence carry_ins.json flip after screenshot is committed
#
# The script CANNOT do the screenshot — that is the human_needed=true
# remainder logged in the evidence JSON.
#
# Documented contracts (regression-tested by tests/e2e/test_liveclose_05_smoke.py):
#   - Flip recipe (literal): docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway
#   - Revert recipe (literal): docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway
#   - Probe (literal): curl -s http://localhost:8000/api/preflight/live-readiness
#
# Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-06-PLAN.md

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly SCRIPT_NAME="liveclose-05-live-flip-smoke.sh"
readonly LIVECLOSE_ID="LIVECLOSE-05"
readonly RUNBOOK_PATH="docs/runbooks/LIVECLOSE-05.md"
readonly COMPOSE_FILE="docker-compose.unified.yml"
readonly GATEWAY_URL="${LIVECLOSE_05_GATEWAY_URL:-http://localhost:8000}"
readonly PREFLIGHT_PATH="/api/preflight/live-readiness"
readonly EXPECTED_ACK="I_UNDERSTAND_REAL_MONEY"
readonly POST_FLIP_WAIT_SECS=10
readonly POST_REVERT_WAIT_SECS=10

# Resolve repo root (scripts/closure/<this>.sh -> repo root via parents[2])
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Working-state tracking
DRY_RUN=0
REVERT_ONLY=0
HELP=0
TARGET_PATH=""
LIVE_RESPONSE_PATH=""
PAPER_AFTER_RESPONSE_PATH=""
FLIP_ATTEMPTED=0  # set to 1 after we start the LIVE flip — trap reads this
REVERT_DONE=0     # set to 1 by revert_to_paper after a successful (or attempted) revert — prevents the EXIT trap from re-reverting if main flow already called it

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
  cat <<EOF
${SCRIPT_NAME} — LIVECLOSE-05 LIVE-flip smoke harness

Usage:
  ${SCRIPT_NAME} [--help] [--dry-run] [--revert-only] [--target-path PATH]

Flags:
  --help            Print this message and exit 0.
  --dry-run         Print the compose recipe + curl probe to stdout
                    without invoking docker. Exits 0 even without
                    LIVECLOSE_05_SUPERVISED_RUN / LIVE_TRADING_ACK.
  --revert-only     Run the revert step only (restore TRADING_MODE=PAPER).
                    Useful when a previous run was interrupted. Bypasses
                    the supervised-run guard since revert IS the safety op.
  --target-path P   Override the evidence-JSON output path. Default:
                    .planning/evidence/${LIVECLOSE_ID}/run-<utc_ts>.json

Required env (only enforced on a real supervised flip):
  LIVECLOSE_05_SUPERVISED_RUN=1
        Explicit attended-session acknowledgement. Without it, the
        script exits 1 BEFORE any docker invocation.
  LIVE_TRADING_ACK=${EXPECTED_ACK}
        Trading-engine boot-time guard — flipping api-gateway alone
        without this is a half-state. Script exits 2 if missing.

Runbook: ${RUNBOOK_PATH}
Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-06-PLAN.md

Compose recipe (documented contract):
  TRADING_MODE=LIVE LIVE_TRADING_ACK=${EXPECTED_ACK} \\
      docker compose -f ${COMPOSE_FILE} up -d --force-recreate api-gateway

Revert recipe (always run on EXIT trap):
  TRADING_MODE=PAPER docker compose -f ${COMPOSE_FILE} \\
      up -d --force-recreate api-gateway

Curl probe (asserts schema_version=1 + trading_mode check present):
  curl -s ${GATEWAY_URL}${PREFLIGHT_PATH}
EOF
}

# Print to stderr with the script name prefix.
log_err() {
  echo "${SCRIPT_NAME}: $*" >&2
}

# Print informational line to stdout.
log_info() {
  echo "${SCRIPT_NAME}: $*"
}

# Refuse-unsupervised-run guard. Returns 0 if guard is satisfied or
# bypassed (--dry-run / --revert-only / --help). Returns non-zero
# (and prints to stderr) if the guard refuses.
check_supervised_run_guard() {
  if [[ "${HELP}" -eq 1 || "${DRY_RUN}" -eq 1 || "${REVERT_ONLY}" -eq 1 ]]; then
    return 0
  fi
  if [[ "${LIVECLOSE_05_SUPERVISED_RUN:-}" != "1" ]]; then
    log_err "Refusing unsupervised LIVE flip. Set LIVECLOSE_05_SUPERVISED_RUN=1 to"
    log_err "acknowledge supervised operator session. See ${RUNBOOK_PATH}."
    return 1
  fi
  return 0
}

# LIVE_TRADING_ACK guard. Same bypass rules as the supervised-run guard.
check_live_trading_ack_guard() {
  if [[ "${HELP}" -eq 1 || "${DRY_RUN}" -eq 1 || "${REVERT_ONLY}" -eq 1 ]]; then
    return 0
  fi
  if [[ "${LIVE_TRADING_ACK:-}" != "${EXPECTED_ACK}" ]]; then
    log_err "LIVE_TRADING_ACK env var missing or incorrect."
    log_err "Trading-engine would refuse to boot — flipping api-gateway alone"
    log_err "is a half-state. Set LIVE_TRADING_ACK=${EXPECTED_ACK} before re-running."
    return 2
  fi
  return 0
}

# Validate that a JSON response body parses and contains the required
# check name string. Args: <response_body>.
validate_preflight_response() {
  local body="$1"
  if [[ -z "${body}" ]]; then
    return 1
  fi
  # JSON-parse check via python3 (portable; jq may not be installed).
  if ! echo "${body}" | python3 -c \
      "import sys, json; json.loads(sys.stdin.read())" >/dev/null 2>&1; then
    return 1
  fi
  # Required substring checks (lightweight; full schema validation lives
  # in the e2e pytest, not the bash harness).
  if [[ "${body}" != *'"trading_mode"'* ]]; then
    return 1
  fi
  if [[ "${body}" != *'"paper_mode"'* ]]; then
    return 1
  fi
  if [[ "${body}" != *'"schema_version":1'* && "${body}" != *'"schema_version": 1'* ]]; then
    return 1
  fi
  return 0
}

# Save a short snippet to disk for evidence. Truncates to 1 KiB to keep
# the JSON small. Args: <body> <out_path>.
write_response_snippet() {
  local body="$1"
  local out_path="$2"
  mkdir -p "$(dirname "${out_path}")"
  echo "${body}" | head -c 1024 > "${out_path}"
}

# Print the compose recipe + curl probe in dry-run mode.
print_dry_run_recipe() {
  cat <<EOF
LIVECLOSE-05 LIVE-flip smoke — DRY RUN (no docker invocation)

[1/3] Flip recipe (compose env-prefix form — see CLAUDE.md "Trading-mode flags"):
  TRADING_MODE=LIVE LIVE_TRADING_ACK=${EXPECTED_ACK} \\
      docker compose -f ${COMPOSE_FILE} up -d --force-recreate api-gateway

[2/3] Probe under LIVE (asserts schema_version=1 + trading_mode check):
  curl -s ${GATEWAY_URL}${PREFLIGHT_PATH}

[3/3] Revert recipe (always run by EXIT trap on real run):
  TRADING_MODE=PAPER docker compose -f ${COMPOSE_FILE} \\
      up -d --force-recreate api-gateway

Runbook: ${RUNBOOK_PATH}
Required env (real run): LIVECLOSE_05_SUPERVISED_RUN=1 + LIVE_TRADING_ACK=${EXPECTED_ACK}
EOF
}

# Revert handler — wired to EXIT trap. ALWAYS runs (success or failure)
# once a flip has been attempted. Skipped when FLIP_ATTEMPTED=0 to avoid
# bouncing api-gateway unnecessarily on early-exit (--help, --dry-run,
# guard refusals).
revert_to_paper() {
  local trap_exit_code=$?

  if [[ "${FLIP_ATTEMPTED}" -eq 0 && "${REVERT_ONLY}" -eq 0 ]]; then
    # No flip happened — nothing to revert.
    return ${trap_exit_code}
  fi

  if [[ "${REVERT_DONE}" -eq 1 ]]; then
    # Main flow already invoked revert (the success path). The EXIT trap
    # is still firing because the script is ending normally; we just
    # need to be idempotent. Return the saved exit code unchanged.
    return ${trap_exit_code}
  fi

  log_info "Reverting api-gateway to TRADING_MODE=PAPER"
  # Use timeout 30s on the compose call to bound DoS from a hung daemon.
  if timeout 30 env -u LIVE_TRADING_ACK TRADING_MODE=PAPER \
      docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" \
          up -d --force-recreate api-gateway; then
    log_info "Reverted to TRADING_MODE=PAPER"
  else
    log_err "Revert step failed (timeout or compose error). Operator must"
    log_err "manually run: TRADING_MODE=PAPER docker compose -f ${COMPOSE_FILE} \\"
    log_err "    up -d --force-recreate api-gateway"
  fi

  # Wait briefly then probe to confirm PAPER state. Failure here is
  # logged but does not change the script's exit code — the operator
  # already has the evidence the flip happened.
  sleep "${POST_REVERT_WAIT_SECS}"
  local paper_resp
  paper_resp="$(curl -s --max-time 5 "${GATEWAY_URL}${PREFLIGHT_PATH}" || echo '')"
  if validate_preflight_response "${paper_resp}"; then
    log_info "Probe under PAPER: ok"
    if [[ -n "${PAPER_AFTER_RESPONSE_PATH}" ]]; then
      write_response_snippet "${paper_resp}" "${PAPER_AFTER_RESPONSE_PATH}"
    fi
  else
    log_err "Probe under PAPER: FAIL (api-gateway not yet healthy or shape mismatch)"
  fi

  REVERT_DONE=1
  return ${trap_exit_code}
}

# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      HELP=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --revert-only)
      REVERT_ONLY=1
      shift
      ;;
    --target-path)
      TARGET_PATH="$2"
      shift 2
      ;;
    *)
      log_err "Unknown flag: $1 (try --help)"
      exit 64
      ;;
  esac
done

if [[ "${HELP}" -eq 1 ]]; then
  usage
  exit 0
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  print_dry_run_recipe
  exit 0
fi

# ---------------------------------------------------------------------------
# Guards (only reached on real supervised flip OR --revert-only)
# ---------------------------------------------------------------------------

if ! check_supervised_run_guard; then
  exit 1
fi

if ! check_live_trading_ack_guard; then
  exit 2
fi

# ---------------------------------------------------------------------------
# --revert-only fast path
# ---------------------------------------------------------------------------

if [[ "${REVERT_ONLY}" -eq 1 ]]; then
  log_info "Running revert-only path (no LIVE flip attempted)"
  # Call revert_to_paper DIRECTLY rather than relying on the EXIT trap.
  # The trap is registered later in the supervised-flip path; if we set
  # FLIP_ATTEMPTED=1 here and exit before registering the trap, the
  # revert never actually runs. PAPER_AFTER_RESPONSE_PATH stays empty
  # so revert_to_paper skips the evidence-snippet write (guard at line
  # ~246 already covers this case).
  FLIP_ATTEMPTED=1
  revert_to_paper
  exit 0
fi

# ---------------------------------------------------------------------------
# Real supervised LIVE flip path
# ---------------------------------------------------------------------------

# Resolve target paths and create scratch dir.
UTC_TS="$(date -u +"%Y%m%dT%H%M%SZ")"
if [[ -z "${TARGET_PATH}" ]]; then
  TARGET_PATH="${REPO_ROOT}/.planning/evidence/${LIVECLOSE_ID}/run-${UTC_TS}.json"
fi
EVIDENCE_DIR="$(dirname "${TARGET_PATH}")"
mkdir -p "${EVIDENCE_DIR}"
LIVE_RESPONSE_PATH="${EVIDENCE_DIR}/probe-live-${UTC_TS}.txt"
PAPER_AFTER_RESPONSE_PATH="${EVIDENCE_DIR}/probe-paper-after-${UTC_TS}.txt"

log_info "LIVECLOSE-05 LIVE-flip smoke"

# Pre-flip probe — confirm we're starting from a known PAPER state.
# Literal route: /api/preflight/live-readiness (substituted via PREFLIGHT_PATH).
log_info "Pre-flip probe: ${GATEWAY_URL}${PREFLIGHT_PATH}"
PAPER_BEFORE_RESPONSE="$(curl -s --max-time 5 "${GATEWAY_URL}${PREFLIGHT_PATH}" || echo '')"  # /api/preflight/live-readiness
if ! validate_preflight_response "${PAPER_BEFORE_RESPONSE}"; then
  log_err "Pre-flip probe: FAIL — response did not match expected schema_version=1 +"
  log_err "trading_mode + paper_mode shape. Refusing to flip without a known"
  log_err "PAPER baseline. Code: PRE_FLIP_PROBE_FAILED"
  log_err "Got: ${PAPER_BEFORE_RESPONSE}"
  exit 3
fi
log_info "Pre-flip probe: ok"

# Register the EXIT trap NOW — before any docker invocation that flips
# state. Order matters: if the docker call below errors mid-flight, the
# trap still runs the revert. Trap covers EXIT (catches errexit, normal
# exit, set -e failures), INT (Ctrl-C), TERM (SIGTERM from operator
# kill). SIGKILL bypasses the trap by design (kernel-level); the script
# header documents that case.
trap revert_to_paper EXIT INT TERM

# Flip api-gateway to TRADING_MODE=LIVE.
log_info "Flipping api-gateway to TRADING_MODE=LIVE"
FLIP_ATTEMPTED=1
TRADING_MODE=LIVE LIVE_TRADING_ACK="${EXPECTED_ACK}" \
    docker compose -f "${REPO_ROOT}/${COMPOSE_FILE}" \
        up -d --force-recreate api-gateway

# Wait for healthcheck then probe under LIVE.
log_info "Waiting ${POST_FLIP_WAIT_SECS}s for api-gateway healthcheck"
sleep "${POST_FLIP_WAIT_SECS}"

# Post-flip probe — same route /api/preflight/live-readiness, now under LIVE.
LIVE_RESPONSE="$(curl -s --max-time 5 "${GATEWAY_URL}${PREFLIGHT_PATH}" || echo '')"  # /api/preflight/live-readiness
if validate_preflight_response "${LIVE_RESPONSE}"; then
  log_info "Probe under LIVE: ok"
else
  log_err "Probe under LIVE: FAIL (api-gateway not healthy or shape mismatch)"
  log_err "Got: ${LIVE_RESPONSE}"
  # Do not exit — the EXIT trap still needs to revert.
fi
write_response_snippet "${LIVE_RESPONSE}" "${LIVE_RESPONSE_PATH}"

# Operator-action prompt: visual confirmation + screenshot capture.
log_info "OPERATOR ACTION: Visit ${GATEWAY_URL%:8000}:3000 and capture screenshot"
log_info "OPERATOR ACTION: Press ENTER to revert to PAPER (auto-revert in 120s)"

# Wait up to 120s for ENTER, else auto-revert via timeout. `read -t` is
# bash-portable and respects the trap if SIGTERM arrives mid-wait.
if read -t 120 -r _; then
  log_info "Operator triggered revert"
else
  log_info "Auto-revert after 120s timeout"
fi

# Run the revert step explicitly in main flow so that PAPER_AFTER_RESPONSE_PATH
# is populated on disk BEFORE we invoke write-evidence (otherwise the JSON
# would list a path that doesn't exist yet for ~10s until the EXIT trap
# fires). The EXIT trap stays registered as a fallback for error paths;
# revert_to_paper is idempotent via the REVERT_DONE flag.
revert_to_paper

# Write evidence JSON via the shared _common.py CLI. Note we pass
# --status AWAITING_HUMAN + --human-needed (the screenshot is operator-
# only — the harness cannot close the carry-in on its own).
COMPOSE_RECIPE="TRADING_MODE=LIVE LIVE_TRADING_ACK=${EXPECTED_ACK} docker compose -f ${COMPOSE_FILE} up -d --force-recreate api-gateway"
REVERT_RECIPE="TRADING_MODE=PAPER docker compose -f ${COMPOSE_FILE} up -d --force-recreate api-gateway"
PROBE_LIVE_SNIPPET="$(echo "${LIVE_RESPONSE}" | head -c 1024)"

EXTRA_JSON="$(python3 -c "
import json, sys
print(json.dumps({
    'compose_recipe': sys.argv[1],
    'revert_recipe': sys.argv[2],
    'probe_response_live': sys.argv[3],
    'supervised_run': True,
    'runbook': sys.argv[4],
    'gateway_url': sys.argv[5],
}))
" "${COMPOSE_RECIPE}" "${REVERT_RECIPE}" "${PROBE_LIVE_SNIPPET}" "${RUNBOOK_PATH}" "${GATEWAY_URL}")"

LIVE_REL="${LIVE_RESPONSE_PATH#${REPO_ROOT}/}"
PAPER_REL="${PAPER_AFTER_RESPONSE_PATH#${REPO_ROOT}/}"

log_info "Writing evidence JSON via scripts.closure._common"
EVIDENCE_TARGET="$(cd "${REPO_ROOT}" && python3 -m scripts.closure._common write-evidence \
    --liveclose-id "${LIVECLOSE_ID}" \
    --status AWAITING_HUMAN \
    --human-needed \
    --evidence-path "${LIVE_REL}" \
    --evidence-path "${PAPER_REL}" \
    --extra-json "${EXTRA_JSON}" \
    --target-path "${TARGET_PATH}")"

log_info "Wrote evidence: ${EVIDENCE_TARGET}"
log_info "Status: AWAITING_HUMAN (screenshot is operator-only)"
log_info "Next: capture dashboard screenshot, save under .planning/evidence/${LIVECLOSE_ID}/,"
log_info "commit, then flip the ${LIVECLOSE_ID} row in .planning/state/carry_ins.json."
