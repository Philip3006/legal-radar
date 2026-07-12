"""Ereignisse aus der Historie, nicht Zustaende aus der Tabelle.

Ereignis 3 (Aufwand geaendert), 4 (Fenster oeffnet) und 6 (gestorben) sind der
eigentliche Grund, das Ding zu bauen. Ereignis 1 ist nur der Eintrittspreis.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

STADIUM_LABEL = {
    "referentenentwurf": "Referentenentwurf",
    "kabinett": "Kabinett",
    "bt": "Bundestag",
    "ausschuss": "Ausschuss",
    "verkuendet": "Verkündet",
    "anwendbar": "Anwendbar",
    "tot": "Eingestellt",
}


def _fmt_eur(v: str | None) -> str:
    if v is None or v == "":
        return "-"
    try:
        n = int(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f} Mrd EUR"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} Mio EUR"
    return f"{n:,} EUR".replace(",", ".")


def _fmt_stadium(v: str | None) -> str:
    return STADIUM_LABEL.get(v, v or "?")


def _fmt_datum(v: str | None) -> str:
    if not v:
        return "offen"
    try:
        return date.fromisoformat(v).strftime("%d.%m.%Y")
    except ValueError:
        return v


@dataclass
class Event:
    kind: str  # neu | stadium | aufwand | fenster | wettbewerb | tot
    vorgang_id: str
    titel: str
    detail: str
    url: str


def events_since(con: sqlite3.Connection, tage: int) -> list[Event]:
    out: list[Event] = []

    # Neu erschienene Vorgaenge (erstgesehen im Zeitfenster)
    neu_rows = con.execute(
        """
        SELECT id, titel, quelle_url
        FROM vorgang
        WHERE erstgesehen >= date('now', ?)
          AND input_hash IS NOT NULL
        ORDER BY erstgesehen DESC
        """,
        (f"-{tage} days",),
    ).fetchall()
    for r in neu_rows:
        out.append(Event("neu", r["id"], r["titel"], "neu im Radar", r["quelle_url"]))

    # Aenderungen bestehender Vorgaenge
    rows = con.execute(
        """
        SELECT h.vorgang_id, h.feld, h.alt, h.neu, v.titel, v.quelle_url
        FROM vorgang_history h JOIN vorgang v ON v.id = h.vorgang_id
        WHERE h.ts >= date('now', ?)
        ORDER BY h.ts DESC
        """,
        (f"-{tage} days",),
    ).fetchall()

    for r in rows:
        feld = r["feld"]
        if feld == "erf_aufwand_eur":
            kind = "aufwand"
            detail = f"{_fmt_eur(r['alt'])} -> {_fmt_eur(r['neu'])} / Jahr"
        elif feld == "stadium":
            kind = "tot" if r["neu"] == "tot" else "stadium"
            detail = f"{_fmt_stadium(r['alt'])} -> {_fmt_stadium(r['neu'])}"
        elif feld == "anwendungsbeginn":
            kind = "fenster"
            detail = f"Anwendungsbeginn: {_fmt_datum(r['alt'])} -> {_fmt_datum(r['neu'])}"
        else:
            continue
        out.append(Event(kind, r["vorgang_id"], r["titel"], detail, r["quelle_url"]))
    return out
