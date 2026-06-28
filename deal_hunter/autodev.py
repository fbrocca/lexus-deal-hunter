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

DEFAULT_BASE_URL = "https://api.auto.dev/listings"
MAX_PAGES = 30  # safety cap on cursor pagination


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

    def _fetch_model(self, search: SearchConfig, model: str) -> List[Mapping]:
        """Fetch all pages for one model.

        We query by only the two confirmed v2 params (`vehicle.make`,
        `vehicle.model`) and apply every other filter client-side. The NX 450h+
        market is small, so this is cheap and avoids returning zero rows from a
        mistyped filter param. Pagination follows the cursor in `links.next`.
        """
        records: List[Mapping] = []
        url: str = self.base_url
        params: Optional[dict] = {"vehicle.make": search.make, "vehicle.model": model}
        for page in range(MAX_PAGES):
            resp = self.session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            if page == 0:
                log.info(
                    "autodev: GET %s params=%s -> HTTP %s",
                    url, params, getattr(resp, "status_code", "?"),
                )
            resp.raise_for_status()
            payload = resp.json()
            batch = payload.get("data") or payload.get("records") or payload.get("listings") or []
            if not batch:
                # Surface why a 200 came back empty so it can be diagnosed from
                # the run log without live access to the API.
                if page == 0 and isinstance(payload, dict):
                    log.warning(
                        "autodev: empty result; payload keys=%s body=%.600s",
                        list(payload.keys()), payload,
                    )
                break
            records.extend(batch)
            nxt = (payload.get("links") or {}).get("next")
            if not nxt:
                break
            # `next` may be a full URL or a bare cursor token.
            if isinstance(nxt, str) and nxt.startswith("http"):
                url, params = nxt, None
            else:
                url = self.base_url
                params = {"vehicle.make": search.make, "vehicle.model": model, "cursor": nxt}
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
