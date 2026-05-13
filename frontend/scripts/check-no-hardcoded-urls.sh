#!/usr/bin/env bash
#
# check-no-hardcoded-urls.sh — Phase 6, DASH-02 regression gate
#
# Fails if any new `http://localhost` or `ws://localhost` literal appears
# under frontend/src/ outside the two documented dev-config defaults:
#
#   1. frontend/src/hooks/useGatewayWebSocket.js
#      Line containing `||` (the documented dev fallback after the
#      VITE_WS_URL env-var read).
#
#   2. frontend/src/services/api.js
#      Match appearing inside a line comment (`//`) or block comment
#      (a line containing `*` outside a string, which covers both
#      `/*` opening lines and ` *` continuation lines used by JSDoc).
#
# Any other match — a fresh hardcoded URL added to a JS/JSX/TS/TSX
# file — exits non-zero and prints the offending file:line.
#
# Usage:
#   bash frontend/scripts/check-no-hardcoded-urls.sh
#   (or, from frontend/, `npm run check-no-hardcoded-urls`)
#
# Threat model: this gate is a regression guard against accidental
# hardcoding only, not a sandbox (T-06-03-02). A motivated developer
# can concatenate `"http://" + "localhost"` to evade the literal-match
# grep; out of scope.
#
set -euo pipefail

# Resolve frontend/ as the parent of this script's directory.
# Use `python3 -c` rather than `readlink -f` for portability across
# macOS (BSD readlink, no -f) and Linux. Falls back to pwd-based path
# if python3 missing.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${FRONTEND_DIR}"

# Pattern: http://localhost or ws://localhost, anywhere.
PATTERN='http://localhost|ws://localhost'

# Collect raw matches under src/ (no error on zero matches).
RAW_MATCHES="$(grep -rn -E "${PATTERN}" src/ 2>/dev/null || true)"

if [ -z "${RAW_MATCHES}" ]; then
  echo "OK: no undocumented hardcoded URLs (zero matches under src/)"
  exit 0
fi

# Filter out the two allowed defaults.
#
# Allowlist rules — applied per line:
#   - File is src/hooks/useGatewayWebSocket.js AND the matched line
#     contains `||` (env-var-with-fallback pattern).
#   - File is src/services/api.js AND the matched line appears to be
#     inside a comment: either contains `//` before the match or has
#     a leading `*` (block-comment continuation line).
#
# Anything else falls through to the violation list.
VIOLATIONS=""
while IFS= read -r line; do
  # `line` is in `grep -rn` format: `<path>:<lineno>:<content>`.
  path="${line%%:*}"
  rest="${line#*:}"
  lineno="${rest%%:*}"
  content="${line#*:*:}"

  case "${path}" in
    src/hooks/useGatewayWebSocket.js)
      # Allow only if the line contains `||` (the fallback pattern).
      if printf '%s' "${content}" | grep -q '||'; then
        continue
      fi
      ;;
    src/services/api.js)
      # Allow only if the line is inside a comment. JSDoc lines start
      # with `*` after optional leading whitespace; line comments
      # contain `//` before the URL.
      if printf '%s' "${content}" | grep -Eq '^[[:space:]]*\*' \
         || printf '%s' "${content}" | grep -q '//'; then
        continue
      fi
      ;;
  esac

  VIOLATIONS="${VIOLATIONS}${line}
"
done <<EOF
${RAW_MATCHES}
EOF

# Trim trailing newline for accurate empty check.
VIOLATIONS="$(printf '%s' "${VIOLATIONS}")"

if [ -z "${VIOLATIONS}" ]; then
  echo "OK: no undocumented hardcoded URLs (only documented defaults remain)"
  exit 0
fi

echo "FAIL: undocumented hardcoded URL(s):"
printf '%s\n' "${VIOLATIONS}"
exit 1
