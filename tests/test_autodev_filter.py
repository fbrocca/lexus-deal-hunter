from deal_hunter.autodev import AutoDevClient, apply_filters
from deal_hunter.config import SearchConfig
from deal_hunter.models import Listing


def _row(vin, price, msrp, year=2026, used=False, trim="450h+ Premium"):
    return {
        "vin": vin,
        "vehicle": {"vin": vin, "make": "Lexus", "model": "NX", "trim": trim,
                    "year": year, "baseMsrp": msrp},
        "retailListing": {"price": price, "used": used, "dealer": "D",
                          "city": "X", "state": "CA", "vdp": "http://d/" + vin},
    }


def _search(**kw):
    base = dict(make="Lexus", model="NX", trim_contains="450h", condition="new", year_min=2022)
    base.update(kw)
    return SearchConfig(**base)


# ----- apply_filters --------------------------------------------------------

def test_apply_filters_condition_year_price_dedupe():
    listings = [
        Listing.from_record(_row("A", 55999, 57810, 2026, False)),  # keep
        Listing.from_record(_row("B", 50000, 57810, 2026, True)),   # drop: used
        Listing.from_record(_row("C", 55000, 57810, 2021, False)),  # drop: year
        Listing.from_record(_row("D", 90000, 95000, 2026, False)),  # drop: price
        Listing.from_record(_row("A", 55999, 57810, 2026, False)),  # drop: dupe vin
    ]
    out = apply_filters(listings, _search(price_max=80000))
    assert {l.vin for l in out} == {"A"}


def test_apply_filters_all_condition_keeps_used():
    listings = [Listing.from_record(_row("B", 50000, 57810, 2026, True))]
    assert len(apply_filters(listings, _search(condition="all"))) == 1


# ----- client (facet discovery + per-trim fetch) ----------------------------

class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        if params and "includes" in params:  # facet request
            return _Resp({"total": 1, "facets": {"trims": {
                "450h+ Premium (945)": "u", "450h+ Luxury (200)": "u",
                "350 Premium (3114)": "u", "350h Premium (100)": "u"}}})
        trim = (params or {}).get("vehicle.trim")
        rows = {
            "450h+ Premium": [_row("A", 55999, 57810), _row("B", 56864, 57810)],
            "450h+ Luxury": [_row("C", 60000, 64000, trim="450h+ Luxury")],
        }.get(trim, [])
        return _Resp({"data": rows, "links": {}})


def test_discover_trims_filters_by_token():
    client = AutoDevClient("k", session=_FakeSession())
    assert sorted(client.discover_trims(_search())) == ["450h+ Luxury", "450h+ Premium"]


def test_search_fetches_each_trim_new_only_sorted_and_parses():
    session = _FakeSession()
    client = AutoDevClient("k", session=session)
    res = client.search(_search())
    assert {l.vin for l in res} == {"A", "B", "C"}
    assert all(l.condition == "new" for l in res)
    assert res[0].msrp == 57810 and res[0].discount is not None  # baseMsrp parsed

    trim_calls = [p for (_u, p) in session.calls if p and "vehicle.trim" in p]
    assert trim_calls and all(p.get("retailListing.used") == "false" for p in trim_calls)
    assert all(p.get("sort") == "retailListing.price" for p in trim_calls)
