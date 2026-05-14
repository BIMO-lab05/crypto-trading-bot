"""Tournament YAML loader + Cartesian experiment enumerator (D-11, D-12, D-13).

Trust boundary: YAML is operator-supplied. Use yaml.safe_load only (T-03-11);
yaml.load enables arbitrary-code execution via tag deserialisation and is
strictly forbidden by acceptance criteria.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List

import yaml


logger = logging.getLogger(__name__)


VALID_ARCHITECTURES = {"gru", "lstm", "transformer", "tcn"}
SYMBOL_RE = re.compile(
    r"^[A-Z0-9]{2,12}USDT$"
)  # T-03-14 — Bybit-convention quote-pair form

# Top-level YAML required keys.
REQUIRED_TOP_LEVEL = (
    "tournament_id",
    "seed",
    "symbols",
    "intervals",
    "target_modes",
    "architectures",
    "default_resource_caps",
)
DEFAULT_MAX_EXPERIMENTS = 10_000

# HP dimensions every cell must produce (TOURN-03).
COMMON_HP_DIMS = ("units", "dropout", "lr", "batch", "lookback", "horizon")
ARCH_SPECIFIC_DIMS = {
    "gru": (),
    "lstm": (),
    "transformer": ("n_heads", "n_blocks", "ff_dim_multiplier"),
    "tcn": ("kernel_size", "dilation_base", "n_blocks"),
}


@dataclass(frozen=True)
class ExperimentSpec:
    tournament_id: str
    run_id: str
    architecture: str
    symbol: str
    interval: str
    horizon: int
    target_mode: str
    hp: Dict[str, Any]
    hp_hash: str
    experiment_seed: int
    resource_caps: Dict[str, Any]


@dataclass
class TournamentSpec:
    tournament_id: str
    seed: int
    symbols: List[str]
    intervals: List[str]
    target_modes: List[str]
    default_resource_caps: Dict[str, Any]
    max_experiments: int
    architectures: Dict[str, Dict[str, Any]]
    config_yaml: str  # raw bytes for reproducibility (stored on tournaments table)


def _validate_top_level(data: Dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_TOP_LEVEL if k not in data]
    if missing:
        raise ValueError(f"tournament.yaml missing required keys: {missing}")
    if not isinstance(data["seed"], int):
        raise ValueError(f"seed must be int, got {type(data['seed']).__name__}")
    if not isinstance(data["symbols"], list) or not data["symbols"]:
        raise ValueError("symbols must be non-empty list")
    for s in data["symbols"]:
        if not isinstance(s, str) or not SYMBOL_RE.match(s):
            raise ValueError(
                f"Symbol {s!r} must be in Bybit-convention quote-pair form (e.g., 'SOLUSDT'). "
                f"Got {s!r}; must match {SYMBOL_RE.pattern}"
            )
    if not isinstance(data["target_modes"], list) or not data["target_modes"]:
        raise ValueError("target_modes must be non-empty list")
    for tm in data["target_modes"]:
        if tm not in {"price", "log_returns"}:
            raise ValueError(f"invalid target_mode {tm!r}")
    if not isinstance(data["architectures"], dict) or not data["architectures"]:
        raise ValueError("architectures must be non-empty mapping")
    bad_archs = set(data["architectures"]) - VALID_ARCHITECTURES
    if bad_archs:
        raise ValueError(f"unknown architectures: {bad_archs}")


def load_tournament(yaml_path: str | Path) -> TournamentSpec:
    """Load + validate a tournament.yaml. Returns TournamentSpec."""
    path = Path(yaml_path)
    raw = path.read_text()
    data = yaml.safe_load(raw)  # T-03-11: safe_load only
    if not isinstance(data, dict):
        raise ValueError(f"top-level yaml must be mapping, got {type(data).__name__}")
    _validate_top_level(data)

    return TournamentSpec(
        tournament_id=str(data["tournament_id"]),
        seed=int(data["seed"]),
        symbols=list(data["symbols"]),
        intervals=list(data["intervals"]),
        target_modes=list(data["target_modes"]),
        default_resource_caps=dict(data["default_resource_caps"]),
        max_experiments=int(data.get("max_experiments", DEFAULT_MAX_EXPERIMENTS)),
        architectures=dict(data["architectures"]),
        config_yaml=raw,
    )


def _hp_hash(hp_dict: Dict[str, Any]) -> str:
    """Deterministic 16-char hex digest over canonicalised hp dict (D-13)."""
    payload = json.dumps(hp_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _experiment_seed(tournament_seed: int, hp_hash: str) -> int:
    """Deterministic uint32 seed = (tournament_seed + int(hp_hash[:8], 16)) & 0xFFFFFFFF (D-13)."""
    return (tournament_seed + int(hp_hash[:8], 16)) & 0xFFFFFFFF


def _grid_for_architecture(
    arch_name: str, arch_block: Dict[str, Any]
) -> Iterator[Dict[str, Any]]:
    """Yield each hp combo as a dict — Cartesian over the architecture's grid (D-12)."""
    expected = COMMON_HP_DIMS + ARCH_SPECIFIC_DIMS[arch_name]
    missing = [k for k in expected if k not in arch_block]
    if missing:
        raise ValueError(f"architecture {arch_name!r} missing HP dimensions: {missing}")

    # Each value in arch_block is a list of options; build axes in deterministic key order.
    axes_keys = sorted(k for k in arch_block.keys() if k != "resource_caps")
    axes_values = [arch_block[k] for k in axes_keys]
    # Validate each axis is a non-empty list
    for k, v in zip(axes_keys, axes_values):
        if not isinstance(v, list) or not v:
            raise ValueError(
                f"architecture {arch_name!r} HP {k!r} must be non-empty list, got {v!r}"
            )
    for combo in itertools.product(*axes_values):
        yield dict(zip(axes_keys, combo))


