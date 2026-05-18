---
phase: 09
slug: ml-re-enablement-gate
status: blocked
threats_open: 1
asvs_level: 1
created: 2026-05-18
---

# Phase 09 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
>
> **STATUS: BLOCKED — 1 of 22 threats OPEN (T-09-03-05).** Phase advancement gated until the declared admin guard on `/daily-summary` is implemented (or risk explicitly accepted in the Accepted Risks Log).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Operator shell → `run_evidence_loop.py` driver | Operator-controlled env (TRADING_MODE, PAPER_TRADING_MODE); driver UPDATEs only `psr_ci_published`. | sqlite db column writes |
| `run_evidence_loop.py` → tournament-harness sqlite db | Single-process file-backed db; driver READS skill metrics, WRITES only the `psr_ci_published` flag. | sqlite UPDATE |
| `--returns-source` test fixture → driver | Developer-only JSON path; production reads from `.planning/evidence/forward_paper_test/<flag>/<run_id>/run.json`. | JSON test convenience |
| Trading-engine startup → leaderboard sqlite | SELECT-only (`check_dsr_evidence`); mutates `os.environ` based on read result. | DB read |
| Trading-engine → `/run/mlgate_auto_flip.json` | Non-secret marker file; readable by all processes in container. | marker JSON (DSR public-grade) |
| Trading-engine in-process reason cache | Module-level `_current_reason`; single writer (lifespan), many readers (signal aggregator). | in-process string |
| Trading-engine → notification-service | NEW unauthenticated read-only `GET /api/preflight/ml-gate-reason-counts`. | reason counts (max 5 keys) |
| Notification-service `/daily-summary` POST → Telegram | Existing route; expanded with `ml_gate_reason_counts` kwarg. **No admin guard — see T-09-03-05.** | digest payload |
| CI grep gates → production code | Read-only static scans; no execution. | none |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status | Evidence |
|-----------|----------|-----------|-------------|------------|--------|----------|
| T-09-01-01 | Tampering | Forged DSR row via driver | accept | Driver only UPDATEs `psr_ci_published`; never INSERTs/modifies skill metrics. | closed | `scripts/forward_paper_test/run_evidence_loop.py:320` UPDATE-only; no INSERT/DELETE. `run_date` SELECT-only (lines 205-210). |
| T-09-01-02 | Tampering | Forged `run_date` to bypass 7-day accrual | mitigate | `run_date` is leaderboard-written by tournament-harness; driver READS only, applies 7-day rule against injectable `now`. | closed | `run_evidence_loop.py:159` injectable `now`; default at 188-189; staleness compares against clock at 256. |
| T-09-01-03 | Information Disclosure | sqlite3.Error leaks filesystem paths via log | mitigate | Mirror `services/trading-engine/app/preflight/checks.py:246-251` — log emits `type(e).__name__` only. | closed | 5 error-path sites at `run_evidence_loop.py:219, 248, 308, 333, 428` all `type(e).__name__`; zero `{e}`/`str(e)` interpolations. |
| T-09-01-04 | Denial of Service | Long-running PSR-CI bootstrap blocks operator shell | accept | Operator-synchronous; no daemon mode; `--dry-run` shortcut. | closed | Documented in plan + driver CLI. |
| T-09-01-05 | Elevation of Privilege | Driver invoked under TRADING_MODE=LIVE publishes evidence gating LIVE | mitigate | `_check_paper_mode_precondition` refuses LIVE with exit 1 + stderr message. | closed | `run_evidence_loop.py:78-98`; LIVE check at 90; `sys.exit(1)` at 98. |
| T-09-01-06 | Spoofing | Fake `returns_source` JSON flips a row | accept | Developer-only test convenience; production resolves under `.planning/evidence/forward_paper_test/`. | closed | Documented in plan + CLI help. |
| T-09-02-01 | Tampering | Forged DSR row to enable ML auto-flip | mitigate | Leaderboard writes go through tournament-harness only; this code path READS, writes only marker file. | closed | `services/trading-engine/app/lifespan/ml.py` contains zero INSERT/UPDATE against leaderboard. `check_dsr_evidence` issues SELECT-only (`preflight/checks.py:281-291`). |
| T-09-02-02 | Tampering | Future-dated `run_date` to bypass 14-day staleness | mitigate | `run_date` written by tournament-harness; this code applies staleness against injectable `now_utc`. | closed | `_DSR_EVIDENCE_STALENESS_DAYS = 14` at `checks.py:65`; injectable `now` at 224; `ORDER BY run_date DESC` at 289. |
| T-09-02-03 | Repudiation | Operator silently removes `MLGATE_AUTO_FLIP` log to avoid audit | mitigate | CI grep gate `test_mlgate_auto_flip_log_exists` blocks merge if literal removed from `lifespan/ml.py`. | closed | `tests/integration/test_mlgate_grep_gates.py:68`; scope locked to `services/trading-engine/app/`; dual-form scan (pathlib rglob + subprocess grep). |
| T-09-02-04 | Information Disclosure | Marker file leaks DSR value to unauthenticated readers | accept | DSR value already public via `/api/preflight/live-readiness` (Phase 8 D-09). | closed | Documented in plan. |
| T-09-02-05 | Denial of Service | Marker write fails on read-only mount and crashes boot | mitigate | Write wrapped in try/except OSError; logs warning and continues. | closed | `lifespan/ml.py:184-196`; test `test_auto_flip_marker_write_failure_does_not_raise` at `test_ml_gate_auto_flip.py:312`. |
| T-09-02-06 | Elevation of Privilege | Auto-flip enables ML in LIVE mode where it should not | accept | Gate is `dsr > 0.95 AND psr_ci_published=1 AND run_date within 14d`; same evidence floor as LIVE-readiness gate; Phase 8 PREFLIGHT-02 still gates LIVE with cap-check. | closed | Documented in plan. |
| T-09-02-07 | Denial of Service | `set_current_reason()` raises and crashes boot | mitigate | Best-effort contract: try/except Exception; failure logs warning and continues. | closed | `lifespan/ml.py:211-214`; test `test_auto_flip_does_not_crash_when_set_current_reason_raises` at `test_ml_gate_auto_flip.py:425`. |
| T-09-03-01 | Tampering | Reason-enum drift (new emission site adds string outside enum) | mitigate | `log_ml_disabled` raises ValueError if `reason not in ML_GATE_REASONS`; unit test enforces; CI grep gate catches direct `logger.info` bypass. | closed | `ml_gate_reasons.py:99-100` (also 131-132, 149-150); test `test_log_ml_disabled_rejects_unknown_reason` at `test_ml_gate_reasons.py:56`. |
| T-09-03-02 | Information Disclosure | Log emissions leak symbol/interval | accept | Symbol + interval public (mainnet ticker); no secrets/PII. | closed | Documented in plan. |
| T-09-03-03 | Denial of Service | Per-cycle emission floods log subsystem | accept | ≥30s cadence; 5 symbols × 1/30s ≈ 10 lines/min. | closed | Documented in plan. |
| T-09-03-04 | Tampering | Notification-service kwarg duplicates reason-order tuple, allowing drift | mitigate | Duplication intentional (decoupling); CI grep gate anchors canonical enum; unit test enforces canonical order on notification-service side. | closed | `test_mlgate_reason_field_present` at `test_mlgate_reason_grep_gate.py:70`; `test_digest_message_reason_order_is_canonical` at `test_daily_digest_ml_gate.py:94`. |
| **T-09-03-05** | **Spoofing** | **Operator passes forged `ml_gate_reason_counts` to `/daily-summary`** | **mitigate** | **Sub-(a) `/daily-summary` admin-guarded; Sub-(b) scheduled fetcher uses canonical `/api/preflight/ml-gate-reason-counts` path, not the operator-facing kwarg.** | **OPEN** | **Sub-(b) CLOSED — scheduler fetches `/api/preflight/ml-gate-reason-counts` at `ml_gate_digest.py:39`. Sub-(a) ABSENT — `services/notification-service/app/routers/alerts.py:445-480` has no `Depends(get_current_admin_user)`; router declared at line 34 with no `dependencies=`. Notification-service has no admin auth mechanism. Port 8006 exposed directly in `docker-compose.unified.yml:664`, bypassing api-gateway. Any reachable process can POST forged `ml_gate_reason_counts` to trigger a forged Telegram digest. Pre-Phase-9 baseline (`7e2c27e`) was also unguarded — Phase 9 did not introduce the gap but inherited it; the threat register asserted the guard would be present, and it never was.** |
| T-09-03-06 | Repudiation | Operator removes `log_ml_disabled` call to hide emission | mitigate | CI grep gate scans for literal `"ML predictions disabled"` in `services/trading-engine/app/`. | closed | `test_mlgate_reason_field_present` at `test_mlgate_reason_grep_gate.py:70`. |
| T-09-03-07 | Information Disclosure | NEW endpoint leaks reason counts to unauthenticated readers | accept | Reason counts public-grade observability — same disclosure level as Phase 8 `/api/preflight/live-readiness`. | closed | Documented in plan. |
| T-09-03-08 | Denial of Service | NEW scheduled fetcher hangs on slow trading-engine | mitigate | `httpx.AsyncClient(timeout=5.0)`; graceful degradation with `ml_gate_reason_counts=None` on timeout/non-200. | closed | `_FETCH_TIMEOUT_SECONDS = 5.0` at `ml_gate_digest.py:38`; applied at line 65; tests `test_scheduler_handles_trading_engine_unreachable` (line 81) and `test_scheduler_handles_non_200_response` (line 106). |
| T-09-03-09 | Tampering | NEW endpoint mutated to return forged counts | mitigate | Returns `snapshot_reasons()` directly — read-only view; no write surface. | closed | Handler at `handlers/ml_gate_reasons.py:28` is GET-only; zero POST/PUT/DELETE/PATCH routes. |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|

