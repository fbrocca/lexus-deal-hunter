from pathlib import Path

from deal_hunter import analyze
from deal_hunter.config import load_config
from deal_hunter.digest import build_digest
from deal_hunter.models import Listing
from deal_hunter.storage import load_snapshot, save_snapshot


def _l(vin, price, msrp=None):
    rec = {"vin": vin, "year": 2024, "make": "Lexus", "model": "NX", "trim": "450h+", "price": price}
    if msrp is not None:
        rec["msrp"] = msrp
    return Listing.from_record(rec)


def test_snapshot_round_trip(tmp_path):
    p = tmp_path / "data" / "snapshot.json"
    save_snapshot(p, {"A": 50000.0, "B": 48000.0})
    assert load_snapshot(p) == {"A": 50000.0, "B": 48000.0}


def test_load_snapshot_missing_file(tmp_path):
    assert load_snapshot(tmp_path / "nope.json") == {}


def test_load_config_reads_lexus_defaults():
    cfg = load_config(Path(__file__).resolve().parent.parent / "config.yaml")
    assert cfg.search.make == "Lexus"
    assert cfg.search.models == ["NX"]
    assert "450h" in cfg.search.keywords
    assert cfg.search.condition == "new"


def test_build_digest_text_contains_sections():
    listings = [_l("A", 54000, 60000), _l("B", 49000)]
    cheapest = analyze.rank_cheapest(listings, 10)
    discounts = analyze.rank_by_discount(listings, 10)
    drops = analyze.find_price_drops(listings, {"A": 56000})

    from deal_hunter.config import EmailConfig

    subject, body = build_digest(
        EmailConfig(subject_prefix="[Lexus NX 450h+]"),
        listings=listings,
        cheapest=cheapest,
        discounts=discounts,
        drops=drops,
    )
    assert "[Lexus NX 450h+]" in subject
    assert "CHEAPEST" in body
    assert "BIGGEST DISCOUNT OFF MSRP" in body
    assert "PRICE DROPS SINCE LAST RUN" in body
    assert "$49,000" in body
