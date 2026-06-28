"""Render the daily digest and send it over SMTP."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from .analyze import PriceDrop
from .config import EmailConfig
from .models import Listing


@dataclass
class SmtpSettings:
    host: str
    port: int
    user: str
    password: str
    email_from: str
    email_to: List[str]

    @property
    def use_ssl(self) -> bool:
        return self.port == 465


def _money(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else "—"


def _loc(l: Listing) -> str:
    bits = [b for b in (l.city, l.state) if b]
    return ", ".join(bits)


def _cheapest_lines(listings: List[Listing]) -> List[str]:
    lines = []
    for i, l in enumerate(listings, 1):
        disc = f" ({l.discount_pct:.0f}% off MSRP)" if l.discount_pct else ""
        lines.append(
            f"{i:>2}. {_money(l.price)}{disc} — {l.label} — {l.dealer or _loc(l)}"
            + (f"\n      {l.url}" if l.url else "")
        )
    return lines


def _discount_lines(listings: List[Listing]) -> List[str]:
    lines = []
    for i, l in enumerate(listings, 1):
        pct = f"{l.discount_pct:.0f}%" if l.discount_pct is not None else "?"
        lines.append(
            f"{i:>2}. -{_money(l.discount)} ({pct}) — {l.label} — "
            f"{_money(l.price)} (MSRP {_money(l.msrp)})"
            + (f"\n      {l.url}" if l.url else "")
        )
    return lines


def _drop_lines(drops: List[PriceDrop]) -> List[str]:
    lines = []
    for i, d in enumerate(drops, 1):
        lines.append(
            f"{i:>2}. -{_money(d.amount)} ({d.pct:.0f}%) — {d.listing.label} — "
            f"{_money(d.old_price)} -> {_money(d.new_price)}"
            + (f"\n      {d.listing.url}" if d.listing.url else "")
        )
    return lines


def render_text(
    *,
    cheapest: List[Listing],
    discounts: List[Listing],
    drops: List[PriceDrop],
    total: int,
) -> str:
    blocks: List[str] = []
    blocks.append(f"{total} matching listing(s) found.\n")

    if drops:
        blocks.append("PRICE DROPS SINCE LAST RUN")
        blocks.append("\n".join(_drop_lines(drops)))
        blocks.append("")

    blocks.append("CHEAPEST")
    blocks.append("\n".join(_cheapest_lines(cheapest)) if cheapest else "  (none)")
    blocks.append("")

    blocks.append("BIGGEST DISCOUNT OFF MSRP")
    blocks.append("\n".join(_discount_lines(discounts)) if discounts else "  (none with MSRP data)")
    blocks.append("")

    return "\n".join(blocks).rstrip() + "\n"


def build_subject(prefix: str, cheapest: List[Listing], drops: List[PriceDrop]) -> str:
    parts = [prefix]
    if cheapest and cheapest[0].price is not None:
        parts.append(f"cheapest {_money(cheapest[0].price)}")
    if drops:
        parts.append(f"{len(drops)} price drop(s)")
    return " ".join(parts)


def build_digest(
    cfg: EmailConfig,
    *,
    listings: List[Listing],
    cheapest: List[Listing],
    discounts: List[Listing],
    drops: List[PriceDrop],
):
    subject = build_subject(cfg.subject_prefix, cheapest, drops)
    body = render_text(
        cheapest=cheapest, discounts=discounts, drops=drops, total=len(listings)
    )
    return subject, body


def send_email(settings: SmtpSettings, subject: str, body: str) -> None:
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = ", ".join(settings.email_to)
    msg.attach(MIMEText(body, "plain"))

    if settings.use_ssl:
        server = smtplib.SMTP_SSL(settings.host, settings.port, timeout=30)
    else:
        server = smtplib.SMTP(settings.host, settings.port, timeout=30)
    try:
        if not settings.use_ssl:
            server.starttls()
        if settings.user:
            server.login(settings.user, settings.password)
        server.sendmail(settings.email_from, settings.email_to, msg.as_string())
    finally:
        server.quit()
