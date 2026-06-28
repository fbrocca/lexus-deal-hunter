"""One-off Auto.dev probe (run in CI; we can't reach auto.dev locally).

Goal: find where the NX 450h+ inventory lives and how new/used is encoded,
so the scanner can return all NEW 450h+ listings. Prints concise summaries.
"""

import json
import os

import requests

KEY = os.environ["AUTO_DEV_API_KEY"]
BEARER = {"Authorization": f"Bearer {KEY}"}


def get(url, params, headers):
    r = requests.get(url, params=params, headers=headers, timeout=40)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:400]}


def v2(model, pages=3):
    """Query api.auto.dev for a model, follow a few cursor pages, summarize."""
    url = "https://api.auto.dev/listings"
    params = {"vehicle.make": "Lexus", "vehicle.model": model, "limit": 100}
    all_recs = []
    total = None
    for _ in range(pages):
        sc, p = get(url, params, BEARER)
        if not isinstance(p, dict):
            break
        total = p.get("total") or p.get("totalCount") or total
        data = p.get("data") or []
        all_recs.extend(data)
        nxt = (p.get("links") or {}).get("next")
        if not data or not nxt:
            break
        if isinstance(nxt, str) and nxt.startswith("http"):
            url, params = nxt, None
        else:
            params = {"vehicle.make": "Lexus", "vehicle.model": model, "limit": 100, "cursor": nxt}
    models = {}
    for r in all_recs:
        m = (r.get("vehicle") or {}).get("model", "")
        models[m] = models.get(m, 0) + 1
    print(f"V2 model={model!r}: total={total} fetched={len(all_recs)} vehicle.models={models}")
    return all_recs


print("=== V2: NX bucket (all powertrains?) ===", flush=True)
nx = v2("NX")
print("=== V2: NX 450h+ ===", flush=True)
phev = v2("NX 450h+")

# Dump one full 450h+ record so we can see the new/used + mileage fields.
sample = None
for r in (phev + nx):
    if "450h" in str((r.get("vehicle") or {}).get("model", "")).lower():
        sample = r
        break
if sample:
    print("FULL 450h+ RECORD:", json.dumps(sample)[:3500], flush=True)
    rl = sample.get("retailListing") or {}
    print("retailListing keys:", list(rl.keys()), flush=True)
else:
    print("No 450h+ record found in V2.", flush=True)
