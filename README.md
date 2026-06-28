# lexus-deal-hunter

Daily scanner for **Lexus NX 450h+** (the plug-in hybrid) listings, built on the
[Auto.dev](https://auto.dev) listings API. Every run ranks the market by
**cheapest price** and **biggest discount off MSRP**, flags **day-over-day price
drops**, and emails a digest.

It's a sibling of `audi-deal-hunter`: the engine (`deal_hunter`) is make-agnostic
— everything Lexus-specific lives in [`config.yaml`](config.yaml).

## How the targeting works

Auto.dev indexes the whole NX family under model `NX`, so a plain `make=Lexus,
model=NX` query also returns the NX 250 / 350 / 350h. The `keywords` filter in
`config.yaml` keeps only listings whose model/trim mentions `450h`, isolating the
450h+ PHEV. Color is intentionally not filtered.

```yaml
search:
  make: Lexus
  models: ["NX"]
  keywords: ["450h"]   # variant filter: drop NX 250 / 350 / 350h
  condition: new
  year_min: 2022
```

## Layout

```
deal_hunter/
  config.py     load + validate config.yaml
  models.py     Listing dataclass + tolerant Auto.dev field parsing
  autodev.py    Auto.dev client + keyword/condition/year/price filtering
  analyze.py    cheapest / biggest-discount ranking + price-drop detection
  storage.py    {vin: price} snapshot persistence (committed back by CI)
  digest.py     render the text digest + SMTP send
  __main__.py   orchestration entry point
config.yaml     all Lexus-specific settings
data/snapshot.json   previous-run prices (tracked, so history survives CI)
.github/workflows/scan.yml   twice-daily cron
```

## Run locally

```bash
pip install -r requirements.txt

# Print the digest instead of emailing (no SMTP needed):
AUTO_DEV_API_KEY=... DRY_RUN=1 python -m deal_hunter config.yaml

# Full run (sends email):
AUTO_DEV_API_KEY=... SMTP_HOST=... SMTP_PORT=587 SMTP_USER=... \
SMTP_PASSWORD=... EMAIL_FROM=... EMAIL_TO=you@example.com \
python -m deal_hunter config.yaml
```

## Deploy (GitHub Actions)

1. Add these repository secrets (**Settings → Secrets and variables → Actions**):
   `AUTO_DEV_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
   `EMAIL_FROM`, `EMAIL_TO`.
2. **Actions → Lexus deal scan → Run workflow** to trigger the first run.
3. The workflow runs twice daily and commits the updated `data/snapshot.json`
   so tomorrow's run can diff prices.

### First-run check

Confirm Auto.dev returns rows for the NX. In the run log, look for:

```
autodev: model=NX returned N row(s)
after filtering: M listing(s)
```

If `N = 0`, Auto.dev indexes the model under a different name — adjust
`search.models` / `search.keywords` in `config.yaml`. (`discount` ranking
depends on the API returning an MSRP field per listing; if MSRPs come back
empty, the "biggest discount" section stays empty while "cheapest" still works.)

## Tests

```bash
python -m pytest -q
```
