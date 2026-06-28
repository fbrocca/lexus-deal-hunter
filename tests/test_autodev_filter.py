from deal_hunter.autodev import apply_filters
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
