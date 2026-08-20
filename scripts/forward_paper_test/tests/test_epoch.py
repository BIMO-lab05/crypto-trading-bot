"""Clean-data epoch constant — single source for analysis filters."""


def test_epoch_constants_agree():
    from scripts.forward_paper_test.epoch import CLEAN_DATA_EPOCH_ISO, CLEAN_DATA_EPOCH_MS
    from datetime import datetime

    dt = datetime.fromisoformat(CLEAN_DATA_EPOCH_ISO.replace("Z", "+00:00"))
    assert dt.tzinfo is not None
    assert int(dt.timestamp() * 1000) == CLEAN_DATA_EPOCH_MS
    assert CLEAN_DATA_EPOCH_ISO == "2026-08-12T13:47:20Z"
