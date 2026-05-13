---
phase: 06-dashboard-audit-safety-state
plan: 03
subsystem: frontend-config
tags:
  - dash-02
  - config-driven-urls
  - regression-gate
  - phase-6
requirements:
  - DASH-02
dependency_graph:
  requires: []
  provides:
    - VITE_WS_URL env-var convention for frontend WebSocket URL
    - VITE_API_BASE_URL documented as the axios baseURL override (no callers
      yet; convention only)
    - grep-gate regression guard for `http://localhost` / `ws://localhost`
      literals under frontend/src/
  affects:
    - frontend/src/hooks/useGatewayWebSocket.js
    - frontend/vite.config.js
    - frontend/package.json
    - frontend/scripts/check-no-hardcoded-urls.sh
tech_stack:
  added: []
  patterns:
    - "env-var with documented fallback (`import.meta.env.X || 'default'`)"
    - "path-scoped allowlist for grep-gate (file path + line content predicate)"
key_files:
  created:
    - frontend/scripts/check-no-hardcoded-urls.sh
  modified:
    - frontend/src/hooks/useGatewayWebSocket.js
    - frontend/vite.config.js
    - frontend/package.json
decisions:
  - "Honored D-16: env-var migration only, no new frontend/src/config.js
     module. Deferred to v2 if more services add direct frontend endpoints."
  - "Grep gate allowlist is path-scoped (file path + per-file line predicate),
     not a universal `is-comment` pass — protects against developers writing
     hardcoded URLs inside arbitrary doc-comments elsewhere in the tree."
  - "Grep-gate script is bash (not Node) to keep the gate runnable outside
     `npm install` state (operator can `bash scripts/check-no-hardcoded-urls.sh`
     directly without a node_modules build)."
metrics:
  completed: 2026-05-13
  duration: ~25min
  tasks_completed: 2
  files_changed: 4
commits:
  - hash: 4f3b3ab
    message: "feat(06-03): migrate WS URL to VITE_WS_URL env var with dev fallback"
  - hash: f98af3b
    message: "feat(06-03): add grep gate for hardcoded localhost URLs in frontend/src"
---

# Phase 6 Plan 03: Config-Driven URLs + Grep Gate Summary

**One-liner:** Migrated the single remaining hardcoded `ws://localhost:8000/ws`
literal to `import.meta.env.VITE_WS_URL` with a documented dev fallback, extended
the `vite.config.js` doc block with the env-var convention, and installed a path-scoped
bash grep-gate (`frontend/scripts/check-no-hardcoded-urls.sh`) wired into npm to
prevent regression. ROADMAP Phase 6 success criterion 3 satisfied.

## Tasks Completed

### Task 1 — Migrate `useGatewayWebSocket.js:34` + extend `vite.config.js` doc block
**Commit:** `4f3b3ab`
**Files:**
- `frontend/src/hooks/useGatewayWebSocket.js` (1-line surgical change)
- `frontend/vite.config.js` (doc-block extension; ~28 new lines)

**Before** (`useGatewayWebSocket.js:34`):
```js
if (import.meta.env.DEV) return 'ws://localhost:8000/ws'
```

**After** (`useGatewayWebSocket.js:34`):
```js
if (import.meta.env.DEV) return import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
```

Production branch (`return ${protocol}//${window.location.host}/ws`) unchanged
— preserves same-origin enforcement per threat T-06-03-01.

**`vite.config.js` extension** — appended a new section `--- ENV VAR CONVENTION
(Phase 6, DASH-02) ---` to the existing dev/prod doc block at lines 16-41,
documenting both `VITE_API_BASE_URL` and `VITE_WS_URL` with defaults, plus the
threat note about prod-branch same-origin enforcement and a pointer to the
grep-gate script as the regression authority. Original block preserved intact.

### Task 2 — Install grep-gate script + wire `package.json`
**Commit:** `f98af3b`
**Files:**
- `frontend/scripts/check-no-hardcoded-urls.sh` (new, executable)
- `frontend/package.json` (added `check-no-hardcoded-urls` script)

**Script behavior** (`frontend/scripts/check-no-hardcoded-urls.sh`):
- `set -euo pipefail`; resolves frontend root from `$BASH_SOURCE` so it works
  regardless of cwd
- Greps `frontend/src/` for `http://localhost|ws://localhost`
- Allowlists per-file with line-content predicates:
  - `src/hooks/useGatewayWebSocket.js` — line must contain `||`
    (the env-fallback pattern)
  - `src/services/api.js` — line must be a comment (either `//` or
    leading-`*` JSDoc continuation)
- Exits 0 with `OK:` on allowlist-only state; exits 1 with `FAIL:` + file:line
  on any violation

**`package.json` addition:**
```json
"check-no-hardcoded-urls": "bash scripts/check-no-hardcoded-urls.sh"
```

