"""Configuration loading.

config.yaml is parsed into a small set of frozen dataclasses so the rest of
the code works with typed attributes instead of dict lookups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass(frozen=True)
class SearchConfig:
    make: str
    models: List[str]
    # Variant filter applied to "<model> <trim>" — keep only listings that
    # mention one of these tokens (case-insensitive). Empty = keep everything.
    keywords: List[str] = field(default_factory=list)
    condition: str = "new"  # new | used | all
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    price_max: Optional[int] = None
    zip_code: Optional[str] = None
    radius_miles: Optional[int] = None


@dataclass(frozen=True)
class ThresholdConfig:
    min_discount_pct: float = 0.0
    max_price: Optional[float] = None


@dataclass(frozen=True)
class EmailConfig:
    subject_prefix: str = "[Deal Hunter]"
    top_n_cheapest: int = 10
    top_n_discount: int = 10


@dataclass(frozen=True)
class StorageConfig:
    snapshot_path: str = "data/snapshot.json"


@dataclass(frozen=True)
class Config:
    search: SearchConfig
    thresholds: ThresholdConfig
    email: EmailConfig
    storage: StorageConfig


def _clean(d: Optional[dict]) -> dict:
    """Drop keys whose value is None so dataclass defaults apply."""
    if not d:
        return {}
    return {k: v for k, v in d.items() if v is not None}


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}

    search_raw = _clean(raw.get("search"))
    if "make" not in search_raw or "models" not in search_raw:
        raise ValueError("config.search must define 'make' and 'models'")

    return Config(
        search=SearchConfig(**search_raw),
        thresholds=ThresholdConfig(**_clean(raw.get("thresholds"))),
        email=EmailConfig(**_clean(raw.get("email"))),
        storage=StorageConfig(**_clean(raw.get("storage"))),
    )
