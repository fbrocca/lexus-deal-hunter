"""Auto.dev (v2) listings client.

The plug-in hybrid is indexed under ``vehicle.model=NX`` with a powertrain
``vehicle.trim`` (e.g. "450h+ Premium"). So we:
  1. read the trims facet for the make/model,
  2. select every trim whose name contains the configured token ("450h"),
  3. query each trim, new-only and price-sorted, following cursor pages,
  4. parse, de-dupe, and apply the remaining (year/price) filters.

Filtering helpers are kept separate from the network so they unit-test
without hitting the API.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Mapping, Optional

import requests

from .config import SearchConfig
from .models import Listing

log = logging.getLogger("deal_hunter.autodev")

BASE_URL = "https://api.auto.dev/listings"
PAGE_LIMIT = 100
MAX_PAGES = 8  # per trim; PAGE_LIMIT * MAX_PAGES = 800 listings/trim ceiling

_FACET_COUNT_RE = re.compile(r"\s*\(\d[\d,]*\)\s*$")  # strips a trailing " (945)"


def _data(payload) -> list:
    if isinstance(payload, dict):
        for key in ("data", "records", "listings"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


class AutoDevClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        session: Optional[requests.Session] = None,
        timeout: int = 40,
    ) -> None:
        if not api_key:
            raise ValueError("AUTO_DEV_API_KEY is required")
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def _get(self, url: str, params: Optional[dict]):
        resp = self.session.get(url, params=params, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _used_param(self, search: SearchConfig) -> dict:
        if search.condition == "new":
            return {"retailListing.used": "false"}
        if search.condition == "used":
            return {"retailListing.used": "true"}
        return {}

    def discover_trims(self, search: SearchConfig) -> List[str]:
        """Return every trim name for make/model that contains the token."""
        payload = self._get(
            self.base_url,
            {"vehicle.make": search.make, "vehicle.model": search.model,
             "includes": "facets,total", "limit": 1},
        )
        trims = ((payload.get("facets") or {}).get("trims") or {}) if isinstance(payload, dict) else {}
        token = (search.trim_contains or "").lower()
        names = []
        for key in trims:
            name = _FACET_COUNT_RE.sub("", str(key)).strip()
            if not token or token in name.lower():
                names.append(name)
        log.info("autodev: %d trim(s) match %r: %s", len(names), search.trim_contains, names)
        return names

    def _fetch_trim(self, search: SearchConfig, trim: str) -> List[Mapping]:
        params: Optional[dict] = {
            "vehicle.make": search.make,
            "vehicle.model": search.model,
            "vehicle.trim": trim,
            "sort": "retailListing.price",
            "limit": PAGE_LIMIT,
            **self._used_param(search),
        }
        url = self.base_url
        records: List[Mapping] = []
        for _ in range(MAX_PAGES):
            payload = self._get(url, params)
            batch = _data(payload)
            if not batch:
                break
            records.extend(batch)
            nxt = (payload.get("links") or {}).get("next") if isinstance(payload, dict) else None
            if not nxt or not isinstance(nxt, str):
                break
            url, params = nxt, None  # `next` is a full URL
        log.info("autodev: trim=%r -> %d row(s)", trim, len(records))
        return records

    def search(self, search: SearchConfig) -> List[Listing]:
        trims = self.discover_trims(search)
        raw: List[Mapping] = []
        for trim in trims:
            raw.extend(self._fetch_trim(search, trim))
        listings = [Listing.from_record(r) for r in raw]
        if listings:
            s = listings[0]
            log.info("autodev: parsed %d record(s); sample -> %s price=%s msrp=%s condition=%r",
                     len(listings), s.label, s.price, s.msrp, s.condition)
        return apply_filters(listings, search)


def apply_filters(listings: Iterable[Listing], search: SearchConfig) -> List[Listing]:
    """Trim is already selected server-side; enforce the remaining bounds."""
    listings = list(listings)
    out: List[Listing] = []
    seen_vins: set[str] = set()
    dropped = {"condition": 0, "year": 0, "price": 0, "dupe": 0}
    for l in listings:
        if search.condition in ("new", "used") and l.condition and l.condition != search.condition:
            dropped["condition"] += 1
            continue
        if search.year_min is not None and l.year is not None and l.year < search.year_min:
            dropped["year"] += 1
            continue
        if search.year_max is not None and l.year is not None and l.year > search.year_max:
            dropped["year"] += 1
            continue
        if search.price_max is not None and l.price is not None and l.price > search.price_max:
            dropped["price"] += 1
            continue
        if l.vin:
            if l.vin in seen_vins:
                dropped["dupe"] += 1
                continue
            seen_vins.add(l.vin)
        out.append(l)
    log.info("filter funnel: in=%d kept=%d dropped=%s", len(listings), len(out), dropped)
    return out
