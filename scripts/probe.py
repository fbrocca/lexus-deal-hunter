"""Probe #3: the 450h+ lives under vehicle.model=NX + vehicle.trim='450h+ ...'.
Enumerate the 450h+ trims, confirm the new-only filter, and check sorting."""

import json
import os

import requests

KEY = os.environ["AUTO_DEV_API_KEY"]
BEARER = {"Authorization": f"Bearer {KEY}"}


def v2(params):
    r = requests.get("https://api.auto.dev/listings",
                     params={"vehicle.make": "Lexus", **params}, headers=BEARER, timeout=40)
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:300]}


# 1) All facet categories + every 450h+ trim name.
p = v2({"vehicle.model": "NX", "includes": "facets,total", "limit": 1})
fac = p.get("facets") or {}
print("facet categories:", list(fac.keys()), flush=True)
trims = fac.get("trims") or {}
h450 = [k for k in trims if "450" in k]
print("450h+ trims:", json.dumps(h450), flush=True)
for k in fac:
    if k not in ("years", "makes", "models", "trims"):
        print("FACET", k, "=", json.dumps(fac[k])[:600], flush=True)

# 2) Confirm a trim query + the new-only filter param.
def total_of(params):
    q = v2({**params, "includes": "total", "limit": 1})
    yr = None
    used = None
    if q.get("data"):
        v = q["data"][0]
        yr = (v.get("vehicle") or {}).get("year")
        used = (v.get("retailListing") or {}).get("used")
    return q.get("total"), yr, used

for params in [
    {"vehicle.model": "NX", "vehicle.trim": "450h+ Premium"},
    {"vehicle.model": "NX", "vehicle.trim": "450h+ Premium", "retailListing.used": "false"},
    {"vehicle.model": "NX", "vehicle.trim": "450h+ Premium", "retailListing.used": "true"},
    {"vehicle.model": "NX", "vehicle.trim": "450h+ Premium", "retailListing.used": "false",
     "sort": "retailListing.price"},
]:
    print(params, "->", total_of(params), flush=True)

# 3) Sample cheapest NEW 450h+ record (verify fields).
q = v2({"vehicle.model": "NX", "vehicle.trim": "450h+ Premium", "retailListing.used": "false",
        "sort": "retailListing.price", "limit": 3})
for v in (q.get("data") or [])[:3]:
    rl = v.get("retailListing") or {}
    ve = v.get("vehicle") or {}
    print(f"  NEW? used={rl.get('used')} yr={ve.get('year')} trim={ve.get('trim')} "
          f"price={rl.get('price')} msrp={ve.get('baseMsrp')} miles={rl.get('miles')} "
          f"dealer={rl.get('dealer')} {rl.get('city')},{rl.get('state')}", flush=True)