## Allowlist of Remaining Grep Matches (Post-Migration)

```
$ grep -rn "http://localhost\|ws://localhost" frontend/src/
frontend/src/hooks/useGatewayWebSocket.js:34:  if (import.meta.env.DEV) return import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
frontend/src/services/api.js:7: * All requests are proxied through Vite to http://localhost:8000 (api-gateway)
```

Both lines are documented dev-config defaults per 06-PATTERNS.md lines 260-262.

## Verification

### Task 1
- `grep -n 'import.meta.env.VITE_WS_URL' frontend/src/hooks/useGatewayWebSocket.js` → 1 match (line 34)
- `grep -c "return 'ws://localhost:8000/ws'$" frontend/src/hooks/useGatewayWebSocket.js` → 0 (bare literal-only return gone)
- `grep -nE "VITE_WS_URL\s*\|\|\s*'ws://localhost:8000/ws'" frontend/src/hooks/useGatewayWebSocket.js` → 1 match (env-with-fallback pattern)
- `grep -c "VITE_API_BASE_URL" frontend/vite.config.js` → 1
- `grep -c "VITE_WS_URL" frontend/vite.config.js` → 2 (one in convention block, one in threat note)
- `grep -c "DASH-02" frontend/vite.config.js` → 1
- `node --check frontend/src/hooks/useGatewayWebSocket.js` → parses
- `node --check frontend/vite.config.js` → parses

### Task 2 (gate behavior)
- **Baseline (post-Task-1):** `bash frontend/scripts/check-no-hardcoded-urls.sh`
  → exit 0, `OK: no undocumented hardcoded URLs (only documented defaults remain)`
- **Negative test 1 (raw URL):** injected `frontend/src/_test_hardcoded.js`
  containing `const x = "http://localhost:8005/foo"` →
  ```
  FAIL: undocumented hardcoded URL(s):
  src/_test_hardcoded.js:1:const x = "http://localhost:8005/foo"
  ```
  exit code 1. Cleaned up.
- **Negative test 2 (URL in comment in non-allowlisted file):** injected
  `frontend/src/_test_comment.js` with `// http://localhost:9999/foo` →
  rejected (exit 1). Confirms allowlist is path-scoped, not universal-comment-pass.
  Cleaned up.
- **npm-script wiring:** `cd frontend && npm run check-no-hardcoded-urls` →
  exit 0 (script invoked through npm successfully).

## Threat Model

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-06-03-01 (Tampering: VITE_WS_URL build-time override) | mitigate | MITIGATED — production branch is unchanged from before this plan; `resolveUrl()` consults `VITE_WS_URL` ONLY inside the `import.meta.env.DEV` branch. The non-DEV path always derives WS URL from `window.location.host`. Build-time-injected hostile env var cannot redirect the prod client. Operator guidance about verifying build target is in the `vite.config.js` doc-block extension. |
| T-06-03-02 (grep gate bypassed via clever encoding) | accept | ACCEPTED — script is a regression guard against accidental hardcoding only. A determined developer can use string concatenation to evade the literal grep. Documented in the script header. |
| T-06-03-03 (VITE_* env vars bundled into client JS) | accept | ACCEPTED — Vite convention; both env vars contain non-secret config values. Documented in the `vite.config.js` doc block. |

## Deviations from Plan

None. Plan executed exactly as written.

The plan's must_haves and authoritative `<verify>` directives all pass. Plan
acceptance criterion line 184 (a draft inline-grep formulation) used a slightly
narrower comment-line regex (`//.*http://localhost`) that does not match the
JSDoc `*`-prefixed continuation line in `frontend/src/services/api.js:7`. My
script's allowlist correctly handles both `//` line comments and ` *` block-comment
continuations, satisfying the plan's `must_haves.truths` (#3 "returns only
documented dev-config defaults") and `<verify><automated>` directive
(`bash frontend/scripts/check-no-hardcoded-urls.sh`). The plan's inline grep
was an alternative formulation, not the load-bearing gate.

## Known Stubs

None.

## Deferred Issues

None.

## Self-Check: PASSED

- File exists: `frontend/scripts/check-no-hardcoded-urls.sh` — FOUND
- File exists: `frontend/src/hooks/useGatewayWebSocket.js` (modified) — FOUND
- File exists: `frontend/vite.config.js` (modified) — FOUND
- File exists: `frontend/package.json` (modified) — FOUND
- Commit `4f3b3ab` — FOUND in `git log`
- Commit `f98af3b` — FOUND in `git log`
- `bash frontend/scripts/check-no-hardcoded-urls.sh` exits 0 with `OK:` baseline message
- `grep -rn "http://localhost\|ws://localhost" frontend/src/` returns only the 2 documented defaults

Plan complete.
