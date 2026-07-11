"""Score = Produkt, nicht Summe. Ein K.-o.-Kriterium zieht alles auf null.

Bei einer Summe kompensiert hoher Erfuellungsaufwand die fehlende Zulassung —
genau der Fehler, der sechs Monate Arbeit kostet.
"""

from __future__ import annotations

import math
from datetime import date

# Zweiseitige Maerkte sind das teuerste Muster. Henne-Ei-Kaltstart.
KALTSTART = {
    "compliance": 1.0,
    "datenprodukt": 0.8,
    "nachweis": 0.7,
    "vermittlung": 0.4,
    "keins": 0.0,
}


def zeitfenster(anwendungsbeginn: date | None, heute: date | None = None) -> float:
    """<6 Monate: zu spaet. >36: Gesetz aendert sich noch. Sweet Spot 12-30."""
    if anwendungsbeginn is None:
        return 0.3
    heute = heute or date.today()
    monate = (anwendungsbeginn - heute).days / 30.44
    if monate < 6:
        return 0.0
    if monate > 36:
        return 0.2
    if monate < 12:
        return 0.2 + 0.8 * (monate - 6) / 6
    if monate <= 30:
        return 1.0
    return 1.0 - 0.8 * (monate - 30) / 6


def marktgroesse(erf_aufwand_eur: int | None, betroffene: int | None) -> float:
    if not erf_aufwand_eur or erf_aufwand_eur <= 0:
        return 0.1
    s = min(1.0, math.log10(erf_aufwand_eur) / 9.0)
    # Wenige Grosskonzerne loesen es intern oder rufen eine Beratung.
    if betroffene and betroffene < 500:
        s *= 0.4
    return s


def durchsetzung(bussgeld_eur: int | None, behoerde: str | None, behoerde_neu: bool) -> float:
    """Ohne Behoerde und ohne Bussgeld: keine Zahlungsbereitschaft. K.-o."""
    if not bussgeld_eur and not behoerde:
        return 0.0
    s = 0.5
    if bussgeld_eur:
        s += 0.3
    if behoerde and not behoerde_neu:
        s += 0.2
    return min(1.0, s)


def score(
    *,
    erf_aufwand_eur: int | None,
    betroffene: int | None,
    anwendungsbeginn: date | None,
    muster: str,
    bussgeld_eur: int | None,
    behoerde: str | None,
    behoerde_neu: bool,
    zulassung_noetig: bool,
    wettbewerber: int = 0,
) -> float:
    return (
        marktgroesse(erf_aufwand_eur, betroffene)
        * zeitfenster(anwendungsbeginn)
        * KALTSTART.get(muster, 0.0)
        * durchsetzung(bussgeld_eur, behoerde, behoerde_neu)
        * (0.3 if zulassung_noetig else 1.0)
        * max(0.0, 1.0 - 0.25 * wettbewerber)
    )
