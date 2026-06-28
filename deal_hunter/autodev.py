"""Auto.dev listings client + filtering.

The client fetches raw records page by page; `apply_filters` enforces the
variant keyword, condition (new/used), and year/price bounds from config.
Filtering is kept separate from fetching so it can be unit-tested without
hitting the network.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Mapping, Optional

import requests

from .config import SearchConfig
from .models import Listing

log = logging.getLogger("deal_hunter.autodev")

DEFAULT_BASE_URL = "https://auto.dev/api/listings"
PAGE_SIZE = 100
MAX_PAGES = 20  # safety cap: 2000 listings is far more than the NX 450h+ market


class AutoDevClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
    ) -> None:
        if not api_key:
            raise ValueError("AUTO_DEV_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()

    def _params(self, search: SearchConfig, model: str, page: int) -> dict:
        params = {
            "apikey": self.api_key,
            "make": search.make,
            "model": model,
            "page": page,
            "limit": PAGE_SIZE,
        }
        if search.year_min is not None:
            params["year_min"] = search.year_min
        if search.year_max is not None:
            params["year_max"] = search.year_max
        if search.price_max is not None:
            params["price_max"] = search.price_max
        if search.zip_code:
            params["zip"] = search.zip_code
        if search.radius_miles is not None:
            params["radius"] = search.radius_miles
        # Auto.dev uses condition=New/Used; omit for "all".
        if search.condition in ("new", "used"):
            params["condition"] = search.condition.capitalize()
        return params

    def _fetch_model(self, search: SearchConfig, model: str) -> List[Mapping]:
        records: List[Mapping] = []
        for page in range(1, MAX_PAGES + 1):
            resp = self.session.get(
                self.base_url,
                params=self._params(search, model, page),
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            batch = payload.get("records") or payload.get("listings") or []
            if not batch:
                break
            records.extend(batch)
            total = payload.get("totalCount") or payload.get("total")
            if total is not None and len(records) >= int(total):
                break
            if len(batch) < PAGE_SIZE:
                break
        log.info("autodev: model=%s returned %d row(s)", model, len(records))
        return records

    def search(self, search: SearchConfig) -> List[Listing]:
        """Fetch every configured model, parse, then filter."""
        raw: List[Mapping] = []
        for model in search.models:
            raw.extend(self._fetch_model(search, model))
        listings = [Listing.from_record(r) for r in raw]
        return apply_filters(listings, search)


def _matches_keywords(listing: Listing, keywords: Iterable[str]) -> bool:
    kws = [k.lower() for k in keywords if k]
    if not kws:
        return True
    hay = f"{listing.model} {listing.trim}".lower()
    return any(k in hay for k in kws)


def apply_filters(listings: Iterable[Listing], search: SearchConfig) -> List[Listing]:
    out: List[Listing] = []
    seen_vins: set[str] = set()
    for l in listings:
        if not _matches_keywords(l, search.keywords):
            continue
        if search.condition in ("new", "used") and l.condition and l.condition != search.condition:
            continue
        if search.year_min is not None and l.year is not None and l.year < search.year_min:
            continue
        if search.year_max is not None and l.year is not None and l.year > search.year_max:
            continue
        if search.price_max is not None and l.price is not None and l.price > search.price_max:
            continue
        # De-dupe by VIN (the same car can appear across pages/dealers).
        if l.vin:
            if l.vin in seen_vins:
                continue
            seen_vins.add(l.vin)
        out.append(l)
    return out
