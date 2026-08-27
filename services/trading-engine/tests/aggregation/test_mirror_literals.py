"""P21-7: the mirror-literal cluster must resolve from a declaration, never a literal.

Five sites in the trading-engine hardcoded a number the technical-analysis
service already declares, and one of them re-derived a classification TA
already returns. They agreed with their counterparts only by coincidence:
nothing read one from the other, so a single env override on the TA side
would have moved one number while the engine kept applying the old one, with
nothing in either service able to notice.

Source: `.planning/audits/2026-08-26-ta-signal-path-audit.md` (defect P21-7),
scoped by `.planning/phases/21-ta-aggregator-widening-leakage-net/21-CONTEXT.md`.

The five sites and how each was resolved:

| Site | Resolution |
|---|---|
| `signal_aggregator.fetch_adx` ADX vote gate | `settings.adx_weak_trend_threshold` |
| `sqzmom_strategy_integration` ADX demotion | `settings.adx_weak_trend_threshold` |
| `sqzmom_strategy_integration` volume demotion | `settings.sqzmom_volume_ratio_min` |
| `handlers/signals._fetch_market_regime` | reads TA's own `regime` field |
| `aggregation/market_regime._fetch_adx_data` | omits the TA-owned `period` |

NO THRESHOLD VALUE CHANGED. Every default asserted here equals the literal it
replaced (20.0, 1.2), and the omitted ADX period equals TA's already-declared
`default_adx_period` (14).

The behavioural assertions below are the load-bearing ones. A source grep
proves a literal is gone; it does not prove the setting is wired. Each
converted site therefore also has a test that moves the setting to a
non-default value and asserts the gate moves with it.

Run from `services/trading-engine` with `--no-cov` (see .claude/rules/testing.md).
"""

import annotated_types
import pytest

from app.config import Settings, get_settings


def _bound(field_name: str, kind) -> float | None:
    """Read a declared ge/le off the pydantic Field metadata."""
    for meta in Settings.model_fields[field_name].metadata:
        if isinstance(meta, kind):
            return meta.ge if kind is annotated_types.Ge else meta.le
    return None


# ---------------------------------------------------------------------------
# Task 1 — the two engine-owned mirror fields are declared, bounded, documented
# ---------------------------------------------------------------------------


def test_adx_weak_trend_threshold_defaults_to_the_literal_it_replaced():
    """20.0 is the number lifted out of the two ADX gates. It must not move."""
    assert get_settings().adx_weak_trend_threshold == 20.0, (
        "20.0 was the inline literal in signal_aggregator.fetch_adx and in "
        "sqzmom_strategy_integration's ADX gate. Moving it changes the traded "
        "signal and needs operator approval (21-CONTEXT threshold lock)."
    )


def test_sqzmom_volume_ratio_min_defaults_to_the_literal_it_replaced():
    """1.2 is the number lifted out of the SQZMOM volume gate."""
    assert get_settings().sqzmom_volume_ratio_min == 1.2, (
        "1.2 was the inline literal in sqzmom_strategy_integration's volume "
        "gate. Moving it changes the traded signal and needs operator "
        "approval (21-CONTEXT threshold lock)."
    )


@pytest.mark.parametrize(
    "field_name,ge,le",
    [
        ("adx_weak_trend_threshold", 0.0, 100.0),
        ("sqzmom_volume_ratio_min", 0.0, 10.0),
    ],
)
def test_mirror_field_is_a_bounded_float(field_name, ge, le):
    """An unbounded env override is how a gate silently stops firing.

    ASVS V14: config that reaches a money path is typed and range-checked at
    the declaration, not defensively re-checked at every use site.
    """
    field = Settings.model_fields[field_name]
    assert field.annotation is float, f"{field_name} must be a float Field"
    assert _bound(field_name, annotated_types.Ge) == ge, (
        f"{field_name} lost its ge bound — an override below {ge} would be accepted"
    )
    assert _bound(field_name, annotated_types.Le) == le, (
        f"{field_name} lost its le bound — an override above {le} would be accepted"
    )


@pytest.mark.parametrize(
    "field_name,expected_phrase",
    [
        # Mirrored: the description must name the TA field it must not diverge from.
        ("adx_weak_trend_threshold", "default_adx_weak_trend_threshold"),
        # Engine-owned: the description must say outright that there is no TA field,
        # so a reader does not go hunting for one that does not exist.
        ("sqzmom_volume_ratio_min", "no counterpart"),
    ],
)
def test_mirror_field_description_names_its_ta_counterpart_or_says_there_is_none(
    field_name, expected_phrase
):
    description = Settings.model_fields[field_name].description or ""
    assert expected_phrase in description, (
        f"{field_name}'s description must state its technical-analysis "
        f"counterpart (or that none exists). Expected {expected_phrase!r} in:\n"
        f"{description!r}"
    )
