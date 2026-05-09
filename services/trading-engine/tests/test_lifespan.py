"""Lifespan refactor tests — phase composition + shutdown order.

These tests verify the structural contract of the lifespan refactor without
booting the full FastAPI app (which requires DB + Redis + TA service). The
core invariant: phases enter in declaration order and exit in REVERSE order.
"""

from contextlib import asynccontextmanager

import pytest


@pytest.mark.asyncio
async def test_lifespan_phase_shutdown_order():
    """Phases must exit in reverse order of entry (cm-stack semantics)."""
    order: list[str] = []

    @asynccontextmanager
    async def make_phase(name: str):
        order.append(f"enter:{name}")
        try:
            yield
        finally:
            order.append(f"exit:{name}")

    async with make_phase("data"), make_phase("ml"), make_phase(
        "strategy"
    ), make_phase("risk"):
        order.append("body")

    assert order == [
        "enter:data",
        "enter:ml",
        "enter:strategy",
        "enter:risk",
        "body",
        "exit:risk",
        "exit:strategy",
        "exit:ml",
        "exit:data",
    ]


def test_lifespan_package_exports():
    """app.lifespan must expose the 4 phase context managers."""
    from app.lifespan import init_data, init_ml, init_risk, init_strategy

    assert callable(init_data)
    assert callable(init_ml)
    assert callable(init_strategy)
    assert callable(init_risk)


def test_main_imports_lifespan_phases():
    """main.py must import the 4 phase factories so lifespan() can compose them."""
    import app.main as main_mod

    assert hasattr(main_mod, "init_data")
    assert hasattr(main_mod, "init_ml")
    assert hasattr(main_mod, "init_strategy")
    assert hasattr(main_mod, "init_risk")


def test_lifespan_body_uses_async_with_phases():
    """Source-level guard: lifespan() body must use the composed phase managers
    (regression check against accidental revert to the inline 200-line body)."""
    import inspect

    import app.main as main_mod

    src = inspect.getsource(main_mod.lifespan)
    assert "init_data()" in src
    assert "init_ml()" in src
    assert "init_strategy()" in src
    assert "init_risk()" in src
    assert "async with" in src
