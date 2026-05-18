#!/usr/bin/env bash
# scripts/closure/liveclose-02-record-ci.sh
#
# LIVECLOSE-02 CI-URL recorder harness (Phase 11.1 Plan 03, Wave 2).
#
# Captures a GitHub Actions run URL for the nightly `integration-ml-on.yml`
# workflow once it has gone green (OP-04 GH Actions billing unblocked).
# Validates the URL points at the correct workflow file with
# `conclusion=success` via `gh api`, then writes both an operator-readable
# `ci-url.txt` and a schema-conformant evidence JSON via the shared helper
# `scripts/closure/_common.py`.
#
# The harness is paper-only — it refuses to run under `TRADING_MODE=LIVE`
# (mirrors LIVECLOSE-01 + run_evidence_loop.py refusal pattern).
#
# Pass `--skip-gh-api` to skip the network call (offline unit tests / repos
# behind authentication that the harness cannot satisfy). URL format
# validation always runs, even when `--skip-gh-api` is set.
#
# Exit codes:
#   0  success — ci-url.txt + evidence JSON written, status AWAITING_HUMAN
#   1  paper-only refusal (TRADING_MODE=LIVE) or evidence helper failure
#   2  URL_FORMAT_INVALID — regex rejected the URL
#   3  GH_API_FAILED — `gh api` exited non-zero
#   4  WORKFLOW_MISMATCH — URL points at a workflow other than integration-ml-on.yml
#   5  CONCLUSION_NOT_SUCCESS — run conclusion is not "success"
#
# Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-03-PLAN.md
# Schema: .planning/evidence/_schema.json
# Workflow: .github/workflows/integration-ml-on.yml

set -euo pipefail

# ---------------------------------------------------------------------------
# Paper-only refusal — fires BEFORE argument parsing so even `--help` under
# LIVE mode is rejected. Exit 1 distinguishes refusal from URL_FORMAT_INVALID
# (exit 2) so the test suite can assert paper-only refusal explicitly.
# ---------------------------------------------------------------------------
if [[ -n "${TRADING_MODE:-}" && "${TRADING_MODE^^}" == "LIVE" ]]; then
    echo "TRADING_MODE=LIVE — harness is paper-only; refusing to run" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Argument defaults + parser. Manual getopts loop — no getopt(1) dep.
# ---------------------------------------------------------------------------
URL=""
SKIP_GH_API=0
TARGET_PATH=""
CI_URL_TXT_PATH=""

print_usage() {
    cat <<'EOF'
Usage: liveclose-02-record-ci.sh --url <URL> [options]

LIVECLOSE-02 CI-URL recorder. Validates a GitHub Actions run URL points at
the integration-ml-on.yml nightly workflow with conclusion=success, then
writes ci-url.txt + evidence JSON via scripts.closure._common.

Required:
  --url <URL>                  GitHub Actions run URL for the green nightly run.

Options:
  --skip-gh-api                Skip the `gh api` network call. URL format
                               validation still runs. For offline tests and
                               repos the harness cannot authenticate against.
  --target-path <path>         Override evidence JSON output path.
                               Default: .planning/evidence/LIVECLOSE-02/evidence-<UTC>.json
  --ci-url-txt-path <path>     Override ci-url.txt output path.
                               Default: .planning/evidence/LIVECLOSE-02/ci-url.txt
  --help                       Print this message and exit 0.

Exit codes: 0=success, 1=paper-only refusal, 2=URL_FORMAT_INVALID,
3=GH_API_FAILED, 4=WORKFLOW_MISMATCH, 5=CONCLUSION_NOT_SUCCESS.

Fixture env (consumed only when --skip-gh-api is set):
  LIVECLOSE_02_FIXTURE_WORKFLOW_NAME — workflow_name recorded in extra (default "<skipped>")
  LIVECLOSE_02_FIXTURE_CONCLUSION    — conclusion recorded in extra      (default "<skipped>")
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)
            URL="${2:-}"
            shift 2
            ;;
        --skip-gh-api)
            SKIP_GH_API=1
            shift
            ;;
        --target-path)
            TARGET_PATH="${2:-}"
            shift 2
            ;;
        --ci-url-txt-path)
            CI_URL_TXT_PATH="${2:-}"
            shift 2
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            print_usage >&2
            exit 64  # EX_USAGE — distinct from validation/paper-only refusal exits
            ;;
    esac
