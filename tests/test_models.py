from deal_hunter.models import Listing, parse_int, parse_money


def test_parse_money_handles_formats():
    assert parse_money("$53,000") == 53000.0
    assert parse_money("53000") == 53000.0
    assert parse_money(53000.5) == 53000.5
    assert parse_money("") is None
    assert parse_money(None) is None
    assert parse_money("N/A") is None
    assert parse_money(0) is None


def test_parse_int():
    assert parse_int("10 miles") == 10
    assert parse_int(None) is None


def test_from_record_maps_alternate_keys():
    rec = {
        "vin": "abc123",
        "modelYear": "2024",
        "make": "Lexus",
        "model": "NX",
        "trimName": "450h+ Luxury",
        "priceUnformatted": "53000",
        "msrp": "60000",
        "miles": "12",
        "inventoryType": "New",
        "dealerName": "Lexus of Somewhere",
        "vdpUrl": "https://example.com/x",
    }
    l = Listing.from_record(rec)
    assert l.vin == "ABC123"
    assert l.year == 2024
    assert l.trim == "450h+ Luxury"
    assert l.price == 53000.0
    assert l.msrp == 60000.0
    assert l.condition == "new"
    assert l.url == "https://example.com/x"


def test_discount_properties():
    l = Listing.from_record({"vin": "v", "price": "54000", "msrp": "60000"})
    assert l.discount == 6000.0
    assert l.discount_pct == 10.0


def test_discount_none_when_no_msrp():
    l = Listing.from_record({"vin": "v", "price": "54000"})
    assert l.discount is None
    assert l.discount_pct is None


def test_from_record_flattens_v2_nested_objects():
    # Shape of an Auto.dev v2 listing: data nested under vehicle/retailListing.
    rec = {
        "vehicle": {
            "vin": "JTJ123",
            "year": 2024,
            "make": "Lexus",
            "model": "NX",
            "trim": "450h+ Luxury",
            "mileage": 8,
        },
        "retailListing": {
            "price": 53000,
            "msrp": 61000,
            "condition": "New",
            "dealerName": "Lexus of Somewhere",
            "city": "Austin",
            "state": "TX",
            "vdpUrl": "https://example.com/jtj123",
        },
    }
    l = Listing.from_record(rec)
    assert l.vin == "JTJ123"
    assert l.make == "Lexus"
    assert l.trim == "450h+ Luxury"
    assert l.price == 53000.0
    assert l.msrp == 61000.0
    assert l.condition == "new"
    assert l.discount_pct == 13.1
    assert l.city == "Austin"
    assert l.url == "https://example.com/jtj123"
