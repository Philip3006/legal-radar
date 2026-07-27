"""Titel-basiertes Matching zwischen Quellen.

Zweck: Wenn BGBl eine Verkuendung liefert, deren Titel zu einem existierenden
DIP-Vorgang passt, ist das ein Stadienwechsel (bt -> verkuendet) auf dem
DIP-Vorgang - keine neue Row. Ohne dieses Matching zaehlt jede Verkuendung
doppelt.

DIP-Titel: "Entwurf eines Gesetzes zur Regelung von X"
BGBl-Titel: "Gesetz zur Regelung von X"

Normalisierung strippt "Entwurf eines", macht "Gesetzes" -> "Gesetz" und
kleinert. Danach exakter Vergleich. Bei fuzzy Match verzichten wir bewusst -
lieber ab und zu einen Match verpassen als falsche Vorgaenge verheiraten.
"""

from __future__ import annotations

import re

_ENTWURF = re.compile(r"^\s*entwurf\s+eines?\s+", re.IGNORECASE)
_GESETZES = re.compile(r"\bgesetzes\b", re.IGNORECASE)
_WS = re.compile(r"\s+")


def titel_normalize(titel: str) -> str:
    """Vereinheitlichte Form fuer Titel-Vergleich."""
    t = titel.strip().lower()
    t = _ENTWURF.sub("", t)
    t = _GESETZES.sub("gesetz", t)
    t = _WS.sub(" ", t)
    return t
