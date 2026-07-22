"""BGBl-Adapter: Feed-Parsing testen, ohne Netzwerk."""

from __future__ import annotations

from unittest.mock import patch

import feedparser

from legal_radar.sources.bgbl_rss import BgblRss

_REAL_PARSE = feedparser.parse

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>BGBl. Teil I</title>
<item>
  <title>Gesetz zur Regelung von XYZ</title>
  <link>https://www.recht.bund.de/bgbl/1/2026/123</link>
  <pubDate>Wed, 15 Jul 2026 10:00:00 GMT</pubDate>
  <description>Verkuendet am 15. Juli 2026</description>
</item>
<item>
  <title>Zweites Aenderungsgesetz ABC</title>
  <link>https://www.recht.bund.de/bgbl/1/2025/999</link>
  <pubDate>Mon, 30 Dec 2024 08:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


def _fake_parse(_url):
    return _REAL_PARSE(RSS_XML)


def test_bgbl_liefert_verkuendete_ab_since():
    adapter = BgblRss(url="stub")
    with patch("legal_radar.sources.bgbl_rss.feedparser.parse", _fake_parse):
        vorgaenge = adapter.fetch("2026-01-01")
    assert len(vorgaenge) == 1
    v = vorgaenge[0]
    assert v.quelle == "bgbl"
    assert v.stadium == "verkuendet"
    assert v.titel.startswith("Gesetz")
    assert v.quelle_url.startswith("https://www.recht.bund.de/")
    assert v.id.startswith("bgbl:")
    assert str(v.anwendungsbeginn) == "2026-07-15"


def test_bgbl_id_ist_stabil():
    adapter = BgblRss(url="stub")
    with patch("legal_radar.sources.bgbl_rss.feedparser.parse", _fake_parse):
        a = adapter.fetch("2020-01-01")
        b = adapter.fetch("2020-01-01")
    assert [v.id for v in a] == [v.id for v in b]


def test_bgbl_text_fuer_vorgang_ist_leer():
    """RSS liefert nur Metadaten - der Fetch-Loop muss das ohne Text tolerieren."""
    assert BgblRss(url="stub").text_fuer_vorgang("bgbl:anything") == ""


# recht.bund.de liefert pubDate im ISO-Format (nicht RFC 822).
ISO_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Gesetz mit ISO-Datum</title>
  <link>https://www.recht.bund.de/eli/bund/bgbl-1/2026/999</link>
  <pubDate>2026-07-22</pubDate>
</item>
</channel></rss>
"""


def test_bgbl_akzeptiert_iso_pubdate():
    adapter = BgblRss(url="stub")
    with patch(
        "legal_radar.sources.bgbl_rss.feedparser.parse", lambda _u: _REAL_PARSE(ISO_RSS_XML)
    ):
        vorgaenge = adapter.fetch("2026-01-01")
    assert len(vorgaenge) == 1
    assert str(vorgaenge[0].anwendungsbeginn) == "2026-07-22"
