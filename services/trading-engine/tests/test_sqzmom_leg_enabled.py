"""
SQZMOM_ENHANCED must vote, and ADX must be categorized.

The leg was commented out of fetch_all_indicators as "stuck at 0.50 HOLD".
That cause was root-caused and fixed 2026-05-05 (indicator_service.py:403-422:
the endpoint read non-prefixed keys and now reads the sqz_-prefixed columns).
The fetcher, its 1.4 metadata weight and its VOLATILITY category all still
exist - only the comment keeps it dark.

ADX votes (since 2026-05-06) but is absent from INDICATOR_CATEGORIES, so
get_indicator_category returns "OTHER" and a lone ADX vote mints its own
category, weakening the min-2-categories diversity gate.

RSI_DIVERGENCE stays disabled: its "stuck at 0.20" cause has no documented fix.
"""

import inspect

from app.aggregation.voter import INDICATOR_CATEGORIES
from app.signal_aggregator import SignalAggregator


def _fetch_entries(source: str, key: str, fetcher: str) -> list[str]:
    """The fetch_all_indicators task-dict entries for one indicator.

    Matched on the fetcher call AND the dict key, never on the bare indicator
    name: other lines inside this same method mention these names in prose -
    the docstring at :719, the log string at :726, and the shadow-mode comment
    at :789-793, which lists RSI_DIVERGENCE and SQZMOM_ENHANCED together. A
    name-only scan trips on that prose and can never go green.
    """
    needle_key = f'"{key}":'
    return [
        line for line in source.splitlines() if needle_key in line and fetcher in line
    ]


def test_sqzmom_enhanced_is_in_the_fetch_set():
    source = inspect.getsource(SignalAggregator.fetch_all_indicators)
    entries = _fetch_entries(source, "SQZMOM_ENHANCED", "fetch_enhanced_sqzmom")

    # Exactly one, or the assertion below is measuring nothing.
    assert len(entries) == 1, f"expected one fetch entry, found {entries!r}"
    assert not entries[0].strip().startswith("#"), (
        "SQZMOM_ENHANCED is still commented out of fetch_all_indicators"
    )


def test_rsi_divergence_stays_disabled():
    """Its disable cause has no documented fix - do not bundle it."""
    source = inspect.getsource(SignalAggregator.fetch_all_indicators)
    entries = _fetch_entries(source, "RSI_DIVERGENCE", "fetch_rsi_divergence")

    assert len(entries) == 1, f"expected one fetch entry, found {entries!r}"
    assert entries[0].strip().startswith("#")


def test_adx_is_categorized_as_trend():
    assert "ADX" in INDICATOR_CATEGORIES["TREND"], (
        "an uncategorized ADX vote counts as its own OTHER category and "
        "weakens the diversity gate"
    )
