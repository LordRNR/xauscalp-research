"""Configuration loading with hard safety ceilings.

Config files may make limits STRICTER, never looser than HARD_LIMITS. Raising a hard
limit requires a code change that is reviewed by the user (see CLAUDE.md).

Loading is strict: in the YAML, the `symbol`, `risk` and `costs` sections must define
EVERY field (no silent defaults), unknown keys are errors, and every number must be a
finite int/float of the right sign. NaN/inf/bools/strings are rejected.
"""

from __future__ import annotations

import math
import os
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

# Absolute ceilings. A config value above any of these is rejected at load time.
HARD_LIMITS = {
    "risk_per_trade_pct": 1.0,
    "daily_loss_limit_pct": 3.0,
    "weekly_loss_limit_pct": 6.0,
    "max_drawdown_pct": 10.0,
    "max_open_positions": 1,
    "max_trades_per_day": 10,
    "max_margin_usage_pct": 50.0,
}

# Sanity bounds for fields without a HARD_LIMIT (audit M2). (min, max), inclusive.
SANITY_BOUNDS = {
    "max_spread_usd": (0.01, 5.0),
    "max_data_age_s": (1.0, 120.0),
    "max_consecutive_errors": (1, 10),
    "expected_slippage_usd": (0.01, 10.0),   # stops DO slip: zero is not allowed
}


class ConfigError(ValueError):
    pass


def _check_number(section: str, name: str, v: Any, *, positive: bool, integer: bool = False):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{section}.{name} must be a number (got {v!r})")
    if not math.isfinite(v):
        raise ConfigError(f"{section}.{name} must be finite (got {v!r})")
    if integer and not float(v).is_integer():
        raise ConfigError(f"{section}.{name} must be an integer (got {v!r})")
    if positive and v <= 0:
        raise ConfigError(f"{section}.{name} must be > 0 (got {v!r})")
    if not positive and v < 0:
        raise ConfigError(f"{section}.{name} must be >= 0 (got {v!r})")


@dataclass(frozen=True)
class SymbolSpec:
    name: str = "XAUUSD"
    contract_size: float = 100.0
    volume_min: float = 0.01
    volume_step: float = 0.01
    volume_max: float = 50.0
    profit_currency: str = "USD"

    def validate(self) -> SymbolSpec:
        """Explicit validation (kept out of __init__ so the RiskManager can be tested
        against a deliberately broken spec and must reject, not crash)."""
        for n in ("contract_size", "volume_min", "volume_step", "volume_max"):
            _check_number("symbol", n, getattr(self, n), positive=True)
        if self.volume_max < self.volume_min:
            raise ConfigError("symbol.volume_max must be >= volume_min")
        if not self.name or not isinstance(self.name, str):
            raise ConfigError("symbol.name must be a non-empty string")
        return self


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.5
    daily_loss_limit_pct: float = 2.0
    weekly_loss_limit_pct: float = 5.0
    max_drawdown_pct: float = 8.0
    max_open_positions: int = 1
    max_trades_per_day: int = 3
    max_spread_usd: float = 0.60
    max_data_age_s: float = 10.0
    max_consecutive_errors: int = 3
    expected_slippage_usd: float = 0.10
    commission_per_lot: float = 0.0
    max_margin_usage_pct: float = 30.0

    _INTEGERS = ("max_open_positions", "max_trades_per_day", "max_consecutive_errors")
    _POSITIVE = ("risk_per_trade_pct", "daily_loss_limit_pct", "weekly_loss_limit_pct",
                 "max_drawdown_pct", "max_spread_usd", "max_data_age_s",
                 "max_margin_usage_pct")

    def __post_init__(self) -> None:
        for f in fields(self):
            _check_number("risk", f.name, getattr(self, f.name),
                          positive=f.name in self._POSITIVE, integer=f.name in self._INTEGERS)
        for k, ceiling in HARD_LIMITS.items():
            v = getattr(self, k)
            if v > ceiling:
                raise ConfigError(f"risk.{k}={v} exceeds hard ceiling {ceiling}")
        for k, (lo, hi) in SANITY_BOUNDS.items():
            v = getattr(self, k)
            if not lo <= v <= hi:
                raise ConfigError(f"risk.{k}={v} outside sanity bounds [{lo}, {hi}]")


@dataclass(frozen=True)
class CostModel:
    extra_spread_usd: float = 0.15
    slippage_usd: float = 0.05
    commission_per_lot_usd: float = 0.0

    def __post_init__(self) -> None:
        for f in fields(self):
            _check_number("costs", f.name, getattr(self, f.name), positive=False)


@dataclass(frozen=True)
class Config:
    mode: str
    symbol: SymbolSpec
    risk: RiskConfig
    costs: CostModel
    account: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    strategy: dict[str, Any] = field(default_factory=dict)


REQUIRED_VALIDATION_KEYS = ("holdout_start", "wf_train_months", "wf_test_months",
                            "min_train_trades", "bootstrap_samples", "random_benchmark_runs",
                            "seed")


def _strict_section(raw: dict, section: str, cls) -> Any:
    data = raw.get(section)
    if not isinstance(data, dict):
        raise ConfigError(f"missing section '{section}'")
    names = {f.name for f in fields(cls) if not f.name.startswith("_")
             and (f.default is not MISSING or f.default_factory is not MISSING)}
    missing, unknown = names - data.keys(), data.keys() - names
    if missing:
        raise ConfigError(f"{section}: missing keys {sorted(missing)} (no silent defaults)")
    if unknown:
        raise ConfigError(f"{section}: unknown keys {sorted(unknown)}")
    return cls(**data)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or os.environ.get("XAU_CONFIG") or ROOT / "config" / "default.yaml")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: not a mapping")
    mode = str(raw.get("mode", "")).upper()
    if mode not in {"RESEARCH", "DEMO", "LIVE"}:
        raise ConfigError(f"unknown or missing mode {mode!r}")
    val = raw.get("validation") or {}
    if missing := [k for k in REQUIRED_VALIDATION_KEYS if k not in val]:
        raise ConfigError(f"validation: missing keys {missing}")
    return Config(
        mode=mode,
        symbol=_strict_section(raw, "symbol", SymbolSpec).validate(),
        risk=_strict_section(raw, "risk", RiskConfig),
        costs=_strict_section(raw, "costs", CostModel),
        account=raw.get("account", {}),
        data=raw.get("data", {}),
        validation=val,
        strategy=raw.get("strategy", {}),
    )
