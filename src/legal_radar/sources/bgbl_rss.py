"""recht.bund.de: RSS-Metadaten neuer Verkuendungen, Inhalt bislang nur PDF.

Bewusst niedrig priorisiert: steht ein Gesetz im BGBl., ist das Fenster meist zu.
Nutzen liegt in der Bestaetigung von Stadienwechseln, nicht in der Entdeckung.
"""

from __future__ import annotations

FEED_I = "https://www.recht.bund.de/bgbl/1/rss"  # TODO(claude): URL verifizieren


class BgblRss:
    name = "bgbl"

    def fetch(self, since: str) -> list:
        raise NotImplementedError("Stub")