*Eight `accept`-disposition threats above (T-09-01-01, T-09-01-04, T-09-01-06, T-09-02-04, T-09-02-06, T-09-03-02, T-09-03-03, T-09-03-07) are accepted-in-register with rationales recorded in the PLAN.md threat models. No additional risks accepted in this audit pass — T-09-03-05 is NOT accepted; it is BLOCKED awaiting remediation.*

---

## Open Threats — Remediation

### T-09-03-05 — `/daily-summary` admin guard absent

**Disposition:** mitigate (declared in plan).
**Status:** OPEN — declared mitigation absent from implementation.

**Gap:**
- `services/notification-service/app/routers/alerts.py:445-480` defines `POST /daily-summary` accepting `ml_gate_reason_counts` kwarg.
- Route has no `Depends(get_current_admin_user)` or equivalent auth dependency.
- Router declaration at line 34 has no router-level `dependencies=` parameter.
- Notification-service has no admin authentication mechanism anywhere in its codebase.
- Port 8006 is exposed directly in `docker-compose.unified.yml:664`, bypassing api-gateway auth.
- **Impact:** Any process reachable on port 8006 can POST forged `ml_gate_reason_counts` to trigger a misleading Telegram digest.

**Note on origin:** Pre-Phase-9 baseline (`7e2c27e`) was also unguarded — Phase 9 did not introduce the gap. The threat register authored at plan time asserted the guard would be present; it never was. This is an inherited gap surfaced by the audit, not a regression caused by Phase 9 code.

