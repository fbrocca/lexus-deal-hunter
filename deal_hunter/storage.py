"""Persistence of the {vin: price} snapshot between runs.

The snapshot is committed back to the repo by the workflow so price history
survives across the ephemeral CI runners.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def load_snapshot(path: str | Path) -> Dict[str, float]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, float] = {}
    for vin, price in data.items():
        try:
            out[str(vin)] = float(price)
        except (TypeError, ValueError):
            continue
    return out


def save_snapshot(path: str | Path, snapshot: Dict[str, float]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
