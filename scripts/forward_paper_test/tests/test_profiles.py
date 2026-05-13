"""Tests for profiles.py — TIER1_FLAG_PROFILES definition.

Tests 1 and 2 from the plan's <behavior> block.
"""

import re


def test_tier1_flag_profiles_has_exactly_three_keys():
    """Test 1: TIER1_FLAG_PROFILES exposes exactly three documented flag names."""
    from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

    expected_keys = {
        "enable_vol_targeting",
        "prefer_maker_orders",
        "enable_funding_gate",
    }
    assert set(TIER1_FLAG_PROFILES.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(TIER1_FLAG_PROFILES.keys())}"
    )


def test_tier1_flag_profiles_each_entry_has_required_fields():
    """Test 1b: Each profile entry has env_overrides, baseline_env_overrides, description, evidence_subdir."""
    from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

    required_keys = {
        "env_overrides",
        "baseline_env_overrides",
        "description",
        "evidence_subdir",
    }
    for flag, profile in TIER1_FLAG_PROFILES.items():
        assert set(profile.keys()) >= required_keys, (
            f"Profile for '{flag}' missing keys: {required_keys - set(profile.keys())}"
        )
        assert isinstance(profile["env_overrides"], dict), (
            f"Profile for '{flag}': env_overrides must be a dict"
        )
        assert isinstance(profile["baseline_env_overrides"], dict), (
            f"Profile for '{flag}': baseline_env_overrides must be a dict"
        )
        assert (
            isinstance(profile["description"], str)
            and len(profile["description"]) >= 40
        ), f"Profile for '{flag}': description must be str of ≥40 chars"
        assert re.match(r"^[a-z_]+$", profile["evidence_subdir"]), (
            f"Profile for '{flag}': evidence_subdir must match ^[a-z_]+$, got {profile['evidence_subdir']!r}"
        )


def test_tier1_flag_profiles_isolation_guarantee():
    """Test 2: Each profile's env_overrides sets only its own flag to 'true', other two to 'false'.

    This is the isolation guarantee: only one Tier-1 flag is on per run.
    """
    from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

    all_flags = ["enable_vol_targeting", "prefer_maker_orders", "enable_funding_gate"]

    # Map env-var names to flag names (upper-cased from flag names)
    flag_to_env = {flag: flag.upper() for flag in all_flags}

    for active_flag, profile in TIER1_FLAG_PROFILES.items():
        env = profile["env_overrides"]
        active_env = flag_to_env[active_flag]

        # Active flag must be "true"
        assert env.get(active_env) == "true", (
            f"Profile '{active_flag}': expected {active_env}='true', got {env.get(active_env)!r}"
        )

        # The other two must be "false" — no inheriting from .env
        for other_flag in all_flags:
            if other_flag == active_flag:
                continue
            other_env = flag_to_env[other_flag]
            assert env.get(other_env) == "false", (
                f"Profile '{active_flag}': expected {other_env}='false' (isolation), got {env.get(other_env)!r}"
            )


def test_tier1_flag_profiles_baseline_env_all_false():
    """Test 2b: baseline_env_overrides sets all three flags to 'false'."""
    from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

    all_flag_envs = [
        "ENABLE_VOL_TARGETING",
        "PREFER_MAKER_ORDERS",
        "ENABLE_FUNDING_GATE",
    ]

    for flag, profile in TIER1_FLAG_PROFILES.items():
        baseline = profile["baseline_env_overrides"]
        for env_key in all_flag_envs:
            assert baseline.get(env_key) == "false", (
                f"Profile '{flag}': baseline_env_overrides[{env_key!r}] should be 'false', "
                f"got {baseline.get(env_key)!r}"
            )


def test_tier1_flag_profiles_evidence_subdir_matches_flag_name():
    """Test 2c: evidence_subdir should mirror the flag name."""
    from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

    for flag, profile in TIER1_FLAG_PROFILES.items():
        assert profile["evidence_subdir"] == flag, (
            f"Profile '{flag}': evidence_subdir should match flag name, got {profile['evidence_subdir']!r}"
        )
