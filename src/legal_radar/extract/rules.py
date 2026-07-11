"""Deterministische Extraktion. Laeuft VOR jedem LLM-Call.

Diese Zahlen stehen im Vorblatt jeder Drucksache. Sie sind Pflichtangaben
(Erfuellungsaufwand fuer die Wirtschaft). Kein LLM noetig, kein Halluzinationsrisiko.
"""

from __future__ import annotations

import re

_MIO = re.compile(
    r"(?P<zahl>[\d.,]+)"
    r"\s*(?P<einheit>Mio\.?|Millionen|Mrd\.?|Milliarden)?"
    r"\s*(?:EUR|Euro|€)"
)
_AUFWAND_WIRTSCHAFT = re.compile(
    r"Erf(?:ü|ue)llungsaufwand\s+f(?:ü|ue)r\s+die\s+Wirtschaft(?P<block>.{0,600})",
    re.IGNORECASE | re.DOTALL,
)
_BUSSGELD = re.compile(
    r"(?:Geldbu(?:ß|ss)e|Bu(?:ß|ss)geld).{0,120}?bis\s+zu\s+(?P<block>[^.;]{0,80})",
    re.IGNORECASE | re.DOTALL,
)
_BEHOERDE = re.compile(
    r"(Bundesamt|Bundesanstalt|Bundesnetzagentur|Bundeskartellamt)[^,.;\n]{0,60}"
)
_BEHOERDE_NEU = re.compile(
    r"(?:wird|ist)\s+(?:eine\s+)?(?:neue\s+)?(?:Beh(?:ö|oe)rde|Stelle)\s+(?:errichtet|geschaffen)",
    re.IGNORECASE,
)
_ZULASSUNG = re.compile(
    r"\b(akkreditiert|zugelassen|bestellt|zertifizierte?\s+Stelle)\b",
    re.IGNORECASE,
)

_FAKTOR = {
    "mio": 1_000_000,
    "millionen": 1_000_000,
    "mrd": 1_000_000_000,
    "milliarden": 1_000_000_000,
}


def _eur(text: str) -> int | None:
    m = _MIO.search(text)
    if not m:
        return None
    zahl = m.group("zahl").replace(".", "").replace(",", ".")
    try:
        wert = float(zahl)
    except ValueError:
        return None
    einheit = (m.group("einheit") or "").lower().rstrip(".")
    return int(wert * _FAKTOR.get(einheit, 1))


def erfuellungsaufwand_wirtschaft(text: str) -> int | None:
    m = _AUFWAND_WIRTSCHAFT.search(text)
    return _eur(m.group("block")) if m else None


def bussgeld(text: str) -> int | None:
    m = _BUSSGELD.search(text)
    return _eur(m.group("block")) if m else None


def behoerde(text: str) -> tuple[str | None, bool]:
    m = _BEHOERDE.search(text)
    return (m.group(0).strip() if m else None, bool(_BEHOERDE_NEU.search(text)))


def zulassung_noetig(text: str) -> bool:
    return bool(_ZULASSUNG.search(text))


def passes_prefilter(text: str, min_aufwand: int) -> bool:
    """Spart ~95 % der LLM-Calls."""
    aufwand = erfuellungsaufwand_wirtschaft(text)
    if aufwand is not None and aufwand >= min_aufwand:
        return True
    return bool(re.search(r"(Nachweis|Meldung|Melde)pflicht|nachzuweisen|zu\s+melden", text, re.I))
