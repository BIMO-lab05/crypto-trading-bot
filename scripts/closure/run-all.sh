#!/usr/bin/env bash
# ============================================================================
# scripts/closure/run-all.sh — Phase 11.1 Plan 07 (Wave 3) orchestrator.
#
# Single-command discovery + status entrypoint for the five LIVECLOSE
# carry-in closure harnesses (LIVECLOSE-01..05). Read-mostly by design —
# the five carry-ins are all `human_needed`, so this script DOES NOT
# auto-iterate over them.
#
# Carry-ins (LIVECLOSE-INDEX.md is the source of truth):
#   LIVECLOSE-01 — Fresh-clone bootstrap     (bash liveclose-01-fresh-clone.sh)
#   LIVECLOSE-02 — CI URL recorder           (bash liveclose-02-record-ci.sh)
#   LIVECLOSE-03 — PSR-CI accrual exporter   (python -m scripts.closure.liveclose_03_psr_evidence)
#   LIVECLOSE-04 — T0.1.x verdict exporter   (python -m scripts.closure.liveclose_04_sweep_verdict)
#   LIVECLOSE-05 — LIVE-flip manual smoke    (bash liveclose-05-live-flip-smoke.sh)
#
# Hyphen-form aliases (referenced by .sh names): liveclose-01-fresh-clone,
# liveclose-02-record-ci, liveclose-03-psr-evidence,
# liveclose-04-sweep-verdict, liveclose-05-live-flip-smoke. The .py
# harnesses on disk use underscore form (Python import contract) — the
# aliases above are documentation only.
#
# Flag surface:
#   --list   (default)  print harness table with carry-in state
#   --status            same as --list plus latest evidence-file status
#   --help              print usage and exit
#   --exec <ID>         invoke ONE named harness; LIVECLOSE-05 refused
#                       (operator-supervised only).
#
# Threat model: per Plan 11.1-07 T-11.1-07-01..05, this orchestrator
# MUST refuse to invoke LIVECLOSE-05 (the LIVE-flip smoke). The refusal
# delegates to the LIVECLOSE-05 harness's own LIVECLOSE_05_SUPERVISED_RUN
# guard, but is also enforced inline so even a stub harness cannot bypass.
#
# Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-07-PLAN.md
# Index: .planning/evidence/LIVECLOSE-INDEX.md
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Path resolution — locate repo root via the script's own location, NOT
# via `git rev-parse` (some operators run this from a fresh tarball
# extraction or detached worktree).
# ---------------------------------------------------------------------------
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "${SCRIPT_PATH}")"
# scripts/closure/ → repo root is two levels up.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# CWD-driven discovery for the carry-in state file: the orchestrator
# reads `.planning/state/carry_ins.json` relative to the current working
# directory so it can be invoked from a tmp tree (used by the missing-
# state-file integration test).
CARRY_INS_JSON="${PWD}/.planning/state/carry_ins.json"
EVIDENCE_BASE="${PWD}/.planning/evidence"

# Harness table — order matches LIVECLOSE-INDEX.md. Each row is one
# carry-in: ID | command literal | evidence dir.
# Bash 3.2+ compatibility — use parallel arrays, not associative arrays.
LIVECLOSE_IDS=(
    "LIVECLOSE-01"
    "LIVECLOSE-02"
    "LIVECLOSE-03"
    "LIVECLOSE-04"
    "LIVECLOSE-05"
)

# Command literals — printed verbatim. The python module names use
# underscore form (Python import contract); the .sh paths use hyphen form.
LIVECLOSE_CMDS=(
    "bash scripts/closure/liveclose-01-fresh-clone.sh"
    "bash scripts/closure/liveclose-02-record-ci.sh --url <green-run-url>"
    "python -m scripts.closure.liveclose_03_psr_evidence"
    "python -m scripts.closure.liveclose_04_sweep_verdict"
    "LIVECLOSE_05_SUPERVISED_RUN=1 bash scripts/closure/liveclose-05-live-flip-smoke.sh"
)

LIVECLOSE_EVIDENCE_DIRS=(
    ".planning/evidence/LIVECLOSE-01/"
    ".planning/evidence/LIVECLOSE-02/"
    ".planning/evidence/LIVECLOSE-03/"
    ".planning/evidence/LIVECLOSE-04/"
    ".planning/evidence/LIVECLOSE-05/"
)

