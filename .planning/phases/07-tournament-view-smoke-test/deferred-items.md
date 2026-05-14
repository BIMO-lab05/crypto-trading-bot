## 2026-05-14 — semgrep compose warnings (pre-existing, out of scope for 07-01)

Semgrep flagged the following on `docker-compose.unified.yml` during Plan 07-01 Task 1 edit. All are pre-existing on lines NOT touched by this plan (we only added the `/app/snapshots:ro` bind-mount under `api-gateway.volumes` near line 294). Documented and deferred:

- L33 postgres: no-new-privileges + writable root
- L70 timescaledb: no-new-privileges + writable root
- L105 redis: no-new-privileges + writable root
- L139 rabbitmq: no-new-privileges + writable root
- L177 prometheus: no-new-privileges + writable root
- L209 grafana: no-new-privileges + writable root
- L773 tournament-harness: docker.sock host mount (Phase 3 design; running tournament containers requires Docker socket)

Out of scope for Phase 7 — file deletion test, smoke-test wiring concerns. Track under a Phase 9+ infra-hardening pass.