def enumerate_experiments(spec: TournamentSpec) -> List[ExperimentSpec]:
    """Full Cartesian enumeration: arch × symbol × interval × target_mode × hp_combo (D-12)."""
    experiments: List[ExperimentSpec] = []
    for arch_name, arch_block in spec.architectures.items():
        per_arch_caps = arch_block.get("resource_caps") or spec.default_resource_caps
        for hp_combo in _grid_for_architecture(arch_name, arch_block):
            for symbol in spec.symbols:
                for interval in spec.intervals:
                    for target_mode in spec.target_modes:
                        # Compute hash over (arch, hp, symbol, interval, target_mode)
                        # so identical hp under different (sym, tm) get distinct rows.
                        full_dict = {
                            "architecture": arch_name,
                            "symbol": symbol,
                            "interval": interval,
                            "target_mode": target_mode,
                            "hp": hp_combo,
                        }
                        hp_hash = _hp_hash(full_dict)
                        exp_seed = _experiment_seed(spec.seed, hp_hash)
                        run_id = (
                            f"{arch_name}_{symbol}_{interval}_{target_mode}_{hp_hash}"
                        )
                        experiments.append(
                            ExperimentSpec(
                                tournament_id=spec.tournament_id,
                                run_id=run_id,
                                architecture=arch_name,
                                symbol=symbol,
                                interval=interval,
                                horizon=int(hp_combo["horizon"]),
                                target_mode=target_mode,
                                hp=dict(hp_combo),
                                hp_hash=hp_hash,
                                experiment_seed=exp_seed,
                                resource_caps=dict(per_arch_caps),
                            )
                        )
    if len(experiments) > spec.max_experiments:
        raise ValueError(
            f"grid produces {len(experiments)} experiments — exceeds "
            f"max_experiments={spec.max_experiments}. Trim YAML or raise max_experiments."
        )
    # Defense: detect duplicate run_ids (would violate leaderboard PK)
    run_ids = [e.run_id for e in experiments]
    if len(set(run_ids)) != len(run_ids):
        dups = [r for r in set(run_ids) if run_ids.count(r) > 1]
        raise RuntimeError(f"duplicate run_id detected: {dups[:5]}")
    return experiments
