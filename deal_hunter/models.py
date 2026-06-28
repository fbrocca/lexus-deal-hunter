"""Domain model + tolerant parsing of Auto.dev listing records.

Auto.dev field names have drifted over time and vary by record, so every
accessor tries a list of candidate keys and tolerates strings like
"$53,000", "53000.0", or plain numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

_MONEY_RE = re.compile(r"[^\d.]")


def parse_money(value: Any) -> Optional[float]:
    """Parse "$53,000", "53000", 53000.0 -> 53000.0; junk/empty -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = _MONEY_RE.sub("", str(value))
    if not s or s == ".":
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n > 0 else None


def parse_int(value: Any) -> Optional[int]:
    n = parse_money(value)
    return int(n) if n is not None else None


def _first(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for k in keys:
        if k in record and record[k] not in (None, "", "null"):
            return record[k]
    return None


@dataclass
class Listing:
    vin: str
    year: Optional[int]
    make: str
    model: str
    trim: str
    price: Optional[float]
    msrp: Optional[float]
    mileage: Optional[int]
    condition: str  # "new" | "used" | "" (unknown)
    dealer: str
    city: str
    state: str
    url: str
    photo: str

    @property
    def discount(self) -> Optional[float]:
        if self.price is None or self.msrp is None:
            return None
        d = self.msrp - self.price
        return d if d > 0 else 0.0

    @property
    def discount_pct(self) -> Optional[float]:
        if self.discount is None or not self.msrp:
            return None
        return round(100.0 * self.discount / self.msrp, 1)

    @property
    def label(self) -> str:
        parts = [str(self.year) if self.year else "", self.make, self.model, self.trim]
        return " ".join(p for p in parts if p).strip()

    @classmethod
    def from_record(cls, r: Mapping[str, Any]) -> "Listing":
        raw_condition = str(_first(r, ["condition", "inventoryType", "type"]) or "").lower()
        if "new" in raw_condition:
            condition = "new"
        elif "used" in raw_condition or "cpo" in raw_condition or "certified" in raw_condition:
            condition = "used"
        else:
            condition = ""

        return cls(
            vin=str(_first(r, ["vin", "vinNumber"]) or "").strip().upper(),
            year=parse_int(_first(r, ["year", "modelYear"])),
            make=str(_first(r, ["make", "makeName"]) or "").strip(),
            model=str(_first(r, ["model", "modelName"]) or "").strip(),
            trim=str(_first(r, ["trim", "trimName", "trimLevel"]) or "").strip(),
            price=parse_money(_first(r, ["price", "priceUnformatted", "listPrice", "salePrice"])),
            msrp=parse_money(_first(r, ["msrp", "msrpUnformatted", "priceMsrp", "originalPrice", "retailValue"])),
            mileage=parse_int(_first(r, ["mileage", "miles", "odometer"])),
            condition=condition,
            dealer=str(_first(r, ["dealerName", "dealer", "sellerName"]) or "").strip(),
            city=str(_first(r, ["city", "dealerCity"]) or "").strip(),
            state=str(_first(r, ["state", "dealerState"]) or "").strip(),
            url=str(_first(r, ["clickoffUrl", "vdpUrl", "detailUrl", "url", "link"]) or "").strip(),
            photo=str(_first(r, ["primaryPhotoUrl", "photoUrl", "thumbnail", "image"]) or "").strip(),
        )
