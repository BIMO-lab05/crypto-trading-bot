"""Killtest-format verdict docs for the edge battery.

One doc per candidate, same shape as the H3/H4 verdicts in
`.planning/evidence/killtests/`: headline verdict, metrics table, caveats.
`run_battery` owns the measuring; this module owns the rendering, so the
degenerate values Gate 2 legitimately produces are formatted in exactly one
place.

Two of those values need care and get it here rather than at every call site:

- `pooled_pf` is `+inf` when a variant had no losing path-days at all. That
  is a degenerate sample, not infinite profit, so it renders as `inf` and is
  always sat next to `n_trades` in the same row.
- Gate 2 returns NaN across the board when CPCV cannot split the series
  (too few samples). NaN renders as `n/a`, never as `0.0000` — a zero DSR
  and an uncomputable DSR are different claims.

The JSON companion doc runs `json.dumps(..., allow_nan=False)`, so those two
must be converted to sentinels before serialization (`json_safe`). The
alternative — letting `allow_nan` default to True — emits bare `Infinity`
and `NaN` literals, which are not JSON and which every strict parser
rejects. The battery would then fail to record exactly the degenerate
candidates it most needs to record.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from edge_lab.config import (
    CPCV_K_TEST_GROUPS,
    CPCV_N_GROUPS,
    DSR_THRESHOLD,
    HURDLE_MULTIPLE,
    MIN_LISTING_AGE_DAYS,
    MIN_POSITIVE_PATH_FRAC,
    NUM_TRIALS_FLOOR,
    UNIVERSE_TOP_N,
)

# All C(n_groups, k_test_groups) combination-paths — 45 at the pinned 10/2.
TOTAL_CPCV_PATHS = math.comb(CPCV_N_GROUPS, CPCV_K_TEST_GROUPS)

SURVIVORSHIP_CAVEAT = (
    "Survivorship: the universe is today's top-30 by turnover with a ≥2y "
    "listing filter; assets that died before the pin date are absent. This "
    "biases results optimistic by an unmeasured amount."
)

TRIALS_CAVEAT = (
    f"num_trials floor = {NUM_TRIALS_FLOOR}: 8 battery variants + 8 historical "
    "strategy families. DSR is deflated against that floor, not against the "
    "CPCV path count, which would understate the search space actually spent "
    "on this repo."
)

# Obligation carried forward from the Task 3-11 reviews: these qualify every
# verdict in the battery, so every doc carries all of them, each tagged with
# the scope it applies to. A reader holding one doc must not have to know
# which other doc the relevant caveat landed in.
STANDING_CAVEATS = (
    "(xs_momentum) Eligibility requires a bar at the exit Monday, so a symbol "
    "that stops trading mid-week is never entered that week. This is "
    "survivorship-lite and is pinned by design — it is not strictly causal on "
    "eligibility.",
    "(all candidates) Variant warm-up asymmetry: variants of one candidate "
    "are NOT scored over a common window. Each variant's Gate 2 return "
    "series starts at its own first trade and runs to the end of the data, "
    "so a long-lookback variant — which cannot trade until its lookback "
    "fills — is measured on a shorter, later series covering a different "
    "slice of market regime than a short-lookback one. Fewer samples also "
    "widen the DSR standard-error term, so long lookbacks face a marginally "
    "higher bar. Compare variants' verdicts, not their Sharpes. Within a "
    "window, flat days after the first trade are kept at 0.0, so idle "
    "capital is charged rather than skipped.",
    "(funding_carry) Per-symbol funding coverage ends at its own date, which "
    "need not match the candle end-date. The freshness rule then makes the "
    "trade set depend on each feed's end offset. Separately, the entry "
    "threshold assumes 9 settlements (a 3-day minimum hold at 8h cadence) "
    "while realized holds vary — where a hold is shorter than 3 days the "
    "threshold was conservative, i.e. it demanded more edge than the trade "
    "collected.",
    "(Gate 2) DSR is computed on the full return series using a variance "
    "derived from the out-of-sample CPCV path Sharpes. It is therefore not a "
    "pure out-of-sample statistic. CPCV paths also share training data, so "
    "the path Sharpes are correlated trials — mildly anticonservative, the "
    "same direction as the H4 verdict's documented caveat.",
)

_TABLE_HEADER = (
    "| variant | n_trades | gross_edge_bps | cost_bps_taker | ratio_taker | "
    f"gate1 | dsr | pooled_pf | positive_path_frac (of {TOTAL_CPCV_PATHS}) | "
    "n_paths_valid | gate2 |"
)
_TABLE_RULE = "|" + "---|" * 11

_RENDERING_NOTE = (
    f"`n/a` = not computed (the gate never ran) or NaN (CPCV could not split "
    f"the series). `inf` = `pooled_pf` with zero losing path-days — read it "
    f"against `n_trades` in the same row; it is a degenerate sample, not "
    f"infinite profit.\n\n"
    f"`positive_path_frac` is a fraction of **all {TOTAL_CPCV_PATHS} = "
    f"C({CPCV_N_GROUPS}, {CPCV_K_TEST_GROUPS}) combination-paths**. Those "
    f"paths overlap — each sample lands in every combination that does not "
    f"hold its group out — so they are correlated windows, not "
    f"{TOTAL_CPCV_PATHS} independent trials. `n_paths_valid` counts only the "
    f"variance-valid subset kept for the Sharpe distribution. Two different "
    f"denominators: never average or compare them directly."
)


def _is_error(record: Mapping) -> bool:
    return bool(record.get("error"))


def overall_verdict(variants: Sequence[Mapping]) -> str:
    """PASS only when a variant cleared both gates; ERROR wins over both."""
    if any(_is_error(v) for v in variants):
        return "ERROR"
    for v in variants:
        if v.get("gate1_verdict") == "PASS" and v.get("gate2_passed"):
            return "PASS"
    return "REJECT"


def _fmt(value: Any, digits: int = 4) -> str:
    """One formatter for Decimal / float / None, degenerate values included."""
    if value is None:
        return "n/a"
    if isinstance(value, Decimal):
        return f"{value:.{digits}f}"
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return str(value)
    fv = float(value)
    if math.isnan(fv):
        return "n/a"
    if math.isinf(fv):
        return "inf" if fv > 0 else "-inf"
    return f"{fv:.{digits}f}"


def _fmt_gate2(value: Any) -> str:
    return "n/a" if value is None else ("PASS" if value else "FAIL")


def _row(v: Mapping) -> str:
    cells = [
        str(v.get("variant", "?")),
        str(v.get("n_trades", "n/a")),
        _fmt(v.get("gross_edge_bps")),
        _fmt(v.get("cost_bps_taker")),
        _fmt(v.get("ratio_taker"), 3),
        str(v.get("gate1_verdict", "n/a")),
        _fmt(v.get("dsr")),
        _fmt(v.get("pooled_pf")),
        _fmt(v.get("positive_path_frac")),
        str(v.get("n_paths_valid", "n/a")),
        _fmt_gate2(v.get("gate2_passed")),
    ]
    return "| " + " | ".join(cells) + " |"


def _funding_missing(variants: Sequence[Mapping]) -> list[str]:
    missing: set[str] = set()
    for v in variants:
        missing.update(v.get("funding_missing") or ())
    return sorted(missing)


def _caveats(variants: Sequence[Mapping]) -> list[str]:
    lines = [SURVIVORSHIP_CAVEAT, TRIALS_CAVEAT]
    missing = _funding_missing(variants)
    if missing:
        lines.append(
            "Funding EXCLUDED for "
            + ", ".join(missing)
            + " — no funding series was found for those symbols, so every net "
            "figure above is gross of their funding. A missing series is not a "
            "measured zero and must never be quoted as funding-inclusive."
        )
    lines.extend(STANDING_CAVEATS)
    return lines


def _pin_line(universe_pin: Mapping) -> str:
    symbols = universe_pin.get("symbols") or []
    return (
        f"- universe pin: {universe_pin.get('date', 'unknown')} "
        f"(top_n={universe_pin.get('top_n', UNIVERSE_TOP_N)}, "
        f"min_age_days={universe_pin.get('min_age_days', MIN_LISTING_AGE_DAYS)}, "
        f"{len(symbols)} symbols)"
    )


def _gate2_detail(variants: Sequence[Mapping]) -> list[str]:
    lines: list[str] = []
    for v in variants:
        if v.get("dsr") is None and not v.get("gate2_reasons"):
            continue
        lines.append(f"- **{v.get('variant', '?')}**")
        lines.append(
            f"  - return window: {v.get('window_start_iso', 'n/a')} -> "
            f"{v.get('window_end_iso', 'n/a')} "
            f"({v.get('n_samples', 'n/a')} calendar days, flat days included "
            f"at 0.0)"
        )
        lines.append(
            f"  - path Sharpe mean {_fmt(v.get('sharpe_mean'))} / std "
            f"{_fmt(v.get('sharpe_std'))} over {v.get('n_paths_valid', 'n/a')} "
            f"variance-valid paths"
        )
        lines.append(
            f"  - label horizon: {v.get('label_horizon_days', 'n/a')} days "
            f"(CPCV purge/embargo)"
        )
        for reason in v.get("gate2_reasons") or []:
            lines.append(f"  - FAIL: {reason}")
    return lines


def render_verdict(
    candidate: str,
    variants: Sequence[Mapping],
    universe_pin: Mapping,
    sanity_summary: str,
    date_str: str,
) -> str:
    """Killtest-style markdown for one candidate."""
    verdict = overall_verdict(variants)
    scored = [v for v in variants if not _is_error(v)]

    lines = [
        f"# {candidate} verdict: {verdict}",
        "",
        "**Criterion (edge-research-battery design §5, paraphrased; every "
        "threshold below is read live from `edge_lab.config`, not "
        "transcribed):** Gate 1 "
        f"gross edge ≥ {HURDLE_MULTIPLE}× the taker round-trip cost; "
        f"Gate 2 DSR ≥ {DSR_THRESHOLD} deflated at a num_trials floor of "
        f"{NUM_TRIALS_FLOOR}, pooled profit factor > 1.0, and positive net "
        f"expectancy in ≥ {MIN_POSITIVE_PATH_FRAC:.0%} of CPCV paths. A "
        "variant must clear both gates; the candidate passes if any variant "
        "does.",
        "",
        f"- date: {date_str}",
        _pin_line(universe_pin),
        f"- variants scored: {len(scored)}",
        "",
        "## Variants",
        "",
        _TABLE_HEADER,
        _TABLE_RULE,
    ]
    lines.extend(_row(v) for v in scored)
    if not scored:
        lines.append("| _no variant completed_ |" + " |" * 10)
    lines.extend(["", _RENDERING_NOTE, ""])

    detail = _gate2_detail(scored)
    if detail:
        lines.extend(["## Gate 2 detail", ""] + detail + [""])

    lines.extend(
        [
            "## Gate 0 — data sanity",
            "",
            "```",
            sanity_summary or "(no symbols checked)",
            "```",
            "",
            "## Caveats",
            "",
        ]
    )
    lines.extend(f"- {c}" for c in _caveats(variants))

    errors = [v["error"] for v in variants if _is_error(v)]
    if errors:
        lines.extend(["", "## Error", ""])
        for err in errors:
            lines.extend(["```", err.rstrip(), "```", ""])

    return "\n".join(lines).rstrip() + "\n"


def write_verdict(text: str, candidate: str, date_str: str, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{candidate}-verdict-{date_str}.md"
    path.write_text(text, encoding="utf-8")
    return path


def render_summary(
    results: Mapping[str, Mapping],
    universe_pin: Mapping,
    sanity_summary: str,
    date_str: str,
) -> str:
    """One line per candidate + the Gate 0 table, written after all four."""
    lines = [
        f"# Edge research battery summary — {date_str}",
        "",
        _pin_line(universe_pin),
        f"- candidates run: {len(results)}",
        "",
        "## Verdicts",
        "",
        "| candidate | verdict | variants | best ratio_taker | gate1 passes | "
        "gate2 passes |",
        "|---|---|---|---|---|---|",
    ]
    for name, res in results.items():
        variants = [v for v in res.get("variants", ()) if not _is_error(v)]
        ratios = [
            v["ratio_taker"] for v in variants if v.get("ratio_taker") is not None
        ]
        g1 = sum(1 for v in variants if v.get("gate1_verdict") == "PASS")
        g2 = sum(1 for v in variants if v.get("gate2_passed"))
        lines.append(
            f"| {name} | {res.get('verdict', 'n/a')} | {len(variants)} | "
            f"{_fmt(max(ratios), 3) if ratios else 'n/a'} | {g1} | {g2} |"
        )

    lines.extend(
        [
            "",
            "## Gate 0 — data sanity",
            "",
            "```",
            sanity_summary or "(no symbols checked)",
            "```",
            "",
            "## Caveats",
            "",
        ]
    )
    all_variants = [v for res in results.values() for v in res.get("variants", ())]
    lines.extend(f"- {c}" for c in _caveats(all_variants))
    return "\n".join(lines).rstrip() + "\n"


def write_summary(text: str, date_str: str, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"battery-summary-{date_str}.md"
    path.write_text(text, encoding="utf-8")
    return path


def json_safe(obj: Any) -> Any:
    """Recursive walk to a payload `json.dumps(allow_nan=False)` accepts.

    Total by construction rather than field-by-field: Gate 2's degenerate
    branch NaNs every float it returns (sharpe_mean and sharpe_std included),
    and a single missed field raises mid-dump, losing the whole artifact.
    Decimal becomes a string so money keeps its exact scale through the
    round trip.
    """
    if isinstance(obj, Mapping):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        return obj
    return str(obj)


def write_verdict_json(
    candidate: str,
    variants: Sequence[Mapping],
    universe_pin: Mapping,
    date_str: str,
    out_dir: Path,
) -> Path:
    """Machine-readable companion to the markdown verdict."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json_safe(
        {
            "candidate": candidate,
            "date": date_str,
            "verdict": overall_verdict(variants),
            "universe_pin_date": universe_pin.get("date"),
            "universe_n_symbols": len(universe_pin.get("symbols") or []),
            "thresholds": {
                "hurdle_multiple": HURDLE_MULTIPLE,
                "dsr": DSR_THRESHOLD,
                "min_positive_path_frac": MIN_POSITIVE_PATH_FRAC,
                "num_trials_floor": NUM_TRIALS_FLOOR,
                "total_cpcv_paths": TOTAL_CPCV_PATHS,
            },
            "variants": list(variants),
            "caveats": _caveats(variants),
        }
    )
    path = out_dir / f"{candidate}-verdict-{date_str}.json"
    path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return path