# carry_ins.json ID mapping. Phase 10 DASHLIVE-02 names the operator
# carry-ins OP-01..OP-04 + INFRA-02; LIVECLOSE-0X is the evidence-tree
# identifier. LIVECLOSE-01 backs INFRA-02; LIVECLOSE-05 backs OP-01.
# LIVECLOSE-02/03/04 carry evidence that contributes to OP-04/02/03
# respectively, but the closure of those OP- rows is driven by a separate
# operator step — the orchestrator reports `unknown` for those rather
# than inventing a mapping that might paper over a drift.
LIVECLOSE_TO_OP=(
    "INFRA-02"
    ""
    ""
    ""
    "OP-01"
)

# ---------------------------------------------------------------------------
# usage() — printed by --help and on argument errors.
# ---------------------------------------------------------------------------
usage() {
    cat <<'USAGE_EOF'
Usage: bash scripts/closure/run-all.sh [FLAG]

LIVECLOSE Carry-In Closure Harness Orchestrator (Phase 11.1 Plan 07).

Discovery + status entrypoint for the five LIVECLOSE-0X carry-in closure
harnesses. Read-mostly by design — the five carry-ins are all
human_needed, so this script does NOT auto-iterate over them.

Flags:
    --list           (default) Print the harness table with carry-in
                     state from .planning/state/carry_ins.json.
    --status         Same as --list plus the status field from each
                     harness's latest evidence file (if any).
    --help           Print this usage and exit.
    --exec <ID>      Invoke ONE named harness. Whitelist: LIVECLOSE-01,
                     LIVECLOSE-02, LIVECLOSE-03, LIVECLOSE-04.
                     LIVECLOSE-05 is REFUSED — operator-supervised only
                     (export LIVECLOSE_05_SUPERVISED_RUN=1 and run
                     scripts/closure/liveclose-05-live-flip-smoke.sh
                     directly).

Examples:
    bash scripts/closure/run-all.sh                       # default --list
    bash scripts/closure/run-all.sh --status              # with evidence
    bash scripts/closure/run-all.sh --exec LIVECLOSE-01   # run harness 1

See .planning/evidence/LIVECLOSE-INDEX.md for the full carry-in details
and the operator follow-up protocol.
USAGE_EOF
}

# ---------------------------------------------------------------------------
# carry_in_state(): emit the `state` field for a LIVECLOSE-0X id by
# resolving it through LIVECLOSE_TO_OP and reading carry_ins.json. If the
# state file is missing or the carry-in has no operator-side row, print
# `unknown` (never crash).
# ---------------------------------------------------------------------------
carry_in_state() {
    local idx="$1"
    local op_id="${LIVECLOSE_TO_OP[${idx}]}"

    if [[ ! -f "${CARRY_INS_JSON}" ]]; then
        echo "unknown"
        return 0
    fi

    if [[ -z "${op_id}" ]]; then
        echo "unknown"
        return 0
    fi

    # Single-line Python query — no jq dependency. Errors degrade to unknown.
    python3 - "${CARRY_INS_JSON}" "${op_id}" <<'PY' 2>/dev/null || echo "unknown"
import json
import sys

path, op_id = sys.argv[1], sys.argv[2]
try:
    data = json.loads(open(path).read())
except Exception:
    print("unknown")
    sys.exit(0)
for row in data.get("carry_ins", []):
    if row.get("id") == op_id:
        print(row.get("state", "unknown"))
        sys.exit(0)
print("unknown")
PY
}

