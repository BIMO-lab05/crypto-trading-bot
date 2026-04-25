#!/usr/bin/env bash
# PreToolUse hook for Write/Edit. Blocks modifications to env/secret files.
# Reads tool-call JSON on stdin, looks at .tool_input.file_path.
# Exit 0 = allow, exit 2 = block.

set -uo pipefail

PATH_VAL="$(python3 -c 'import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || true)"

# Templates and examples are fine.
case "$PATH_VAL" in
    *.env.example|*.env.template|*.env.sample)
        exit 0
        ;;
esac

# Block .env, .env.<anything>, secrets/, credentials/, .aws/, .ssh/, .npmrc.
if printf '%s' "$PATH_VAL" | grep -qE '(^|/)(\.env(\.[^/]*)?$|\.npmrc$|\.netrc$|secrets/|credentials/|\.aws/|\.ssh/)'; then
    printf 'BLOCKED by .claude/scripts/block-secret-writes.sh: refusing to Write/Edit secret file: %s\n' "$PATH_VAL" >&2
    printf 'Edit the file directly outside Claude Code if intentional.\n' >&2
    exit 2
fi

exit 0
