# Phase 07.1 — Deferred Items

Items surfaced during execution of `07.1-01-PLAN.md` that are out-of-scope
for this plan's commits (pre-existing, unrelated to the BUG-1/2/3 fix
surface). Logged per the GSD executor SCOPE BOUNDARY rule.

## Semgrep findings (`docker-compose.unified.yml`) — pre-existing

Surfaced by the PostToolUse `semgrep mcp` scan on 2026-05-14 when adding
`FRONTEND_UPSTREAM` env var to api-gateway block (lines ~283-300). None
of the findings touch the api-gateway block or any line modified by this
plan; all flag long-standing container-hardening warnings on the DB +
ops services that have been in the compose file since project setup.

| Line | Service     | Finding (severity: WARNING)                                                              | CWE                                          |
| ---- | ----------- | ---------------------------------------------------------------------------------------- | -------------------------------------------- |
| 33   | postgres    | Missing `security_opt: no-new-privileges:true` (setuid escalation surface)               | CWE-732 (Incorrect Permission Assignment)    |
| 33   | postgres    | Writable root filesystem; consider `read_only: true` + tmpfs for ephemeral writes        | CWE-732                                      |
| 70   | timescaledb | Same as postgres (no-new-privileges + read_only)                                         | CWE-732                                      |
| 105  | redis       | Same                                                                                     | CWE-732                                      |
| 139  | rabbitmq    | Same                                                                                     | CWE-732                                      |
| 177  | prometheus  | Same                                                                                     | CWE-732                                      |
| 209  | grafana     | Same                                                                                     | CWE-732                                      |
| 784  | (unknown)   | Docker socket exposed to a container via volume (root-equivalent privilege if abused)    | CWE-250 (Execution with Unnecessary Privilege) |

### Why deferred

1. **Scope boundary.** Each finding flags a service unrelated to the
   api-gateway BUG-3 fix. Fixing them here would balloon the diff and
   force a larger compose-level security review (compatibility testing,
   tmpfs sizing for postgres/redis/rabbitmq write paths, etc.).
2. **All pre-existing.** None of the flagged lines were added or
   modified by this plan. Verified by inspecting `git diff` for this
   commit — only lines 288-300 (api-gateway env block) are touched.
3. **Follow-up owner.** Container-hardening sweep belongs in a
   dedicated security plan (Phase 8+), not bundled into a smoke-test
   bugfix plan.

### Recommended follow-up

- Open a security-hardening plan that:
  - Adds `security_opt: ["no-new-privileges:true"]` to every service in
    `docker-compose.unified.yml`.
  - Evaluates `read_only: true` per service + adds tmpfs mounts for
    `/tmp`, `/var/run`, `/var/lib/postgresql/run` (and any other
    runtime-mutable paths the service needs).
  - Audits the Docker socket bind-mount at line ~784 — if the consumer
    is a monitoring agent (cAdvisor / Portainer), consider a
    socket-proxy (e.g. `tecnativa/docker-socket-proxy`) restricting
    the allowed verbs/endpoints to read-only inspection.
- Tag the plan with `requirements: [SEC-NN]` once the requirement IDs
  are minted in `REQUIREMENTS.md`.
