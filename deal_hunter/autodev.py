"""Auto.dev listings client + filtering.

The client fetches raw records page by page; `apply_filters` enforces the
variant keyword, condition (new/used), and year/price bounds from config.
Filtering is kept separate from fetching so it can be unit-tested without
hitting the network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional

import requests

from .config import SearchConfig
from .models import Listing

log = logging.getLogger("deal_hunter.autodev")

MAX_PAGES = 30  # safety cap on pagination


def _extract_batch(payload) -> list:
    if not isinstance(payload, dict):
        return payload if isinstance(payload, list) else []
    for key in ("data", "records", "listings", "results", "hits"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    return []


@dataclass
class Strategy:
    """One way to talk to Auto.dev. We try each until one returns rows."""

    label: str
    base_url: str
    # Build the first-page query params for a make/model.
    params: Callable[[str, str, str], dict]
    # True if this shape authenticates via Bearer header (vs. apikey param).
    bearer: bool


# Auto.dev has shipped two request shapes. We don't know which a given key is
# provisioned for and can't probe it offline, so we try both and keep the one
# that actually returns listings.
STRATEGIES: List[Strategy] = [
    Strategy(
        label="v1",
        base_url="https://auto.dev/api/listings",
        params=lambda mk, md, key: {"apikey": key, "make": mk, "model": md},
        bearer=True,
    ),
    Strategy(
        label="v2",
        base_url="https://api.auto.dev/listings",
        params=lambda mk, md, key: {"vehicle.make": mk, "vehicle.model": md, "limit": 100},
        bearer=True,
    ),
]


class AutoDevClient:
    def __init__(
        self,
        api_key: str,
        strategies: Optional[List[Strategy]] = None,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
    ) -> None:
        if not api_key:
            raise ValueError("AUTO_DEV_API_KEY is required")
        self.api_key = api_key
        self.strategies = strategies or STRATEGIES
        self.timeout = timeout
        self.session = session or requests.Session()

    def _get(self, url: str, params: Optional[dict], bearer: bool):
        headers = {"Authorization": f"Bearer {self.api_key}"} if bearer else {}
        return self.session.get(url, params=params, headers=headers, timeout=self.timeout)

    def _paginate(self, strategy: Strategy, make: str, model: str, first_payload) -> List[Mapping]:
        """Collect remaining pages after a strategy's first page succeeded."""
        records: List[Mapping] = list(_extract_batch(first_payload))
        payload = first_payload
        page = 1
        while page < MAX_PAGES:
            nxt = (payload.get("links") or {}).get("next") if isinstance(payload, dict) else None
            if nxt:  # cursor-style (v2)
                if isinstance(nxt, str) and nxt.startswith("http"):
                    resp = self._get(nxt, None, strategy.bearer)
                else:
                    p = strategy.params(make, model, self.api_key)
                    p["cursor"] = nxt
                    resp = self._get(strategy.base_url, p, strategy.bearer)
            else:  # page-number style (v1)
                total = payload.get("totalCount") or payload.get("total") if isinstance(payload, dict) else None
                if not total or len(records) >= int(total):
                    break
                p = strategy.params(make, model, self.api_key)
                p["page"] = page + 1
                resp = self._get(strategy.base_url, p, strategy.bearer)
            resp.raise_for_status()
            payload = resp.json()
            batch = _extract_batch(payload)
            if not batch:
                break
            records.extend(batch)
            page += 1
        return records

    def _fetch_model(self, search: SearchConfig, model: str) -> List[Mapping]:
        for strategy in self.strategies:
            params = strategy.params(search.make, model, self.api_key)
            try:
                resp = self._get(strategy.base_url, params, strategy.bearer)
                status = getattr(resp, "status_code", "?")
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # try the next shape rather than aborting
                log.warning("autodev[%s]: %s %s -> %s", strategy.label, strategy.base_url, model, exc)
                continue

            batch = _extract_batch(payload)
            log.info(
                "autodev[%s]: GET %s model=%s -> HTTP %s, %d row(s) on page 1",
                strategy.label, strategy.base_url, model, status, len(batch),
            )
            if not batch:
                if isinstance(payload, dict):
                    log.warning(
                        "autodev[%s]: empty; payload keys=%s body=%.800s",
                        strategy.label, list(payload.keys()), payload,
                    )
                continue

            records = self._paginate(strategy, search.make, model, payload)
            log.info("autodev[%s]: model=%s returned %d row(s) total", strategy.label, model, len(records))
            return records

        log.warning("autodev: no strategy returned rows for model=%s", model)
        return []

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
