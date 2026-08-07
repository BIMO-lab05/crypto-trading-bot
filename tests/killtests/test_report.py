import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.report import latest_verdict, write_verdict  # noqa: E402


def test_write_and_read_roundtrip(tmp_path):
    p = write_verdict(
        "H3",
        "REJECT",
        "stop-out < 40% AND gross expectancy > 0",
        metrics={"stop_out_rate": 0.62, "gross_expectancy": -0.31},
        caveats=["n=13"],
        config={"stop_mult": 1.5},
        input_hashes={"entries": "abc123"},
        out_dir=str(tmp_path),
    )
    assert Path(p).exists() and p.endswith(".md")
    v = latest_verdict("H3", out_dir=str(tmp_path))
    assert v["verdict"] == "REJECT"
    assert v["metrics"]["stop_out_rate"] == 0.62
    assert "n=13" in v["caveats"]


def test_invalid_verdict_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_verdict("H3", "MAYBE", "c", {}, [], {}, {}, out_dir=str(tmp_path))


def test_latest_verdict_none_when_absent(tmp_path):
    assert latest_verdict("H4", out_dir=str(tmp_path)) is None


def test_latest_verdict_can_exclude_a_date(tmp_path):
    """Same-day re-runs overwrite in place, so picking a genuine prior
    baseline means skipping today's file (see h3_atr_replay._vintage_caveats)."""
    import json

    from killtests.report import latest_verdict

    for d in ("20260805", "20260807"):
        (tmp_path / f"H3-verdict-{d}.json").write_text(json.dumps({"date": d}))
    assert latest_verdict("H3", out_dir=str(tmp_path))["date"] == "20260807"
    assert (
        latest_verdict("H3", out_dir=str(tmp_path), exclude_date="20260807")["date"]
        == "20260805"
    )
    assert (
        latest_verdict("H3", out_dir=str(tmp_path), exclude_date="20260805") is not None
    )
