#!/usr/bin/env bash
# PreToolUse hook for Bash. Blocks destructive commands by exiting with code 2.
# Reads Claude Code's tool-call JSON on stdin, parses the .tool_input.command,
# and matches against a curated list of patterns. Exit 0 = allow, exit 2 = block.

set -uo pipefail

CMD="$(python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || true)"

# Patterns we never want Claude to run automatically.
# Each line is an extended-regex; matched anywhere in the command string.
PATTERNS='(^|[^[:alnum:]_])rm -rf (/|/[a-z]|/\*|\$HOME|~)(/|$|[^[:alnum:]])
^:\(\)\{
dd if=/dev/(zero|random|urandom) of=/
mkfs(\.|[[:space:]]+/dev/)
chmod 777 /(/|$)
chown -R [^/[:space:]]+ /(/|$)
> ?/dev/sd[a-z]
DROP DATABASE
TRUNCATE DATABASE
git push --force.*(main|master)
git push -f.*(main|master)
git reset --hard origin/(main|master)
shutdown( |$)
reboot( |$)
:set noundo'

# Walk patterns; first match blocks.
while IFS= read -r p; do
    [ -z "$p" ] && continue
    if printf '%s' "$CMD" | grep -qE -- "$p"; then
        printf 'BLOCKED by .claude/scripts/block-dangerous-bash.sh: command matches "%s".\n' "$p" >&2
        printf 'If this is intentional, run it outside Claude Code or temporarily remove the hook.\n' >&2
        exit 2
    fi
done <<<"$PATTERNS"

exit 0
