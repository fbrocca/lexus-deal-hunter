from deal_hunter import analyze
from deal_hunter.models import Listing


def _l(vin, price, msrp=None):
    rec = {"vin": vin, "model": "NX", "trim": "450h+", "price": price}
    if msrp is not None:
        rec["msrp"] = msrp
    return Listing.from_record(rec)


def test_rank_cheapest_orders_and_limits():
    listings = [_l("A", 55000), _l("B", 48000), _l("C", 51000)]
    out = analyze.rank_cheapest(listings, 2)
    assert [l.vin for l in out] == ["B", "C"]


def test_rank_by_discount():
    listings = [
        _l("A", 54000, 60000),  # 6000 off
        _l("B", 50000, 52000),  # 2000 off
        _l("C", 50000),         # no msrp -> excluded
    ]
    out = analyze.rank_by_discount(listings, 5)
    assert [l.vin for l in out] == ["A", "B"]


def test_find_price_drops():
    listings = [_l("A", 50000), _l("B", 49000), _l("C", 47000)]
    previous = {"A": 52000, "B": 49000, "C": 50000}  # A dropped 2k, C dropped 3k, B same
    drops = analyze.find_price_drops(listings, previous)
    assert [d.listing.vin for d in drops] == ["C", "A"]
    assert drops[0].amount == 3000


def test_snapshot_only_priced_with_vin():
    listings = [_l("A", 50000), Listing.from_record({"vin": "", "price": "1"})]
    snap = analyze.snapshot(listings)
    assert snap == {"A": 50000.0}
