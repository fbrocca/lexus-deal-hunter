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
    assert cfg.search.model == "NX"
    # Targets the plug-in hybrid via the trim token.
    assert "450h" in cfg.search.trim_contains
    assert cfg.search.condition == "new"


def test_build_digest_html_contains_sections():
    listings = [_l("A", 54000, 60000), _l("B", 49000)]
    cheapest = analyze.rank_cheapest(listings, 10)
    drops = analyze.find_price_drops(listings, {"A": 56000})

    from deal_hunter.config import EmailConfig, ThresholdConfig

    subject, text, html = build_digest(
        EmailConfig(subject_prefix="Lexus NX 450h+"),
        ThresholdConfig(min_discount_pct=8.0),
        date="2026-06-28",
        model_desc="Lexus NX 450h+ (new), nationwide",
        listings=listings,
        cheapest=cheapest,
        drops=drops,
        previous={"A": 56000},
    )
    assert "Lexus NX 450h+" in subject and "2 " in subject
    # HTML structure
    assert "Lexus deal report — 2026-06-28" in html
    assert "Top 10 cheapest" in html
    assert "Flagged deals" in html          # the 10% discount listing clears 8%
    assert "Price drops" in html
    assert "% off MSRP" in html
    assert "$49,000" in html
    # plain-text fallback present
    assert "TOP 10 CHEAPEST" in text
