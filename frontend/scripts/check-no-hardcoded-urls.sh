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
# Allowlist rules — applied per match:
#   - File is src/hooks/useGatewayWebSocket.js AND the matched line
#     contains `||` (env-var-with-fallback pattern).
#   - File is src/services/api.js AND the match is inside a comment:
#       * line contains `//` before the match (single-line comment), OR
#       * line number is inside a `/* ... */` block-comment range.
#
# WR-07: the original heuristic accepted any line containing `//` OR
# starting with `*` (after whitespace). That allowed false positives
# (a code line with `//` embedded as an inline comment after a string
# literal got silently allowlisted) and false negatives (a URL on a
# line of a `/* ... */` block that does NOT start with `*` tripped the
# gate). Replace the leading-`*` heuristic with a real block-comment
# state pass (awk) that records the set of line numbers inside
# `/* ... */` ranges. The `//` rule is preserved because it is exact.
#
# The block-comment pass runs once over api.js up-front and exports
# BLOCK_LINES as a space-separated list of line numbers.

api_js_block_lines() {
  # Emit one line number per output line for each source line that lies
  # inside a /* ... */ block in src/services/api.js. Handles nested
  # tokens within a single line correctly: e.g.
  #     /* opens */ code() /* opens again
  # toggles state twice on the line, ending with `inblk=1`. The line on
  # which the open/close tokens appear is also considered inside the
  # block (operator-friendly: a closing `*/` line is part of the
  # comment).
  awk '
    {
      line = $0
      lineno = NR
      had_block_token = 0
      while (1) {
        if (inblk) {
          # Looking for end token.
          p = index(line, "*/")
          if (p == 0) {
            # Whole line is inside the block.
            print lineno
            had_block_token = 1
            break
          }
          # Block ends mid-line; consume and continue scanning.
          print lineno
          had_block_token = 1
          line = substr(line, p + 2)
          inblk = 0
        } else {
          # Looking for open token.
          p = index(line, "/*")
          if (p == 0) break
          # Block opens on this line.
          print lineno
          had_block_token = 1
          line = substr(line, p + 2)
          inblk = 1
        }
      }
    }
  ' "src/services/api.js"
}

BLOCK_LINES=" $(api_js_block_lines | sort -u | tr '\n' ' ')"

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
      # Allow only if (a) the line begins with a `//` single-line
      # comment BEFORE the URL (so the URL is inside a comment, not just
      # part of the URL's scheme), or (b) the line number is inside a
      # `/* ... */` block-comment range computed by the awk pre-pass.
      #
      # The `//` check uses an anchored regex (line starts with
      # optional whitespace then `//`) to avoid the false positive where
      # `grep -q '//'` matched the `//` of `http://localhost:...` and
      # silently allowlisted any code line containing the URL literal.
      if printf '%s' "${content}" | grep -Eq '^[[:space:]]*//'; then
        continue
      fi
      case "${BLOCK_LINES}" in
        *" ${lineno} "*) continue ;;
      esac
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
