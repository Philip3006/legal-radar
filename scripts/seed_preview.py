"""Fuellt eine Preview-DB mit realistischen Fake-Vorgaengen fuer HTML-Iteration.

Nutzen: RADAR_DB=data/preview.db uv run python scripts/seed_preview.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_radar.core import db  # noqa: E402
from legal_radar.core.config import Settings  # noqa: E402


HEUTE = date.today()


def _tage_her(n: int) -> str:
    return (HEUTE - timedelta(days=n)).isoformat()


VORGAENGE = [
    {
        "id": "dip:333001",
        "titel": "Gesetz zur Weiterentwicklung der Lieferkettensorgfaltspflichten",
        "stadium": "bt",
        "quelle_url": "https://dip.bundestag.de/vorgang/-/333001",
        "anwendungsbeginn": (HEUTE + timedelta(days=180)).isoformat(),
        "betroffene": 3200,
        "einmalaufwand_eur": 45_000_000,
        "erf_aufwand_eur": 320_000_000,
        "bussgeld_eur": 8_000_000,
        "behoerde": "Bundesamt fuer Wirtschaft und Ausfuhrkontrolle",
        "behoerde_neu": 0,
        "zulassung_noetig": 0,
        "muster": "nachweis",
        "input_hash": "seed-lksg-001",
        "erstgesehen": _tage_her(3),
        "zuletzt_geprueft": _tage_her(0),
        "score": 0.87,
        "score_hash": "seed-lksg-001",
        "pflichten": [
            {
                "typ": "Meldepflicht",
                "gegenstand": "Jaehrlicher Menschenrechtsbericht an BAFA",
                "frequenz": "jaehrlich",
            },
            {
                "typ": "Nachweispflicht",
                "gegenstand": "Risikoanalyse fuer Lieferanten Tier 1-3",
                "frequenz": "laufend",
            },
        ],
    },
    {
        "id": "dip:333002",
        "titel": "Zweites Gesetz zur Umsetzung der NIS2-Richtlinie",
        "stadium": "ausschuss",
        "quelle_url": "https://dip.bundestag.de/vorgang/-/333002",
        "anwendungsbeginn": (HEUTE + timedelta(days=90)).isoformat(),
        "betroffene": 29000,
        "einmalaufwand_eur": 800_000_000,
        "erf_aufwand_eur": 1_600_000_000,
        "bussgeld_eur": 10_000_000,
        "behoerde": "Bundesamt fuer Sicherheit in der Informationstechnik",
        "behoerde_neu": 0,
        "zulassung_noetig": 0,
        "muster": "compliance",
        "input_hash": "seed-nis2-002",
        "erstgesehen": _tage_her(8),
        "zuletzt_geprueft": _tage_her(1),
        "score": 0.92,
        "score_hash": "seed-nis2-002",
        "pflichten": [
            {
                "typ": "Meldepflicht",
                "gegenstand": "Sicherheitsvorfaelle binnen 24h an BSI",
                "frequenz": "anlassbezogen",
            },
            {
                "typ": "Registrierpflicht",
                "gegenstand": "Erst-Registrierung bei BSI",
                "frequenz": "einmalig",
            },
            {
                "typ": "Nachweispflicht",
                "gegenstand": "Jaehrliches Audit der IT-Schutzmassnahmen",
                "frequenz": "jaehrlich",
            },
        ],
    },
    {
        "id": "dip:333003",
        "titel": "Gesetz zur Anpassung des Bundesdatenschutzgesetzes an EU-KI-Verordnung",
        "stadium": "referentenentwurf",
        "quelle_url": "https://dip.bundestag.de/vorgang/-/333003",
        "anwendungsbeginn": (HEUTE + timedelta(days=365)).isoformat(),
        "betroffene": 12000,
        "einmalaufwand_eur": 180_000_000,
        "erf_aufwand_eur": 240_000_000,
        "bussgeld_eur": 35_000_000,
        "behoerde": "Bundesnetzagentur",
        "behoerde_neu": 1,
        "zulassung_noetig": 1,
        "muster": "compliance",
        "input_hash": "seed-kivo-003",
        "erstgesehen": _tage_her(1),
        "zuletzt_geprueft": _tage_her(0),
        "score": 0.78,
        "score_hash": "seed-kivo-003",
        "pflichten": [
            {
                "typ": "Konformitaetsbewertung",
                "gegenstand": "Hochrisiko-KI-Systeme vor Marktzugang",
                "frequenz": "vor Einsatz",
            },
            {
                "typ": "Registrierpflicht",
                "gegenstand": "EU-Datenbank fuer Hochrisiko-KI",
                "frequenz": "einmalig",
            },
        ],
    },
    {
        "id": "dip:333004",
        "titel": "Gesetz zur Einfuehrung einer digitalen Rechnungspflicht (E-Rechnungsgesetz II)",
        "stadium": "verkuendet",
        "quelle_url": "https://dip.bundestag.de/vorgang/-/333004",
        "anwendungsbeginn": (HEUTE + timedelta(days=30)).isoformat(),
        "betroffene": 3_100_000,
        "einmalaufwand_eur": 1_200_000_000,
        "erf_aufwand_eur": 450_000_000,
        "bussgeld_eur": 500_000,
        "behoerde": "Bundeszentralamt fuer Steuern",
        "behoerde_neu": 0,
        "zulassung_noetig": 0,
        "muster": "nachweis",
        "input_hash": "seed-erech-004",
        "erstgesehen": _tage_her(40),
        "zuletzt_geprueft": _tage_her(5),
        "score": 0.71,
        "score_hash": "seed-erech-004",
        "pflichten": [
            {
                "typ": "Formatpflicht",
                "gegenstand": "Ausstellen von B2B-Rechnungen im XRechnung-Format",
                "frequenz": "laufend",
            },
        ],
    },
    {
        "id": "dip:333005",
        "titel": "Achtes Gesetz zur Aenderung der Verbraucherinformationspflichten",
        "stadium": "tot",
        "quelle_url": "https://dip.bundestag.de/vorgang/-/333005",
        "anwendungsbeginn": None,
        "betroffene": 800,
        "einmalaufwand_eur": None,
        "erf_aufwand_eur": 12_000_000,
        "bussgeld_eur": None,
        "behoerde": None,
        "behoerde_neu": 0,
        "zulassung_noetig": 0,
        "muster": "keins",
        "input_hash": "seed-vip-005",
        "erstgesehen": _tage_her(120),
        "zuletzt_geprueft": _tage_her(10),
        "score": 0.15,
        "score_hash": "seed-vip-005",
        "pflichten": [],
    },
]


HISTORY = [
    # LkSG: Stadium-Wechsel neulich
    ("dip:333001", _tage_her(2), "stadium", "kabinett", "bt"),
    ("dip:333001", _tage_her(2), "erf_aufwand_eur", "280000000", "320000000"),
    # NIS2: erst gestern in den Ausschuss ueberwiesen
    ("dip:333002", _tage_her(1), "stadium", "bt", "ausschuss"),
    # KIVo: neu
    # E-Rechnung: verkuendet vor 5 Tagen
    ("dip:333004", _tage_her(5), "stadium", "bt", "verkuendet"),
]


def main() -> None:
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)

    # Alles alte platt machen (Preview-DB)
    con.execute("DELETE FROM pflicht")
    con.execute("DELETE FROM vorgang_history")
    con.execute("DELETE FROM vorgang")

    for v in VORGAENGE:
        pflichten = v.pop("pflichten")
        cols = ", ".join(v)
        marks = ", ".join("?" * len(v))
        con.execute(
            f"INSERT INTO vorgang ({cols}, quelle) VALUES ({marks}, ?)",
            (*v.values(), "dip"),
        )
        for p in pflichten:
            con.execute(
                "INSERT INTO pflicht (vorgang_id, typ, gegenstand, frequenz) VALUES (?, ?, ?, ?)",
                (v["id"], p["typ"], p["gegenstand"], p["frequenz"]),
            )

    for vid, ts, feld, alt, neu in HISTORY:
        con.execute(
            "INSERT INTO vorgang_history (vorgang_id, ts, feld, alt, neu) VALUES (?,?,?,?,?)",
            (vid, ts, feld, alt, neu),
        )

    con.commit()
    print(f"seed ok: {s.db_path}")
    print(f"  vorgaenge: {con.execute('SELECT COUNT(*) FROM vorgang').fetchone()[0]}")
    print(f"  pflichten: {con.execute('SELECT COUNT(*) FROM pflicht').fetchone()[0]}")
    print(f"  history:   {con.execute('SELECT COUNT(*) FROM vorgang_history').fetchone()[0]}")


if __name__ == "__main__":
    main()
