"""Notification-service scheduler package (Plan 09-03 MLGATE-03).

Currently exposes:
- ``ml_gate_digest`` — cross-service fetcher that pulls ML-gate reason counts
  from the trading-engine and forwards them to ``alert_manager.send_daily_summary``.

Pure-asyncio implementation; no apscheduler dependency in v1.1.
"""
