"""Ereignisse aus der Historie, nicht Zustaende aus der Tabelle.

Ereignis 3 (Aufwand geaendert), 4 (Fenster oeffnet) und 6 (gestorben) sind der
eigentliche Grund, das Ding zu bauen. Ereignis 1 ist nur der Eintrittspreis.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Event:
    kind: str  # neu | stadium | aufwand | fenster | wettbewerb | tot
    vorgang_id: str
    titel: str
    detail: str
    url: str


def events_since(con: sqlite3.Connection, tage: int) -> list[Event]:
    rows = con.execute(
        """
        SELECT h.vorgang_id, h.feld, h.alt, h.neu, v.titel, v.quelle_url
        FROM vorgang_history h JOIN vorgang v ON v.id = h.vorgang_id
        WHERE h.ts >= date('now', ?)
        ORDER BY h.ts DESC
        """,
        (f"-{tage} days",),
    ).fetchall()

    out: list[Event] = []
    for r in rows:
        feld = r["feld"]
        if feld == "erf_aufwand_eur":
            kind, detail = "aufwand", f"Erfuellungsaufwand {r['alt']} -> {r['neu']} EUR/Jahr"
        elif feld == "stadium":
            kind = "tot" if r["neu"] == "tot" else "stadium"
            detail = f"{r['alt']} -> {r['neu']}"
        elif feld == "anwendungsbeginn":
            kind, detail = "fenster", f"Anwendungsbeginn {r['alt']} -> {r['neu']}"
        else:
            continue
        out.append(Event(kind, r["vorgang_id"], r["titel"], detail, r["quelle_url"]))
    return out
