# Deferred Items — quick task 260816-qjz

Out-of-scope discoveries logged during execution. **Not fixed** per the executor scope boundary
(only auto-fix issues directly caused by the current task's changes).

## Pre-existing test failures in `services/bybit-connector`

Full-suite run: `3 failed, 373 passed, 25 skipped`.

All three were proven pre-existing by reverting both modified `bybit-connector` files to HEAD and
re-running the same three node IDs — they fail identically at clean HEAD, so no regression is
traceable to commit `c774638`.

| Test | Failure | Note |
|---|---|---|
| `tests/test_rest_client_comprehensive.py::TestCoreRequestMethods::test_make_request_success` | `TypeError: BybitRestClient._make_request() got an unexpected keyword argument 'json_data'` | Stale test against a refactored `_make_request` signature. The test passes `json_data=`; the implementation no longer accepts it. Fix is a one-line test update, but it is unrelated to instruments-info. |
| `tests/test_config.py::TestSettingsInitialization::test_settings_default_values` | default-value assertions vs. environment | The test already monkeypatches a list of env vars to defend against cross-service env pollution under full discovery; something outside that list still leaks. |
| `tests/test_main.py::TestErrorHandling::test_validation_exception_handling` | validation-exception handler assertion | Pre-existing. |

## Tooling inconsistency

`pyproject.toml` configures **black and isort at line-length 100** but contains **no `[tool.ruff]`
section**, while the PostToolUse hook `.claude/scripts/format-python.sh` runs
`ruff format` + `ruff check --fix` at ruff's **default 88 columns**.

Consequence: the hook wants to rewrite large fractions of files that are otherwise consistent with
the repo's declared style — measured on this task's targets, 250 lines in
`bybit_rest_client.py`, 198 in `test_rest_client_comprehensive.py`, 6 in `instruments_cache.py`.
Any agent using Edit/Write on those paths produces an enormous cosmetic diff that buries the real
change and risks `--fix` stripping imports.

Suggested resolution (not applied): add a `[tool.ruff]` section pinning `line-length = 100` to
match black/isort, then decide deliberately whether to land a one-time repo-wide format commit.
