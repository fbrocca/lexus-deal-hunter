"""Probe #2: enumerate Lexus NX inventory via Auto.dev facets/aggregations,
so we find the correct way to query the NEW NX 450h+ (not guess model strings)."""

import json
import os

import requests

KEY = os.environ["AUTO_DEV_API_KEY"]
BEARER = {"Authorization": f"Bearer {KEY}"}


def v1(params):
    r = requests.get("https://auto.dev/api/listings",
                     params={"apikey": KEY, **params}, timeout=40)
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:300]}


def v2(params):
    r = requests.get("https://api.auto.dev/listings",
                     params={"vehicle.make": "Lexus", **params}, headers=BEARER, timeout=40)
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:300]}


print("===== V1: all Lexus, dump aggregations/facets =====", flush=True)
p = v1({"make": "Lexus"})
print("V1 keys:", list(p.keys()), "total:", p.get("totalCount"), flush=True)
print("V1 promotedAggregations:", json.dumps(p.get("promotedAggregations"))[:3000], flush=True)

print("===== V1: model-string counts =====", flush=True)
for m in ["NX 450h+", "NX 450h", "NX450h+", "NX 450h Plus", "NX450h", "NX 450", "NX450H+", "NX 450H+"]:
    p = v1({"make": "Lexus", "model": m})
    print(f"  V1 model={m!r}: totalCount={p.get('totalCount')}", flush=True)

print("===== V1: NX with new-only + fuel filters (guess param names) =====", flush=True)
for extra in [{"condition": "New"}, {"fuel_type": "Plug-in Hybrid"}, {"fuelType": "Hybrid"},
              {"trim": "450h+"}, {"body_type": "SUV", "min_price": 50000}]:
    p = v1({"make": "Lexus", "model": "NX", **extra})
    recs = p.get("records") or []
    trims = sorted({str((r or {}).get("trim", "")) for r in recs})[:8]
    print(f"  V1 NX + {extra}: total={p.get('totalCount')} sampleTrims={trims}", flush=True)

print("===== V2: NX facets =====", flush=True)
p = v2({"vehicle.model": "NX", "includes": "facets,total", "limit": 1})
print("V2 keys:", list(p.keys()), "total:", p.get("total"), flush=True)
print("V2 facets:", json.dumps(p.get("facets"))[:3000], flush=True)
print("V2 discover:", json.dumps(p.get("discover"))[:1500], flush=True)
