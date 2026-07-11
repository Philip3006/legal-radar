"""Datenmodelle. Zahlen und URLs stammen immer aus dem Rohdokument."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Stadium = Literal[
    "referentenentwurf", "kabinett", "bt", "ausschuss", "verkuendet", "anwendbar", "tot"
]
Muster = Literal["compliance", "nachweis", "vermittlung", "datenprodukt", "keins"]


class Pflicht(BaseModel):
    typ: Literal["Nachweis", "Meldung", "Zertifizierung", "Register", "Beschaffung"]
    gegenstand: str
    frequenz: str | None = None


class Durchsetzung(BaseModel):
    """Ohne Behoerde und ohne Bussgeld gibt es keine Zahlungsbereitschaft."""

    bussgeld_eur: int | None = None
    behoerde: str | None = None
    behoerde_neu: bool = False


class Vorgang(BaseModel):
    id: str
    quelle: str
    titel: str
    stadium: Stadium
    quelle_url: str
    anwendungsbeginn: date | None = None
    erf_aufwand_eur: int | None = None
    einmalaufwand_eur: int | None = None
    betroffene: int | None = None
    zulassung_noetig: bool = False
    pflichten: list[Pflicht] = Field(default_factory=list)
    durchsetzung: Durchsetzung = Field(default_factory=Durchsetzung)
    muster: Muster = "keins"
    rohtext: str = ""
