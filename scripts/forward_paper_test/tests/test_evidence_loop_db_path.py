"""TOURNAMENT_DB_PATH env override for the evidence-loop driver."""

import importlib


def test_db_path_env_override(monkeypatch):
    monkeypatch.setenv("TOURNAMENT_DB_PATH", "/tmp/somewhere/else.db")
    import scripts.forward_paper_test.run_evidence_loop as rel

    importlib.reload(rel)
    assert rel.resolve_db_path() == "/tmp/somewhere/else.db"


def test_db_path_default_without_env(monkeypatch):
    monkeypatch.delenv("TOURNAMENT_DB_PATH", raising=False)
    import scripts.forward_paper_test.run_evidence_loop as rel

    importlib.reload(rel)
    assert rel.resolve_db_path() == rel.DEFAULT_TOURNAMENT_DB_PATH
