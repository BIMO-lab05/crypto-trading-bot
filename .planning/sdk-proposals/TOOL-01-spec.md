---
requirement: TOOL-01
phase: 15-planning-tooling-hardening
sdk_target: "~/.claude/get-shit-done/bin/lib/"
upstream_status: "proposal — not yet ported"
gate_pins: "tests/ci/test_no_placeholder_one_liners.py"
---

# TOOL-01 — `plan.validate` SDK verb spec

This document is the authoritative contract for the upstream `plan.validate`
SDK verb implementation. The verb lives outside this repo at the host SDK
path `~/.claude/get-shit-done/bin/lib/` (or, when the SDK is installed via
the build pipeline, at `node_modules/@gsd-build/sdk/dist/`). The repo-side
CI grep gate at `tests/ci/test_no_placeholder_one_liners.py` is the
authoritative enforcement point; this spec pins what the verb must do so the
operator-side pre-commit hook can reject the same shapes locally before they
reach CI.

## Verb contract

Invocation surface:

```
gsd-sdk query plan.validate <path-to-PLAN-or-SUMMARY.md>
```

Canonical implementation path (per the ROADMAP success criterion 1 form):

```
node ./node_modules/@gsd-build/sdk/dist/cli.js query plan.validate <path>
```

Host-install fallback:

```
~/.claude/get-shit-done/bin/cli.js query plan.validate <path>
```

Exit codes:

- `0` — happy path, no banned patterns detected at any candidate one-liner
  position in the input file.
- non-zero — at least one banned pattern fired. The offending pattern name
  is reported in stderr and, when stdout is parsed, returned as part of
  the violations JSON.

Stdout contract:

- Empty on pass.
- JSON-shaped on fail, mirroring the `audit_bybit_bypass.py` violation
  shape used by the repo-side gates:

```json
{
  "violations": [
    {
      "file": "path/relative/to/repo",
      "line": 42,
      "pattern_name": "placeholder_task_n",
      "snippet": "Task 1 -- title"
    }
  ]
}
```

## Banned patterns

The five pattern names lock the spec contract. The repo-side gate
(`tests/ci/test_no_placeholder_one_liners.py::BANNED_PATTERNS`) and the
SDK verb MUST use the same names so violation reports stay portable across
both surfaces.

| Pattern name | Regex source (Python / ERE-equivalent) | Rejects |
|---|---|---|
| `placeholder_rule_n` | `^Rule\s+\d` | One-liners starting with "Rule N" |
| `placeholder_task_n` | `^Task\s+\d` | One-liners starting with "Task N" |
| `placeholder_one_liner_empty` | `^one-liner:\s*$` | Empty `one-liner:` frontmatter key |
| `placeholder_template_token` | `<one-line summary>` | The unfilled GSD template token |
| `placeholder_empty_string` | `^one-liner:\s*""\s*$` | Explicit empty-string frontmatter |

Candidate position contract — patterns run only against the extracted
candidate one-liner text, not arbitrary body / code-block text. The
extractor mirrors `~/.claude/get-shit-done/bin/lib/core.cjs::extractOneLinerFromBody`
lines 200-230:

1. Every frontmatter line matching `^one-liner:`.
2. The first bold-span line (`**...**`) after the first markdown heading
   (`# ...`). The span's inner text is the candidate.
3. If no bold-span is found between heading and body, the first non-empty
   body line after the first heading is the candidate (fallback path).

Bold-span takes precedence over the fallback path when both would qualify.

## File types

The verb name says "plan" per REQUIREMENTS.md TOOL-01 wording, but both
file types under `.planning/phases/**/` are in scope:

- `*-PLAN.md` — the `<objective>` body and any frontmatter `one-liner:`
  key can land with placeholder text on first save.
- `*-SUMMARY.md` — the bold one-liner immediately after the title heading
  is what `summary-extract` reads and feeds into the milestone-close
  auto-text in MILESTONES.md. A placeholder here silently auto-generates
  garbage milestone narrative.