**Remediation options (operator decision required):**

1. **Implement admin guard.** Add admin auth dependency to `/daily-summary` (or all of notification-service `/api/v1/alerts/*`). Mirror api-gateway's `get_current_admin_user` pattern. Reference: `services/api-gateway/app/auth/dependencies.py`. Estimated work: small (1 file + tests + auth wiring through env/secret). Re-run `/gsd-secure-phase 09` after implementation.

2. **Accept the risk explicitly.** Document in Accepted Risks Log above with rationale: e.g., "Notification-service port 8006 is bound to localhost-only / private docker network; no external reachability; forged digest impact bounded to misleading operator UX, no money/data loss." Operator signs the row with date. Then re-run `/gsd-secure-phase 09` to re-classify as closed-by-acceptance.

3. **Tighten network exposure.** Remove `${NOTIFICATION_PORT:-8006}:8006` host-port mapping from `docker-compose.unified.yml:664`; require the notification-service to be reachable only via api-gateway (which already enforces admin auth on its proxied surface). This converts T-09-03-05 from "spoofing" to "internal-only request"; document the new network boundary as an accepted risk and re-run.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-18 | 22 | 21 | 1 | gsd-security-auditor (sonnet, balanced) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [ ] Accepted risks documented in Accepted Risks Log — *N/A for T-09-03-05 unless operator accepts*
- [ ] `threats_open: 0` confirmed — **currently `threats_open: 1`**
- [ ] `status: verified` set in frontmatter — **currently `status: blocked`**

**Approval:** pending — phase advancement BLOCKED until T-09-03-05 is closed (by mitigation, acceptance, or scope reduction). Re-run `/gsd-secure-phase 09` after remediation.
