#!/usr/bin/env bash
# PreToolUse hook for Bash. If Claude is about to run `git commit ...`, run the
# smoke suite first and block (exit 2) on failure. Reads Claude Code's tool-call
# JSON on stdin and parses .tool_input.command. Same shape as block-dangerous-bash.sh.

set -uo pipefail

CMD="$(python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || true)"

# Only intercept actual `git commit ...` invocations. Allow `git commit-tree`,
# `git --git-dir=... commit` is rare enough to skip; refine later if needed.
if ! [[ "$CMD" =~ (^|[[:space:];&|])git[[:space:]]+commit($|[[:space:]]) ]]; then
    exit 0
fi

# Run smoke suite from repo root (cwd when hook fires). Force the smoke-local
# pytest.ini so the project-wide --cov addopts don't apply.
OUT="$(python3 -m pytest -c tests/smoke/pytest.ini tests/smoke -x --timeout=30 -q 2>&1)"
RC=$?

if [ $RC -ne 0 ]; then
    {
        echo "pre-commit smoke check FAILED — commit blocked."
        echo "Run \`python3 -m pytest -c tests/smoke/pytest.ini tests/smoke -x\` and fix before retrying."
        echo "----- pytest output -----"
        echo "$OUT"
    } >&2
    exit 2
fi

exit 0
