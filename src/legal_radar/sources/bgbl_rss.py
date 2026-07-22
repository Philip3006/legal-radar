"""recht.bund.de: RSS-Feed neuer Verkuendungen im BGBl. Teil I.

Bewusst niedrig priorisiert: steht ein Gesetz im BGBl., ist das Fenster meist zu.
Nutzen: Bestaetigung von Stadienwechseln (bt -> verkuendet), nicht Entdeckung.

Der Feed liefert nur Metadaten (Titel, Link auf PDF, Datum). Kein Volltext -
`rohtext` bleibt leer, LLM- und Regex-Extraktion greifen nicht. Score bleibt 0,
aber die History bekommt einen sauberen 'verkuendet'-Eintrag, wenn wir den
DIP-Vorgang ueber Titel-Match verknuepfen koennen (Follow-up).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime

import feedparser

from legal_radar.core.models import Vorgang

log = logging.getLogger(__name__)

# Vom Browser verifizierte Default-URL (Stand 2026-07). Bei 404 in Settings ueberschreiben.
DEFAULT_URL = "https://www.recht.bund.de/rss/feeds/rss_bgbl-1.xml?nn=211452"


class BgblRss:
    name = "bgbl"

    def __init__(self, url: str = DEFAULT_URL) -> None:
        self.url = url

    def fetch(self, since: str) -> list[Vorgang]:
        seit = date.fromisoformat(since)
        feed = feedparser.parse(self.url)
        if feed.bozo and not feed.entries:
            log.warning("BGBl-RSS unparsable: %s", getattr(feed, "bozo_exception", "unknown"))
            return []

        out: list[Vorgang] = []
        for e in feed.entries:
            link = getattr(e, "link", "") or ""
            titel = (getattr(e, "title", "") or "").strip()
            if not link or not titel:
                continue
            pub = _pubdate(e)
            if pub and pub < seit:
                continue
            vid = _vid(link, titel)
            out.append(
                Vorgang(
                    id=vid,
                    quelle="bgbl",
                    titel=titel,
                    stadium="verkuendet",
                    quelle_url=link,
                    anwendungsbeginn=pub,
                )
            )
        return out

    # RSS liefert kein Volltext-Endpoint. Adapter-Interface bleibt konsistent zu DIP.
    def text_fuer_vorgang(self, vorgang_id: str) -> str:  # noqa: ARG002
        return ""


def _pubdate(entry) -> date | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6]).date()
            except (TypeError, ValueError):
                continue
    # recht.bund.de liefert pubDate als ISO (YYYY-MM-DD), nicht RFC-822.
    for attr in ("published", "pubdate", "updated"):
        raw = getattr(entry, attr, "") or ""
        try:
            return date.fromisoformat(raw.strip()[:10])
        except ValueError:
            continue
    return None


def _vid(link: str, titel: str) -> str:
    """Stabile ID aus link+titel. BGBl-URLs enthalten die Fundstelle."""
    key = hashlib.sha256(f"{link}|{titel}".encode()).hexdigest()[:16]
    return f"bgbl:{key}"
