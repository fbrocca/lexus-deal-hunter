"""Render the daily digest as styled HTML (with a plain-text fallback) and
send it over SMTP."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Dict, List, Optional

from .analyze import PriceDrop
from .config import EmailConfig, ThresholdConfig
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


# ----- formatting helpers ---------------------------------------------------

def _money(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else "—"


def _loc(l: Listing) -> str:
    bits = [b for b in (l.city, l.state) if b]
    return ", ".join(bits)


def _dealer_line(l: Listing) -> str:
    parts = []
    where = _loc(l)
    if l.dealer and where:
        parts.append(f"{l.dealer} ({where})")
    elif l.dealer:
        parts.append(l.dealer)
    elif where:
        parts.append(where)
    if l.mileage is not None:
        parts.append(f"{l.mileage:,} mi")
    return " · ".join(parts)


def is_flagged(l: Listing, t: ThresholdConfig) -> bool:
    """A listing is a 'deal' if it clears the discount or absolute-price bar."""
    if l.discount_pct is not None and t.min_discount_pct and l.discount_pct >= t.min_discount_pct:
        return True
    if t.max_price is not None and l.price is not None and l.price <= t.max_price:
        return True
    return False


# ----- HTML rendering -------------------------------------------------------

_CARD = """\
<div style="border:1px solid #e3e3e3;border-radius:10px;padding:16px 18px;margin:0 0 14px;">
  <div style="font-size:17px;font-weight:700;color:#1a1a1a;margin-bottom:6px;">{title}</div>
  {discount}
  <div style="color:#666;font-size:13px;margin-top:6px;">MSRP {msrp} · Asking {price} · was {was}</div>
  <div style="color:#666;font-size:13px;margin-top:2px;">{dealer}</div>
  <div style="color:#999;font-size:12px;margin-top:2px;">VIN {vin}</div>
  {link}
</div>"""


def _card_html(l: Listing, previous: Dict[str, float]) -> str:
    title = f"{escape(l.label)} — {_money(l.price)}"
    discount = ""
    if l.discount_pct is not None and l.discount:
        discount = (
            '<div style="color:#d93025;font-weight:700;font-size:15px;">'
            f"{l.discount_pct:.1f}% off MSRP ({_money(l.discount)} below {_money(l.msrp)})"
            "</div>"
        )
    was = previous.get(l.vin) if l.vin else None
    link = ""
    if l.url:
        link = (
            f'<a href="{escape(l.url, quote=True)}" style="color:#1a73e8;font-size:14px;'
            'text-decoration:none;display:inline-block;margin-top:8px;">View listing →</a>'
        )
    return _CARD.format(
        title=title,
        discount=discount,
        msrp=_money(l.msrp),
        price=_money(l.price),
        was=_money(was if was is not None else l.price),
        dealer=escape(_dealer_line(l)) or "—",
        vin=escape(l.vin) or "—",
        link=link,
    )


def _section(title: str, cards: List[str]) -> str:
    if not cards:
        return ""
    head = f'<h2 style="font-size:20px;font-weight:700;color:#1a1a1a;margin:28px 0 12px;">{title}</h2>'
    return head + "".join(cards)


def _drop_card_html(d: PriceDrop) -> str:
    l = d.listing
    body = (
        '<div style="color:#188038;font-weight:700;font-size:15px;">'
        f"↓ {_money(d.amount)} ({d.pct:.1f}%) — {_money(d.old_price)} → {_money(d.new_price)}"
        "</div>"
    )
    link = ""
    if l.url:
        link = (
            f'<a href="{escape(l.url, quote=True)}" style="color:#1a73e8;font-size:14px;'
            'text-decoration:none;display:inline-block;margin-top:8px;">View listing →</a>'
        )
    return (
        '<div style="border:1px solid #e3e3e3;border-radius:10px;padding:16px 18px;margin:0 0 14px;">'
        f'<div style="font-size:17px;font-weight:700;color:#1a1a1a;margin-bottom:6px;">{escape(l.label)}</div>'
        f"{body}{link}</div>"
    )


def render_html(
    *,
    date: str,
    model_desc: str,
    listings: List[Listing],
    flagged: List[Listing],
    cheapest: List[Listing],
    drops: List[PriceDrop],
    previous: Dict[str, float],
) -> str:
    sections = []
    if drops:
        sections.append(_section("📉 Price drops since last run", [_drop_card_html(d) for d in drops]))
    sections.append(_section("🔥 Flagged deals", [_card_html(l, previous) for l in flagged]))
    sections.append(_section("💸 Top 10 cheapest", [_card_html(l, previous) for l in cheapest]))
    if not flagged and not cheapest:
        sections.append('<p style="color:#666;">No matching listings today.</p>')

    return f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;max-width:680px;margin:0 auto;padding:24px;">
  <h1 style="font-size:28px;font-weight:700;margin:0 0 12px;">Lexus deal report — {escape(date)}</h1>
  <p style="color:#666;font-size:15px;line-height:1.5;margin:0 0 8px;">{escape(model_desc)}<br>
  Scanned {len(listings)} listing(s) · {len(flagged)} flagged.</p>
  {''.join(sections)}
</div>"""


# ----- plain-text fallback --------------------------------------------------

def _text_line(i: int, l: Listing) -> str:
    disc = f" ({l.discount_pct:.0f}% off MSRP)" if l.discount_pct else ""
    out = f"{i:>2}. {_money(l.price)}{disc} — {l.label} — {_dealer_line(l)}"
    if l.url:
        out += f"\n      {l.url}"
    return out


def render_text(
    *, date: str, model_desc: str, listings: List[Listing],
    flagged: List[Listing], cheapest: List[Listing], drops: List[PriceDrop],
) -> str:
    blocks = [f"Lexus deal report — {date}", model_desc,
              f"Scanned {len(listings)} listing(s) · {len(flagged)} flagged.", ""]
    if flagged:
        blocks.append("FLAGGED DEALS")
        blocks += [_text_line(i, l) for i, l in enumerate(flagged, 1)]
        blocks.append("")
    blocks.append("TOP 10 CHEAPEST")
    blocks += [_text_line(i, l) for i, l in enumerate(cheapest, 1)] or ["  (none)"]
    return "\n".join(blocks).rstrip() + "\n"


# ----- assembly + send ------------------------------------------------------

def build_digest(
    email_cfg: EmailConfig,
    thresholds: ThresholdConfig,
    *,
    date: str,
    model_desc: str,
    listings: List[Listing],
    cheapest: List[Listing],
    drops: List[PriceDrop],
    previous: Dict[str, float],
):
    flagged = [l for l in listings if is_flagged(l, thresholds)]
    flagged.sort(key=lambda l: (-(l.discount_pct or 0), l.price or 0))
    flagged = flagged[: email_cfg.top_n_discount]

    n = len(listings)
    subject = f"🔥 {n} {email_cfg.subject_prefix} deal{'s' if n != 1 else ''} today"
    text = render_text(date=date, model_desc=model_desc, listings=listings,
                        flagged=flagged, cheapest=cheapest, drops=drops)
    html = render_html(date=date, model_desc=model_desc, listings=listings,
                       flagged=flagged, cheapest=cheapest, drops=drops, previous=previous)
    return subject, text, html


def send_email(settings: SmtpSettings, subject: str, text: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = ", ".join(settings.email_to)
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

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
