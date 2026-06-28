from deal_hunter.autodev import AutoDevClient, apply_filters
from deal_hunter.config import SearchConfig
from deal_hunter.models import Listing


def _l(model="NX", trim="", condition="New", year=2024, vin="V1", price="50000"):
    return Listing.from_record(
        {
            "vin": vin,
            "model": model,
            "trim": trim,
            "condition": condition,
            "year": year,
            "price": price,
        }
    )


def _search(**kw):
    base = dict(make="Lexus", models=["NX"], keywords=["450h"], condition="new", year_min=2022)
    base.update(kw)
    return SearchConfig(**base)


def test_keyword_isolates_450h_variant():
    listings = [
        _l(trim="450h+ Luxury", vin="A"),   # keep
        _l(trim="350h Premium", vin="B"),   # drop (350h)
        _l(trim="250 Base", vin="C"),       # drop (250)
        _l(model="NX 450h", trim="", vin="D"),  # keep (matches on model)
    ]
    kept = {l.vin for l in apply_filters(listings, _search())}
    assert kept == {"A", "D"}


def test_condition_new_only():
    listings = [
        _l(trim="450h+", condition="New", vin="A"),
        _l(trim="450h+", condition="Used", vin="B"),
    ]
    kept = {l.vin for l in apply_filters(listings, _search())}
    assert kept == {"A"}


def test_year_min_filter():
    listings = [
        _l(trim="450h+", year=2021, vin="A"),
        _l(trim="450h+", year=2024, vin="B"),
    ]
    kept = {l.vin for l in apply_filters(listings, _search(year_min=2022))}
    assert kept == {"B"}


def test_dedup_by_vin():
    listings = [_l(trim="450h+", vin="DUP"), _l(trim="450h+", vin="DUP")]
    assert len(apply_filters(listings, _search())) == 1


def test_empty_keywords_keeps_all_variants():
    listings = [_l(trim="350h", vin="A"), _l(trim="250", vin="B")]
    kept = {l.vin for l in apply_filters(listings, _search(keywords=[]))}
    assert kept == {"A", "B"}


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _row(vin, price):
    return {"vehicle": {"vin": vin, "model": "NX", "trim": "450h+"},
            "retailListing": {"price": price, "condition": "New"}}


class _V1Session:
    """v1 shape: `records` key + totalCount, page-number pagination."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        page = (params or {}).get("page", 1)
        row = _row("A", 53000) if page == 1 else _row("B", 51000)
        return _FakeResp({"records": [row], "totalCount": 2})


class _FallthroughSession:
    """v1 endpoint returns empty; v2 endpoint returns one row of `data`."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        if "api.auto.dev" in url:  # v2
            return _FakeResp({"data": [_row("C", 50000)], "links": {}})
        return _FakeResp({"records": [], "totalCount": 0})  # v1 empty


def test_client_v1_paginates_by_page():
    session = _V1Session()
    client = AutoDevClient(api_key="k", session=session)
    listings = client.search(_search())
    assert {l.vin for l in listings} == {"A", "B"}
    # First strategy (v1) authenticates with the apikey param.
    assert session.calls[0][1]["make"] == "Lexus"
    assert session.calls[0][1]["apikey"] == "k"
    assert session.calls[1][1]["page"] == 2


def test_client_falls_through_to_v2_when_v1_empty():
    session = _FallthroughSession()
    client = AutoDevClient(api_key="k", session=session)
    listings = client.search(_search())
    assert {l.vin for l in listings} == {"C"}
    # It tried v1 first (auto.dev/api/listings), then v2 (api.auto.dev).
    assert "auto.dev/api/listings" in session.calls[0][0]
    assert "api.auto.dev" in session.calls[1][0]
