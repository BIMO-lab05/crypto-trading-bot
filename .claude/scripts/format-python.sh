#!/usr/bin/env bash
# PostToolUse hook for Edit/Write: auto-format Python files with ruff.
# Reads tool-call JSON on stdin, formats only when file_path ends in .py.
# Non-blocking — failures are reported via stderr but exit 0 so the
# tool call succeeds (formatting is a polish step, not a correctness gate).

set -uo pipefail

PATH_VAL="$(python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || true)"

# Only act on Python files that exist on disk.
case "$PATH_VAL" in
    *.py) ;;
    *) exit 0 ;;
esac

if [ ! -f "$PATH_VAL" ]; then
    exit 0
fi

RUFF="$HOME/.local/bin/ruff"
if [ ! -x "$RUFF" ]; then
    # Tool not installed — silent no-op.
    exit 0
fi

# Format then auto-fix lint issues. Both are idempotent.
"$RUFF" format --quiet "$PATH_VAL" 2>/dev/null || true
"$RUFF" check --fix --quiet "$PATH_VAL" 2>/dev/null || true

exit 0