# ---------------------------------------------------------------------------
# latest_evidence_status(): for a LIVECLOSE-0X dir, find the newest *.json
# file (by mtime) and print its `status` field. Falls back to
# `no-evidence-yet` when the dir is missing or empty.
# ---------------------------------------------------------------------------
latest_evidence_status() {
    local idx="$1"
    local evidence_dir="${PWD}/${LIVECLOSE_EVIDENCE_DIRS[${idx}]}"

    if [[ ! -d "${evidence_dir}" ]]; then
        echo "no-evidence-yet"
        return 0
    fi

    # find newest JSON file. ls -1t is portable; null when nothing matches.
    local newest
    # shellcheck disable=SC2012  # ls -t is fine here; filenames are timestamped.
    newest="$(ls -1t "${evidence_dir}"*.json 2>/dev/null | head -n 1 || true)"
    if [[ -z "${newest}" ]]; then
        echo "no-evidence-yet"
        return 0
    fi

    python3 - "${newest}" <<'PY' 2>/dev/null || echo "unknown"
import json
import sys

try:
    data = json.loads(open(sys.argv[1]).read())
    print(data.get("status", "unknown"))
except Exception:
    print("unknown")
PY
}

# ---------------------------------------------------------------------------
# print_table(): emit the harness discovery table. include_status=1 adds
# the latest-evidence status row.
# ---------------------------------------------------------------------------
print_table() {
    local include_status="${1:-0}"

    echo "LIVECLOSE Carry-In Closure Harnesses (Phase 11.1)"
    printf '%.0s=' {1..48}
    echo

    local i
    for i in "${!LIVECLOSE_IDS[@]}"; do
        local id="${LIVECLOSE_IDS[${i}]}"
        local cmd="${LIVECLOSE_CMDS[${i}]}"
        local target="${LIVECLOSE_EVIDENCE_DIRS[${i}]}"
        local state
        state="$(carry_in_state "${i}")"

        echo
        echo "${id}  ${cmd}"
        echo "  state:   ${state}"
        if [[ "${include_status}" == "1" ]]; then
            local latest
            latest="$(latest_evidence_status "${i}")"
            echo "  latest:  ${latest}"
        fi
        echo "  target:  ${target}"
    done

    echo
    echo "See .planning/evidence/LIVECLOSE-INDEX.md for full details."
}

# ---------------------------------------------------------------------------
# exec_harness(): invoke ONE named carry-in harness. Whitelist enforced
# via case (no `eval`, no shell interpolation of the ID).
# ---------------------------------------------------------------------------
exec_harness() {
    local id="$1"

    case "${id}" in
        LIVECLOSE-01)
            exec bash "${REPO_ROOT}/scripts/closure/liveclose-01-fresh-clone.sh"
            ;;
        LIVECLOSE-02)
            exec bash "${REPO_ROOT}/scripts/closure/liveclose-02-record-ci.sh"
            ;;
        LIVECLOSE-03)
            cd "${REPO_ROOT}" || exit 1
            exec python3 -m scripts.closure.liveclose_03_psr_evidence
            ;;
        LIVECLOSE-04)
            cd "${REPO_ROOT}" || exit 1
            exec python3 -m scripts.closure.liveclose_04_sweep_verdict
            ;;
        LIVECLOSE-05)
            cat >&2 <<'REFUSAL_EOF'
ERROR: LIVECLOSE-05 must be operator-supervised; run
scripts/closure/liveclose-05-live-flip-smoke.sh directly with
LIVECLOSE_05_SUPERVISED_RUN=1. The orchestrator will not auto-flip
TRADING_MODE=LIVE — see threat model T-11.1-07-01.
REFUSAL_EOF
            exit 2
            ;;
        *)
            echo "ERROR: unknown harness id '${id}' — must be one of LIVECLOSE-01..LIVECLOSE-04" >&2
            echo "       (LIVECLOSE-05 is operator-supervised only — see --help)" >&2
            exit 2
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Argument dispatch — manual case (no getopts; we only have four flags).
# ---------------------------------------------------------------------------

# Default: --list (no flags supplied).
if [[ $# -eq 0 ]]; then
    print_table 0
    exit 0
fi

case "$1" in
    --help|-h)
        usage
        exit 0
        ;;
    --list)
        print_table 0
        exit 0
        ;;
    --status)
        print_table 1
        exit 0
        ;;
    --exec)
        if [[ $# -lt 2 ]]; then
            echo "ERROR: --exec requires a LIVECLOSE-0X id (got nothing)" >&2
            usage >&2
            exit 2
        fi
        exec_harness "$2"
        ;;
    *)
        echo "ERROR: unknown flag '$1'" >&2
        usage >&2
        exit 2
        ;;
esac
