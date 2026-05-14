"""Isolation-run profiles for the three Tier-1 opt-in features.

Each profile binds a flag name to:
- env_overrides: env vars for the isolation run (ONE flag on, other two off)
- baseline_env_overrides: env vars for the baseline run (ALL three flags off)
- description: human-readable description (≥40 chars)
- evidence_subdir: directory name under .planning/evidence/forward_paper_test/

The isolation guarantee: only ONE Tier-1 flag is on per run. The other two
are explicitly set to "false" — never inherited from .env. This prevents
cross-contamination of feature effects.

Tier-1 flags (from services/trading-engine/app/config.py):
    enable_vol_targeting  — vol-parity position sizing (T1.2)
    prefer_maker_orders   — PostOnly limit entries for maker fee (T1.3)
    enable_funding_gate   — funding-rate gate for perp entries (T2.3)

Forward-paper-test reference: docs/runbooks/forward-paper-test.md
"""

from __future__ import annotations

TIER1_FLAG_PROFILES: dict[str, dict] = {
    "enable_vol_targeting": {
        "env_overrides": {
            "ENABLE_VOL_TARGETING": "true",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "false",
        },
        "baseline_env_overrides": {
            "ENABLE_VOL_TARGETING": "false",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "false",
        },
        "description": (
            "Per-position vol-parity sizing (T1.2): scales entry size inversely "
            "to realised vol so each position contributes equal expected vol. "
            "Off by default until forward-paper-tested ≥7 days."
        ),
        "evidence_subdir": "enable_vol_targeting",
    },
    "prefer_maker_orders": {
        "env_overrides": {
            "ENABLE_VOL_TARGETING": "false",
            "PREFER_MAKER_ORDERS": "true",
            "ENABLE_FUNDING_GATE": "false",
        },
        "baseline_env_overrides": {
            "ENABLE_VOL_TARGETING": "false",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "false",
        },
        "description": (
            "PostOnly maker limit orders on perp entries (T1.3): harvests the "
            "maker fee (~7 bps round-trip saving vs taker). Falls back to taker "
            "on timeout. Off by default until forward-paper-tested ≥7 days."
        ),
        "evidence_subdir": "prefer_maker_orders",
    },
    "enable_funding_gate": {
        "env_overrides": {
            "ENABLE_VOL_TARGETING": "false",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "true",
        },
        "baseline_env_overrides": {
            "ENABLE_VOL_TARGETING": "false",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "false",
        },
        "description": (
            "Funding-rate gate for perp entries (T2.3): blocks entries when the "
            "current funding rate works against the intended direction by more "
            "than 5 bps/settlement. Fail-open on fetch errors. Off by default."
        ),
        "evidence_subdir": "enable_funding_gate",
    },
}

__all__ = ["TIER1_FLAG_PROFILES"]
