"""Ranking + day-over-day price-drop detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import Listing


def rank_cheapest(listings: List[Listing], n: int) -> List[Listing]:
    priced = [l for l in listings if l.price is not None]
    return sorted(priced, key=lambda l: l.price)[:n]


def rank_by_discount(listings: List[Listing], n: int) -> List[Listing]:
    """Biggest absolute discount off MSRP first; ties broken by % off."""
    with_discount = [l for l in listings if l.discount is not None and l.discount > 0]
    return sorted(
        with_discount,
        key=lambda l: (l.discount or 0, l.discount_pct or 0),
        reverse=True,
    )[:n]


@dataclass
class PriceDrop:
    listing: Listing
    old_price: float
    new_price: float

    @property
    def amount(self) -> float:
        return self.old_price - self.new_price

    @property
    def pct(self) -> float:
        return round(100.0 * self.amount / self.old_price, 1) if self.old_price else 0.0


def find_price_drops(
    listings: List[Listing], previous: Dict[str, float]
) -> List[PriceDrop]:
    """Compare today's prices to a {vin: price} snapshot from the last run."""
    drops: List[PriceDrop] = []
    for l in listings:
        if not l.vin or l.price is None:
            continue
        old = previous.get(l.vin)
        if old is not None and l.price < old:
            drops.append(PriceDrop(listing=l, old_price=float(old), new_price=l.price))
    drops.sort(key=lambda d: d.amount, reverse=True)
    return drops


def snapshot(listings: List[Listing]) -> Dict[str, float]:
    """Build a {vin: price} map to persist for next run's comparison."""
    return {l.vin: l.price for l in listings if l.vin and l.price is not None}
