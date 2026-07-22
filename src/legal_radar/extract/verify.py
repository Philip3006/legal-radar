"""Cross-Check von LLM-Belegen gegen den Rohtext.

CLAUDE.md-Regel: Zahlen kommen nie vom LLM. Der Kompromiss hier:
- Das LLM darf die Textstelle (Beleg) markieren, wo eine Zahl steht.
- Wir akzeptieren die Zahl nur, wenn (a) der textspan wortwoertlich im Rohtext steht
  und (b) die gleiche Zahl per Regex aus dem textspan extrahierbar ist.
Damit erzeugt das LLM keinen Wert - es findet nur die Stelle.
"""

from __future__ import annotations

import re
import unicodedata

from legal_radar.extract.rules import _eur

# Erlaubte Abweichung: max. 1 % Rundungsdifferenz zwischen LLM-Wert und Regex-Wert.
# Bewusst eng - lieber ablehnen als schweigend danebenliegen.
_TOLERANZ = 0.01


def _normalize(s: str) -> str:
    """Whitespace kollabieren, NFC normalisieren, damit LLM-Zitat matcht."""
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s).strip()


def verify_eur(beleg: dict | None, rohtext: str) -> int | None:
    """Gib den EUR-Wert zurueck, wenn Beleg im Text steht und Zahl konsistent ist."""
    if not isinstance(beleg, dict):
        return None
    wert = beleg.get("wert")
    span = beleg.get("textspan") or ""
    if not isinstance(wert, int) or wert <= 0 or not span:
        return None
    if _normalize(span) not in _normalize(rohtext):
        return None
    aus_span = _eur(span)
    if aus_span is None:
        return None
    if abs(aus_span - wert) / max(wert, 1) > _TOLERANZ:
        return None
    return aus_span


def verify_int(beleg: dict | None, rohtext: str) -> int | None:
    """Wie verify_eur, aber fuer reine Ganzzahlen (z.B. betroffene Unternehmen)."""
    if not isinstance(beleg, dict):
        return None
    wert = beleg.get("wert")
    span = beleg.get("textspan") or ""
    if not isinstance(wert, int) or wert <= 0 or not span:
        return None
    if _normalize(span) not in _normalize(rohtext):
        return None
    # Zahl mit Tausendertrennern akzeptieren
    m = re.search(r"\b([\d.,]{1,15})\b", span)
    if not m:
        return None
    try:
        aus_span = int(m.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None
    if abs(aus_span - wert) / max(wert, 1) > _TOLERANZ:
        return None
    return aus_span