done

if [[ -z "$URL" ]]; then
    echo "ERROR: --url is required" >&2
    print_usage >&2
    exit 64
fi

# ---------------------------------------------------------------------------
# Resolve repo root + default paths. The harness lives at
# scripts/closure/liveclose-02-record-ci.sh; repo root is two parents up.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." &>/dev/null && pwd)"
EVIDENCE_DIR="${REPO_ROOT}/.planning/evidence/LIVECLOSE-02"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ -z "$TARGET_PATH" ]]; then
    TARGET_PATH="${EVIDENCE_DIR}/evidence-${TIMESTAMP}.json"
fi
if [[ -z "$CI_URL_TXT_PATH" ]]; then
    CI_URL_TXT_PATH="${EVIDENCE_DIR}/ci-url.txt"
fi

# ---------------------------------------------------------------------------
# URL format validation (ALWAYS runs, even under --skip-gh-api).
#
# Pattern accepts:
#   - https://github.com/<owner>/<repo>/actions/runs/<numeric-id>
#   - optionally followed by /<subpath> (e.g. /job/<id>) — group 1
#   - optionally followed by ?<query>                    — group 2
#
# Reject branches the regex catches:
#   - non-github.com host
#   - missing run_id segment (trailing slash with nothing after)
#   - non-numeric run_id segment
# ---------------------------------------------------------------------------
URL_REGEX='^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+(/[^?]*)?(\?.*)?$'
if ! [[ "$URL" =~ $URL_REGEX ]]; then
    echo "URL_FORMAT_INVALID url=$URL" >&2
    exit 2
fi

# Extract owner/repo and run_id from the URL via a parse regex.
PARSE_REGEX='^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/actions/runs/([0-9]+)'
if ! [[ "$URL" =~ $PARSE_REGEX ]]; then
    # Should be unreachable — URL_REGEX above must have passed for us to get here.
    echo "URL_FORMAT_INVALID url=$URL (parse failed)" >&2
    exit 2
fi
OWNER="${BASH_REMATCH[1]}"
REPO="${BASH_REMATCH[2]}"
RUN_ID="${BASH_REMATCH[3]}"
OWNER_REPO="${OWNER}/${REPO}"

# ---------------------------------------------------------------------------
# Network validation branch — only when --skip-gh-api is NOT set.
# Calls `gh api repos/<owner>/<repo>/actions/runs/<run_id>` and asserts:
#   - workflow path == .github/workflows/integration-ml-on.yml
#   - conclusion    == success
# ---------------------------------------------------------------------------
WORKFLOW_PATH=""
CONCLUSION=""
WORKFLOW_NAME=""

if [[ "$SKIP_GH_API" -eq 0 ]]; then
    if ! command -v gh >/dev/null 2>&1; then
        echo "GH_API_FAILED gh not installed; pass --skip-gh-api for offline use" >&2
        exit 3
    fi
    GH_OUTPUT=""
    if ! GH_OUTPUT="$(gh api "repos/${OWNER_REPO}/actions/runs/${RUN_ID}" \
        --jq '.path,.conclusion,.name' 2>&1)"; then
        echo "GH_API_FAILED owner_repo=${OWNER_REPO} run_id=${RUN_ID}: ${GH_OUTPUT}" >&2
        exit 3
    fi
    # gh --jq '.a,.b,.c' returns three lines in the order requested.
    WORKFLOW_PATH="$(printf '%s\n' "$GH_OUTPUT" | sed -n '1p')"
    CONCLUSION="$(printf '%s\n' "$GH_OUTPUT" | sed -n '2p')"
    WORKFLOW_NAME="$(printf '%s\n' "$GH_OUTPUT" | sed -n '3p')"

    if [[ "$WORKFLOW_PATH" != ".github/workflows/integration-ml-on.yml" ]]; then
        echo "WORKFLOW_MISMATCH expected=.github/workflows/integration-ml-on.yml got=${WORKFLOW_PATH}" >&2
        exit 4
    fi
    if [[ "$CONCLUSION" != "success" ]]; then
        echo "CONCLUSION_NOT_SUCCESS got=${CONCLUSION}" >&2
        exit 5
    fi
