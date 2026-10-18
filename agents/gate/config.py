"""Tenant and model configuration. Model IDs live only in config/models.toml."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load(path: str | Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass(frozen=True)
class SellbyRule:
    version: str
    min_fraction_remaining: float
    min_days_remaining: int
    combine: str = "max"


@dataclass(frozen=True)
class TenantConfig:
    tenant_id: str
    currency: str
    languages: list[str]
    sellby_rule: SellbyRule
    thresholds: dict[str, float]
    margin_floor_pct: dict[str, float]
    policy_version: str
    policy_text: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    elasticity: dict[str, float] = field(default_factory=dict)

    def elasticity_for(self, category: str) -> float:
        """Units uplift per unit of discount fraction (est-v2). Category entry, then `[elasticity] default`,
        then `thresholds.markdown_elasticity`, then 1.0."""
        if category in self.elasticity:
            return float(self.elasticity[category])
        if "default" in self.elasticity:
            return float(self.elasticity["default"])
        return float(self.thresholds.get("markdown_elasticity", 1.0))

    def markdown_setting(self, name: str, default: Any) -> Any:
        """`[markdown]` table of the tenant config: depths_pct, beats_tolerance_inr, beats_tolerance_pct,
        clearance_window_days (0 = exception off), clearance_margin_floor_pct, ramp_days (0 = off)."""
        return (self.raw.get("markdown") or {}).get(name, default)

    def margin_floor(self, category: str) -> float:
        return float(self.margin_floor_pct.get(category, self.margin_floor_pct["default"]))


def load_tenant(path: str | Path | None = None) -> TenantConfig:
    path = Path(path or os.environ.get("TAAL_TENANT_CONFIG", ROOT / "config" / "tenant.demo.toml"))
    d = _load(path)
    s = d["sellby_rule"]
    return TenantConfig(
        tenant_id=d["tenant_id"],
        currency=d["currency"],
        languages=list(d["languages"]),
        sellby_rule=SellbyRule(s["version"], float(s["min_fraction_remaining"]), int(s["min_days_remaining"]), s.get("combine", "max")),
        thresholds={k: float(v) for k, v in d["thresholds"].items()},
        margin_floor_pct={k: float(v) for k, v in d["margin_floor_pct"].items()},
        policy_version=d["policy"]["version"],
        policy_text=d["policy"]["text"],
        raw=d,
        elasticity={k: float(v) for k, v in (d.get("elasticity") or {}).items()},
    )


def load_models(path: str | Path | None = None) -> dict[str, Any]:
    d = _load(path or ROOT / "config" / "models.toml")
    d["backend"] = os.environ.get("TAAL_MODEL_BACKEND", d.get("backend", "stub"))
    return d
