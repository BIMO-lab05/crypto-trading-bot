"""
Pre-commit smoke suite: fast, no external dependencies, no service start.
Goal: catch obvious-broken commits (bad YAML, syntax errors, testnet leaks).
Deeper end-to-end verification belongs in /verify-stack, not here.
"""
import compileall
import io
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _compose_files():
    return sorted(REPO_ROOT.glob("docker-compose*.yml"))


@pytest.mark.smoke
@pytest.mark.parametrize("compose_path", _compose_files(), ids=lambda p: p.name)
def test_compose_file_parses(compose_path: Path):
    with compose_path.open() as f:
        doc = yaml.safe_load(f)
    assert isinstance(doc, dict), f"{compose_path.name} did not parse to a mapping"
    assert "services" in doc, f"{compose_path.name} has no top-level 'services' key"


@pytest.mark.smoke
def test_services_python_syntax():
    """compileall services/ — catches SyntaxError without importing (no dep needed)."""
    services_dir = REPO_ROOT / "services"
    if not services_dir.is_dir():
        pytest.skip("services/ not found")
    buf = io.StringIO()
    ok = compileall.compile_dir(
        str(services_dir),
        quiet=1,
        force=True,
        workers=0,
        rx=__import__("re").compile(r"(__pycache__|\.venv|venv|/tests?/)"),
    )
    assert ok, f"SyntaxError in services/. Output:\n{buf.getvalue()}"


@pytest.mark.smoke
def test_shared_python_syntax():
    shared_dir = REPO_ROOT / "shared"
    if not shared_dir.is_dir():
        pytest.skip("shared/ not found")
    ok = compileall.compile_dir(
        str(shared_dir),
        quiet=1,
        force=True,
        workers=0,
        rx=__import__("re").compile(r"(__pycache__|\.venv|venv|/tests?/)"),
    )
    assert ok, "SyntaxError in shared/"


@pytest.mark.smoke
def test_no_testnet_url_in_root_env_example():
    """Root .env.example must not point to testnet — production templates leak otherwise."""
    env_example = REPO_ROOT / ".env.example"
    if not env_example.is_file():
        pytest.skip(".env.example not found at repo root")
    content = env_example.read_text(errors="ignore").lower()
    forbidden = ["testnet.binance", "api-testnet.bybit", "stream-testnet"]
    hits = [token for token in forbidden if token in content]
    assert not hits, f".env.example contains testnet URLs: {hits}"


@pytest.mark.smoke
def test_pytest_ini_loads():
    """If the root pytest.ini ever breaks, every CI/test run fails — catch it here first."""
    import configparser

    ini = REPO_ROOT / "pytest.ini"
    assert ini.is_file()
    parser = configparser.ConfigParser(strict=False)
    parser.read(ini)
    assert "pytest" in parser.sections()