else
    # Skip branch — populate workflow_name + conclusion from fixture env (used
    # by unit tests to record realistic values) or fall back to placeholders.
    WORKFLOW_PATH=".github/workflows/integration-ml-on.yml"
    WORKFLOW_NAME="${LIVECLOSE_02_FIXTURE_WORKFLOW_NAME:-<skipped>}"
    CONCLUSION="${LIVECLOSE_02_FIXTURE_CONCLUSION:-<skipped>}"
fi

# ---------------------------------------------------------------------------
# Write ci-url.txt verbatim (URL + exactly one trailing newline). Create
# parent directories if missing so operator-supplied paths under tmp_path
# work without setup.
# ---------------------------------------------------------------------------
mkdir -p -- "$(dirname -- "$CI_URL_TXT_PATH")"
printf '%s\n' "$URL" >"$CI_URL_TXT_PATH"

# ---------------------------------------------------------------------------
# Build the JSON payload for `--extra-json`. We use python3 here rather than
# jq because jq is not guaranteed on every host; python is a hard requirement
# already (the evidence-writer helper is python).
#
# Variables flow into python via env vars (NOT shell-interpolated into the
# python source) — defends against shell injection in operator-supplied
# argument values (T-11.1-03-05 in the threat model).
# ---------------------------------------------------------------------------
EXTRA_JSON="$(
    URL="$URL" \
    RUN_ID="$RUN_ID" \
    OWNER_REPO="$OWNER_REPO" \
    WORKFLOW_PATH="$WORKFLOW_PATH" \
    WORKFLOW_NAME="$WORKFLOW_NAME" \
    CONCLUSION="$CONCLUSION" \
    SKIP_GH_API="$SKIP_GH_API" \
    python3 -c '
import json, os
print(json.dumps({
    "ci_url":        os.environ["URL"],
    "run_id":        int(os.environ["RUN_ID"]),
    "owner_repo":    os.environ["OWNER_REPO"],
    "workflow_path": os.environ["WORKFLOW_PATH"],
    "workflow_name": os.environ["WORKFLOW_NAME"],
    "conclusion":    os.environ["CONCLUSION"],
    "skip_gh_api":   os.environ["SKIP_GH_API"] == "1",
}))
'
)"

# ---------------------------------------------------------------------------
# Invoke the shared helper to write + validate evidence JSON. Status is
# AWAITING_HUMAN: operator still commits ci-url.txt + flips
# .planning/state/carry_ins.json LIVECLOSE-02 row from open → closed.
# ---------------------------------------------------------------------------
mkdir -p -- "$(dirname -- "$TARGET_PATH")"
if ! ( cd "$REPO_ROOT" && python3 -m scripts.closure._common write-evidence \
    --liveclose-id LIVECLOSE-02 \
    --status AWAITING_HUMAN \
    --human-needed \
    --evidence-path "$CI_URL_TXT_PATH" \
    --extra-json "$EXTRA_JSON" \
    --target-path "$TARGET_PATH" \
    >/dev/null ); then
    echo "FAILED evidence-helper rejected payload" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Wave 2 plan currently writes extra fields as TOP-LEVEL keys (helper
# implementation merges extra into the root payload). For ergonomic test
# assertions (`payload["extra"]["run_id"]`), the plan + tests assume the
# extra dict ALSO appears under an "extra" key. Re-emit the JSON with the
# extra block nested under "extra" so consumers have a single, stable
# location to read harness-specific fields. The top-level keys remain so
# any existing reader still works.
# ---------------------------------------------------------------------------
EXTRA_JSON="$EXTRA_JSON" TARGET_PATH="$TARGET_PATH" python3 -c '
import json, os
from pathlib import Path
p = Path(os.environ["TARGET_PATH"])
payload = json.loads(p.read_text())
payload["extra"] = json.loads(os.environ["EXTRA_JSON"])
p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
'

# ---------------------------------------------------------------------------
# 8-line operator-facing summary on stdout. Order is fixed per plan spec.
# ---------------------------------------------------------------------------
echo "LIVECLOSE-02 CI-URL recorder"
echo "URL: $URL"
echo "run_id: $RUN_ID"
echo "workflow_path: $WORKFLOW_PATH"
echo "conclusion: $CONCLUSION"
echo "Wrote ci-url.txt: $CI_URL_TXT_PATH"
echo "Wrote evidence: $TARGET_PATH"
echo "Status: AWAITING_HUMAN"

exit 0
