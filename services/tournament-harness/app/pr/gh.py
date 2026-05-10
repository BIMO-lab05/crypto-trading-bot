"""gh CLI subprocess wrapper for `tournament open-pr` (D-11, CD-09, CD-10).

Public API:
  open_draft_pr(*, title, body, head, base="main",
                 labels=("tournament", "evaluation-gate"), dry_run=False) -> str
      Returns the PR URL on success or "(dry-run)" if dry_run=True.

Hard-fail gates:
  _check_gh_installed() — SystemExit(2) if `gh --version` cannot run (CD-09).
  _check_gh_token()     — SystemExit(2) if GH_TOKEN unset (D-11).

Security invariants:
  - Branch name validated against ^[A-Za-z0-9._\\-/]+$ before any subprocess call (T-04-11).
  - GH_TOKEN inherited from env; NEVER appears in argv (T-04-14).
  - GH_TOKEN never written to log messages (T-04-14).
  - subprocess.run invoked with default shell=False (no shell injection surface).
  - The auto-merge command (`gh pr` then `merge` — split here so the literal
    does not appear) MUST NOT appear in this module (CD-10 / T-04-16).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Sequence


logger = logging.getLogger(__name__)

# T-04-11: branch-name validation regex. Allows alphanumerics + . _ - /, refuses
# spaces, "..", and any shell metacharacter. Mirrors the path-traversal guard
# used in app/significance/predict_cache.py and app/leaderboard/snapshot.py.
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._\-/]+$")


def _check_gh_installed() -> None:
    """CD-09: hard-fail with exit 2 if gh is not on PATH or returns non-zero."""
    try:
        subprocess.check_output(["gh", "--version"], stderr=subprocess.STDOUT)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        sys.stderr.write(
            "gh CLI not found on PATH. Install: https://cli.github.com/  "
            f"(underlying error: {e})\n"
        )
        raise SystemExit(2)


def _check_gh_token() -> None:
    """D-11: hard-fail with exit 2 if GH_TOKEN unset."""
    if not os.environ.get("GH_TOKEN"):
        sys.stderr.write(
            "GH_TOKEN env var not set — refusing to invoke gh pr create. "
            "(D-11: missing PR after winning tournament is the worst silent failure.)\n"
        )
        raise SystemExit(2)


def open_draft_pr(
    *,
    title: str,
    body: str,
    head: str,
    base: str = "main",
    labels: Sequence[str] = ("tournament", "evaluation-gate"),
    dry_run: bool = False,
) -> str:
    """Open a draft PR via gh CLI. Returns PR URL on success; '(dry-run)' if dry_run=True.

    Only invokes `gh pr create --draft` — never the auto-merge subcommand (CD-10).
    """
    if not _BRANCH_RE.fullmatch(head) or ".." in head:
        raise ValueError(
            f"invalid branch name {head!r} — must match {_BRANCH_RE.pattern} and not contain '..'"
        )
    cmd = [
        "gh",
        "pr",
        "create",
        "--draft",
        "--title",
        title,
        "--body",
        body,
        "--head",
        head,
        "--base",
        base,
    ]
    for label in labels:
        cmd += ["--label", label]
    if dry_run:
        # Log argv shape; cmd never contains the token by construction.
        logger.info(
            "dry-run gh pr create: argv-len=%d head=%s base=%s", len(cmd), head, base
        )
        return "(dry-run)"

    # Belt-and-suspenders: env hygiene, then invoke.
    _check_gh_installed()
    _check_gh_token()
    # subprocess inherits env (gh reads GH_TOKEN from env). Do NOT pass a custom
    # env that could log the token via str(env) anywhere downstream. shell=False
    # is the default; we pass it explicitly so the test can assert it.
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh pr create failed: rc={result.returncode} stderr={result.stderr.strip()}"
        )
    return result.stdout.strip()


__all__ = [
    "open_draft_pr",
]
