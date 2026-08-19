"""TRADING_SYMBOLS / SYMBOL_ALLOCATIONS must survive the compose → container hop.

Two coupled defects (audit finding 8, 2026-08-12):

  * docker-compose.unified.yml whitelists ~30 env vars for trading-engine and
    neither symbol var was among them; the Dockerfile copies ``app/`` only, so
    the pydantic ``env_file`` fallback is dead in-container. Every operator
    symbol/allocation edit was silently ignored and the engine traded the
    hardcoded defaults.
  * Passing them through as ``${TRADING_SYMBOLS:-}`` injects ``""`` when the
    operator leaves the var unset, and ``EnvSettingsSource`` JSON-decodes
    complex fields BEFORE any validator runs — an empty string raises
    ``SettingsError`` and the container never boots. Blank must mean "use the
    declared default", not "crash", and not "trade an empty symbol list".

Incoherent *non-blank* values must still fail loudly: ``validate_allocations()``
is unchanged and the lifespan calls it at startup.
"""

from pathlib import Path

import pytest
import yaml

from app.config import Settings

# tests/ -> trading-engine/ -> services/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_PATH = _REPO_ROOT / "docker-compose.unified.yml"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_symbol_env_falls_back_to_declared_defaults(monkeypatch, blank):
    """An unset operator var arrives as blank → defaults, no boot crash."""
    monkeypatch.setenv("TRADING_SYMBOLS", blank)
    monkeypatch.setenv("SYMBOL_ALLOCATIONS", blank)

    settings = Settings()

    assert settings.trading_symbols == Settings.model_fields["trading_symbols"].default
    assert (
        settings.symbol_allocations
        == Settings.model_fields["symbol_allocations"].default
    )
    settings.validate_allocations()


def test_blank_init_values_fall_back_to_declared_defaults():
    """Same rule on the init path (direct construction in tests/scripts)."""
    settings = Settings(trading_symbols="", symbol_allocations="")

    assert settings.trading_symbols == Settings.model_fields["trading_symbols"].default
    assert (
        settings.symbol_allocations
        == Settings.model_fields["symbol_allocations"].default
    )


def test_operator_json_env_reaches_settings(monkeypatch):
    """A coherent operator override replaces the defaults outright."""
    monkeypatch.setenv("TRADING_SYMBOLS", '["BTCUSDT","ETHUSDT"]')
    monkeypatch.setenv("SYMBOL_ALLOCATIONS", '{"BTCUSDT": 0.6, "ETHUSDT": 0.4}')

    settings = Settings()

    assert settings.trading_symbols == ["BTCUSDT", "ETHUSDT"]
    assert settings.symbol_allocations == {"BTCUSDT": 0.6, "ETHUSDT": 0.4}
    settings.validate_allocations()


def test_incoherent_operator_symbols_still_fail_boot(monkeypatch):
    """Symbols overridden, allocations left blank → mismatch must raise."""
    monkeypatch.setenv("TRADING_SYMBOLS", '["BTCUSDT","XRPUSDT"]')
    monkeypatch.setenv("SYMBOL_ALLOCATIONS", "")

    settings = Settings()

    with pytest.raises(ValueError, match="XRPUSDT"):
        settings.validate_allocations()


def test_allocations_not_summing_to_one_still_fail_boot(monkeypatch):
    """The sum check is untouched by the blank-value fallback."""
    monkeypatch.setenv("TRADING_SYMBOLS", '["BTCUSDT","ETHUSDT"]')
    monkeypatch.setenv("SYMBOL_ALLOCATIONS", '{"BTCUSDT": 0.6, "ETHUSDT": 0.6}')

    settings = Settings()

    with pytest.raises(ValueError, match="must equal 1.0"):
        settings.validate_allocations()


def test_malformed_symbol_env_still_raises(monkeypatch):
    """Garbage is not silently swallowed into the defaults."""
    monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT")

    with pytest.raises(ValueError):
        Settings()


def test_compose_passes_both_symbol_vars_to_trading_engine():
    """Without these two lines the operator's .env cannot reach the container."""
    compose = yaml.safe_load(_COMPOSE_PATH.read_text())
    env_entries = compose["services"]["trading-engine"]["environment"]
    keys = {entry.split("=", 1)[0] for entry in env_entries}

    assert "TRADING_SYMBOLS" in keys
    assert "SYMBOL_ALLOCATIONS" in keys
