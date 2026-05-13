
## Plan 06-02 — semgrep pre-existing findings (out of scope)

Detected by post-tool semgrep scan during F-04 patch on api-gateway env block.
NONE of these findings live in the api-gateway block (lines 245-310) — they
are pre-existing in untouched compose blocks at:

- line 33 postgres, line 70 timescaledb, line 105 redis, line 139 rabbitmq,
  line 177 prometheus, line 209 grafana — all flag missing `security_opt:
  no-new-privileges:true` + missing `read_only: true`.
- line 768 — `docker.sock` mount exposure (tournament-harness or similar
  test service; not in the safety-state code path).

Out of scope for Plan 06-02 (DASH-03 surface only). Defer to a separate
container-hardening plan; require explicit operator sign-off before adding
read_only flags to stateful DB services (postgres/redis write paths break
without a tmpfs).