## Pre-commit invocation

The pre-commit hook contract (the installer script ships in Plan 15-04 as
`scripts/install-pre-commit.sh`):

1. Enumerate staged `*-PLAN.md` and `*-SUMMARY.md` files via
   `git diff --cached --name-only --diff-filter=ACM`.
2. For each file, invoke `gsd-sdk query plan.validate <file>`.
3. Fail the commit on first non-zero exit. Print the offending pattern
   name + line snippet so the author can fix in place.

No silent-skip env vars. No `SKIP_PLAN_VALIDATE` or `--no-verify-plans`
escape hatches. The override path is "fix the one-liner" — the placeholder
is never the right answer.

## CI invocation

The repo-side enforcement is the CI grep gate, run as a required PR
check via the Plan 15-04 workflow (`.github/workflows/planning-tooling-gate.yml`):

```
pytest tests/ci/test_no_placeholder_one_liners.py -v
```

The CI gate is the authoritative pin (it scans planning artifacts
directly and is independent of whether the operator has installed the
SDK verb). The verb is the developer-side convenience that catches the
shape earlier, at commit time, before CI fires.

Both surfaces share the same `BANNED_PATTERNS` names so violation
messages are consistent regardless of where the gate catches the issue.

## Unit test contract

The SDK verb's own unit tests MUST cover all 6 cases per REQUIREMENTS.md
TOOL-01 line:

| Case | Input one-liner | Expected exit | Expected pattern_name |
|---|---|---|---|
| Rule N rejection | `Rule 1 -- TDD discipline` | non-zero | `placeholder_rule_n` |
| Task N rejection | `Task 2 -- refactor module X` | non-zero | `placeholder_task_n` |
| Empty one-liner key | `one-liner:` (frontmatter, no value) | non-zero | `placeholder_one_liner_empty` |
| Template token | `<one-line summary>` (unfilled GSD template) | non-zero | `placeholder_template_token` |
| Explicit empty string | `one-liner: ""` (frontmatter) | non-zero | `placeholder_empty_string` |
| Happy path | `Refactor the orderbook fetcher to route through bybit-connector` | `0` | (none) |

Each test must assert both the exit code and the offending pattern_name
appears in stderr / the JSON violations array. The happy-path test must
assert stdout is empty.

## Port path

To port this verb into the host SDK:

1. Add a new module `~/.claude/get-shit-done/bin/lib/plan-validate.cjs`.
2. Register it in the existing
   `~/.claude/get-shit-done/bin/lib/validate-command-router.cjs` dispatcher.
3. Mirror the `BANNED_PATTERNS` dictionary and candidate-extraction logic
   from this spec; reuse `extractOneLinerFromBody` from
   `~/.claude/get-shit-done/bin/lib/core.cjs` (lines 200-230) so the
   extractor stays single-sourced inside the SDK.
4. Wire the CLI dispatcher so `gsd-sdk query plan.validate <path>` routes
   to the new module. The dispatcher returns the JSON violation array on
   the way out so callers (pre-commit, CI parity scripts) can post-process.

## Open questions

Two operator-side decisions remain out of scope for this spec:

- Should the verb gain a `--fix` mode that auto-suggests one-liner
  replacements from the plan's `<objective>` block? Per 15-CONTEXT.md
  Deferred Ideas, auto-fix is out of scope for v1.2. Spec reflects
  rejection-only.
- Should the SDK verb also consume
  `.planning/phases/<phase>/placeholder-allowlist.json` for late-discovered
  false-positives? The repo-side CI gate does (mirroring the Phase 14
  pattern) but the SDK verb spec defaults to ignoring the allowlist — the
  verb is meant to be portable across repos that may not have the GSD
  planning directory structure. Allowlist consumption stays a repo-side
  gate concern only.
