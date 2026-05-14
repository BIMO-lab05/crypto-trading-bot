"""Phase 04 gap-closure regression test.

Inverse of the host-skip gate used by test_open_pr_e2e.py and
test_reproduce_idempotent.py: those tests SKIP on host because the canonical
metric chain is unavailable. This test instead asserts the invariant the
OTHER way — when running inside the tournament-harness container, the
canonical chain MUST resolve. If someone re-introduces a regular-package
`app/__init__.py` and the resolution silently breaks again, this test FAILS
in CI (Plan 04-09 wires it into the container-integration job) instead of
every other test going green-by-skip.

See: .planning/phases/04-tournament-significance-auto-pr/04-UAT.md Test 6.
"""

from __future__ import annotations

import os

import pytest


def _in_tournament_harness_container() -> bool:
    # The image lays both trees side-by-side. Host worktree never has
    # /opt/ml_retraining as an absolute path.
    return os.path.isdir("/app/app") and os.path.isdir("/opt/ml_retraining/app")


pytestmark = pytest.mark.skipif(
    not _in_tournament_harness_container(),
    reason=(
        "canonical-metric resolution invariant only meaningful inside the "
        "tournament-harness container"
    ),
)


def test_canonical_metrics_available_in_container():
    """`_CANONICAL_METRICS_AVAILABLE` MUST be True inside the container.

    Regression guard for 04-UAT.md Test 6: the dual `app/__init__.py`
    collision silently regressed the import chain. The fix (Plan 04-08)
    deletes both regular-package markers and relies on PEP 420 namespace
    packages. If someone re-adds `services/tournament-harness/app/__init__.py`
    or `services/ml-retraining-service/app/__init__.py`, this test fails.
    """
    from app.runner.metrics_bridge import _CANONICAL_METRICS_AVAILABLE

    assert _CANONICAL_METRICS_AVAILABLE is True, (
        "Canonical metric chain unavailable inside the container — "
        "likely cause: a regular-package app/__init__.py was re-introduced "
        "in either services/tournament-harness/app/ or "
        "services/ml-retraining-service/app/. See 04-UAT.md Test 6."
    )


def test_app_is_namespace_package_in_container():
    """`app` must be a PEP 420 namespace package, not a regular package.

    Regular packages have `__file__` pointing at `__init__.py`. Namespace
    packages have `__file__ is None` (or no attribute at all on older
    Pythons). This makes the regression test independent of the canonical
    chain — even if the imports happened to succeed for some other reason,
    the namespace-package invariant must hold.
    """
    import app

    # PEP 420 namespace packages set __file__ to None (3.7+) OR raise AttributeError.
    file_attr = getattr(app, "__file__", None)
    assert file_attr is None, (
        f"`app` is a regular package (has __file__={file_attr!r}); "
        "namespace-package merge with /opt/ml_retraining/app cannot succeed. "
        "Delete services/tournament-harness/app/__init__.py and "
        "services/ml-retraining-service/app/__init__.py."
    )


def test_app_path_includes_both_trees_in_container():
    """`app.__path__` must list BOTH /app/app and /opt/ml_retraining/app."""
    import app

    paths = list(app.__path__)
    assert any("/app/app" in p for p in paths), (
        f"/app/app missing from app.__path__: {paths}"
    )
    assert any("/opt/ml_retraining/app" in p for p in paths), (
        f"/opt/ml_retraining/app missing from app.__path__: {paths}"
    )
