"""LLM-Wochenzusammenfassung fuer die Summary-Card.

Ein Call/Woche, temperature=0, Cache in llm_cache-Tabelle.
Bei Fehlern: None zurueckgeben (Dashboard rendert dann ohne Summary-Card).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta

from legal_radar.core import db

MODEL = "claude-haiku-4-5-20251001"
MAX_KANDIDATEN = 20

SYSTEM = (
    "Du fasst eine Kalenderwoche deutsche Bundestags-Gesetzgebung fuer "
    "wirtschaftlich denkende Leser zusammen. Antworte in 3-5 klaren Saetzen. "
    "Keine Aufzaehlung, keine Marketing-Adjektive, kein 'wichtig' oder 'entscheidend'. "
    "Nenne konkret, welche Branchen oder Muster diese Woche in Bewegung sind, "
    "und woran ein Leser konkret denken sollte. Wenn nichts Relevantes passiert, "
    "sage das in einem Satz."
)


def _kandidaten(con: sqlite3.Connection) -> list[dict]:
    """Top-N Vorgaenge mit Bewegung oder Neuerscheinung diese Woche."""
    grenzdatum = (date.today() - timedelta(days=7)).isoformat()
    rows = con.execute(
        """
        SELECT id, titel, muster, stadium, anwendungsbeginn,
               erf_aufwand_eur, betroffene, behoerde,
               COALESCE(score, 0) AS score, erstgesehen
        FROM vorgang
        WHERE input_hash IS NOT NULL
          AND (
            erstgesehen >= ?
            OR id IN (
              SELECT DISTINCT vorgang_id FROM vorgang_history WHERE ts >= ?
            )
          )
        ORDER BY score DESC, erstgesehen DESC
        LIMIT ?
        """,
        (grenzdatum, grenzdatum, MAX_KANDIDATEN),
    ).fetchall()
    return [dict(r) for r in rows]


def _cache_key(kandidaten: list[dict]) -> str:
    heute = date.today()
    kw = heute.isocalendar()
    ids = sorted(k["id"] for k in kandidaten)
    h = hashlib.sha256(f"summary:{kw[0]}-{kw[1]}:{','.join(ids)}".encode()).hexdigest()
    return f"summary:{h}"


def _user_message(kandidaten: list[dict]) -> str:
    zeilen = []
    for k in kandidaten:
        aufwand = k["erf_aufwand_eur"]
        aufwand_txt = f"{aufwand / 1_000_000:.0f} Mio EUR/J" if aufwand else "-"
        zeilen.append(
            f"- {k['titel'][:120]} "
            f"[muster={k['muster'] or '-'}, stadium={k['stadium'] or '-'}, "
            f"aufwand={aufwand_txt}, anwendung={k['anwendungsbeginn'] or '-'}]"
        )
    if not zeilen:
        return "Diese Woche waren keine Vorgaenge im Radar. Bitte melde das."
    return (
        "Kandidaten dieser Woche (sortiert nach interner Relevanz):\n\n"
        + "\n".join(zeilen)
        + "\n\nDeine 3-5 Saetze:"
    )


def erzeuge_summary(con: sqlite3.Connection, client) -> str | None:
    """Rueckgabe: Summary-Text oder None (wenn nichts, Cache-Fehler, oder API-Fehler)."""
    kandidaten = _kandidaten(con)
    if not kandidaten:
        return None

    ck = _cache_key(kandidaten)
    cached = db.cached_llm(con, ck)
    if cached:
        try:
            return json.loads(cached)["text"]
        except (KeyError, json.JSONDecodeError):
            pass  # Cache kaputt, neu erzeugen

    if client is None:
        return None

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            temperature=0,
            system=SYSTEM,
            messages=[{"role": "user", "content": _user_message(kandidaten)}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
    except Exception:
        return None

    if not text:
        return None

    db.put_llm(con, ck, json.dumps({"text": text}))
    return text
