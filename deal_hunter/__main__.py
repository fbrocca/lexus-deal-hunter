"""Entry point: fetch -> rank -> diff -> email -> persist snapshot.

Run with:  python -m deal_hunter [path/to/config.yaml]

Required environment variables:
  AUTO_DEV_API_KEY
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO

Set DRY_RUN=1 to print the digest instead of sending it (no SMTP needed).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import List

from . import analyze
from .autodev import AutoDevClient
from .config import load_config
from .digest import SmtpSettings, build_digest, send_email
from .storage import load_snapshot, save_snapshot

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("deal_hunter")


def _smtp_from_env() -> SmtpSettings:
    to = os.environ.get("EMAIL_TO", "")
    recipients = [a.strip() for a in to.replace(";", ",").split(",") if a.strip()]
    return SmtpSettings(
        host=os.environ["SMTP_HOST"],
        port=int(os.environ.get("SMTP_PORT", "587")),
        user=os.environ.get("SMTP_USER", ""),
        password=os.environ.get("SMTP_PASSWORD", ""),
        email_from=os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER", ""),
        email_to=recipients,
    )


def main(argv: List[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = argv[0] if argv else "config.yaml"
    cfg = load_config(config_path)
    dry_run = os.environ.get("DRY_RUN") == "1"

    client = AutoDevClient(api_key=os.environ.get("AUTO_DEV_API_KEY", ""))
    listings = client.search(cfg.search)
    log.info("after filtering: %d listing(s)", len(listings))

    cheapest = analyze.rank_cheapest(listings, cfg.email.top_n_cheapest)
    discounts = analyze.rank_by_discount(listings, cfg.email.top_n_discount)

    previous = load_snapshot(cfg.storage.snapshot_path)
    drops = analyze.find_price_drops(listings, previous)
    log.info("detected %d price drop(s)", len(drops))

    subject, body = build_digest(
        cfg.email,
        listings=listings,
        cheapest=cheapest,
        discounts=discounts,
        drops=drops,
    )

    if dry_run:
        print(f"Subject: {subject}\n\n{body}")
    elif not listings and not drops:
        # Nothing to report — skip the email (and the SMTP round-trip) entirely
        # rather than send an empty digest or fail a run with no content.
        log.info("no listings and no drops; skipping email")
    else:
        smtp = _smtp_from_env()
        if not smtp.email_to:
            raise SystemExit(
                "EMAIL_TO is empty — set the EMAIL_TO secret to one or more "
                "comma-separated recipient addresses."
            )
        send_email(smtp, subject, body)
        log.info("digest sent to %s: %s", ", ".join(smtp.email_to), subject)

    # Persist today's prices for tomorrow's diff (only when we actually got data,
    # so a transient empty fetch doesn't wipe history).
    if listings:
        save_snapshot(cfg.storage.snapshot_path, analyze.snapshot(listings))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
