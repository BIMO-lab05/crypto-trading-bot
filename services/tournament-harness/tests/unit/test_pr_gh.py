"""Unit tests for app.pr.gh — gh CLI subprocess wrapper (D-11, CD-09, CD-10, T-04-11/14/16)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest


def _import_gh():
    from app.pr import gh

    return gh


# --- _check_gh_token ---------------------------------------------------------


def test_check_gh_token_missing_exits_2(monkeypatch):
    gh = _import_gh()
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        gh._check_gh_token()
    assert exc.value.code == 2


def test_check_gh_token_present_passes(monkeypatch):
    gh = _import_gh()
    monkeypatch.setenv("GH_TOKEN", "ghs_xxx")
    gh._check_gh_token()  # no exception


# --- _check_gh_installed -----------------------------------------------------


def test_check_gh_installed_missing_exits_2(monkeypatch):
    gh = _import_gh()

    def _raise(*a, **kw):
        raise FileNotFoundError("gh not on PATH")

    monkeypatch.setattr(subprocess, "check_output", _raise)
    with pytest.raises(SystemExit) as exc:
        gh._check_gh_installed()
    assert exc.value.code == 2


def test_check_gh_installed_present_passes(monkeypatch):
    gh = _import_gh()
    monkeypatch.setattr(
        subprocess, "check_output", lambda *a, **kw: b"gh version 2.0.0\n"
    )
    gh._check_gh_installed()  # no exception


# --- open_draft_pr -----------------------------------------------------------


def test_open_draft_pr_argv_correct(monkeypatch):
    gh = _import_gh()
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw

        class R:
            returncode = 0
            stdout = "https://github.com/x/y/pull/1\n"
            stderr = ""

        return R()

    monkeypatch.setenv("GH_TOKEN", "ghs_xxx")
    monkeypatch.setattr(
        subprocess, "check_output", lambda *a, **kw: b"gh version 2.0.0\n"
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    gh.open_draft_pr(
        title="t",
        body="b",
        head="tournament/abc",
        base="main",
        labels=("tournament", "evaluation-gate"),
        dry_run=False,
    )
    cmd = captured["cmd"]
    assert cmd[:4] == ["gh", "pr", "create", "--draft"]
    assert "--title" in cmd
    assert "--body" in cmd
    assert "--head" in cmd
    assert "--base" in cmd
    assert "--label" in cmd


def test_open_draft_pr_no_shell_true(monkeypatch):
    gh = _import_gh()
    captured = {}

    def fake_run(cmd, **kw):
        captured["kw"] = kw

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    monkeypatch.setenv("GH_TOKEN", "ghs_xxx")
    monkeypatch.setattr(
        subprocess, "check_output", lambda *a, **kw: b"gh version 2.0.0\n"
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    gh.open_draft_pr(title="t", body="b", head="tournament/abc")
    assert captured["kw"].get("shell", False) is False


def test_open_draft_pr_dry_run_skips_call(monkeypatch):
    gh = _import_gh()
    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = gh.open_draft_pr(title="t", body="b", head="tournament/abc", dry_run=True)
    assert out == "(dry-run)"
    assert called["n"] == 0


def test_open_draft_pr_branch_regex_validates():
    gh = _import_gh()
    with pytest.raises(ValueError):
        gh.open_draft_pr(title="t", body="b", head="../etc/passwd", dry_run=True)
    with pytest.raises(ValueError):
        gh.open_draft_pr(title="t", body="b", head="branch with spaces", dry_run=True)


def test_gh_token_never_in_argv(monkeypatch):
    gh = _import_gh()
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    token = "ghs_VERY_SECRET_VALUE"
    monkeypatch.setenv("GH_TOKEN", token)
    monkeypatch.setattr(
        subprocess, "check_output", lambda *a, **kw: b"gh version 2.0.0\n"
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    gh.open_draft_pr(title="t", body="b", head="tournament/abc")
    for arg in captured["cmd"]:
        assert token not in str(arg), f"GH_TOKEN leaked into argv: {arg}"


def test_logs_do_not_include_token(monkeypatch, caplog):
    gh = _import_gh()
    token = "ghs_VERY_SECRET_VALUE"
    monkeypatch.setenv("GH_TOKEN", token)
    caplog.set_level(logging.DEBUG)
    out = gh.open_draft_pr(title="t", body="b", head="tournament/abc", dry_run=True)
    assert out == "(dry-run)"
    for record in caplog.records:
        assert token not in record.getMessage()


def test_failure_returncode_raises(monkeypatch):
    gh = _import_gh()

    def fake_run(cmd, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = "rate limited"

        return R()

    monkeypatch.setenv("GH_TOKEN", "ghs_xxx")
    monkeypatch.setattr(
        subprocess, "check_output", lambda *a, **kw: b"gh version 2.0.0\n"
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        gh.open_draft_pr(title="t", body="b", head="tournament/abc")
    assert "rate limited" in str(exc.value)


def test_no_gh_pr_merge_in_module():
    src = Path("services/tournament-harness/app/pr/gh.py").read_text()
    assert "gh pr merge" not in src, "CD-10: gh pr merge MUST NOT appear in pr/gh.py"
