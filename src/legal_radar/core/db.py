"""SQLite + Historisierung. Jede Feldaenderung wird append-only protokolliert."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

TRACKED = (
    "stadium",
    "anwendungsbeginn",
    "erf_aufwand_eur",
    "einmalaufwand_eur",
    "betroffene",
    "bussgeld_eur",
    "behoerde",
    "muster",
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def migrate(con: sqlite3.Connection, migrations: Path = Path("migrations")) -> None:
    """Fuehrt jede *.sql genau einmal aus. Reihenfolge = Dateiname."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, ts TEXT NOT NULL)"
    )
    done = {r[0] for r in con.execute("SELECT name FROM schema_migrations")}
    for f in sorted(migrations.glob("*.sql")):
        if f.name in done:
            continue
        con.executescript(f.read_text(encoding="utf-8"))
        con.execute(
            "INSERT INTO schema_migrations (name, ts) VALUES (?, ?)",
            (f.name, date.today().isoformat()),
        )
    con.commit()


def upsert(con: sqlite3.Connection, row: dict) -> list[tuple[str, str | None, str | None]]:
    """Schreibt den Vorgang und gibt die geaenderten Felder zurueck.

    Die Rueckgabe ist das, woraus digest/events.py die Ereignisse baut.
    """
    today = date.today().isoformat()
    old = con.execute("SELECT * FROM vorgang WHERE id = ?", (row["id"],)).fetchone()

    if old is None:
        cols = ", ".join(row)
        marks = ", ".join("?" * len(row))
        con.execute(
            f"INSERT INTO vorgang ({cols}, erstgesehen, zuletzt_geprueft) VALUES ({marks}, ?, ?)",
            (*row.values(), today, today),
        )
        con.commit()
        return [("__neu__", None, row["titel"])]

    changes: list[tuple[str, str | None, str | None]] = []
    for feld in TRACKED:
        if feld not in row:
            continue
        alt, neu = old[feld], row[feld]
        if str(alt) != str(neu):
            changes.append(
                (
                    feld,
                    None if alt is None else str(alt),
                    None if neu is None else str(neu),
                )
            )
            con.execute(
                "INSERT INTO vorgang_history (vorgang_id, ts, feld, alt, neu) VALUES (?,?,?,?,?)",
                (row["id"], today, feld, str(alt), str(neu)),
            )

    sets = ", ".join(f"{k} = ?" for k in row if k != "id")
    con.execute(
        f"UPDATE vorgang SET {sets}, zuletzt_geprueft = ? WHERE id = ?",
        (*[v for k, v in row.items() if k != "id"], today, row["id"]),
    )
    con.commit()
    return changes


def cached_llm(con: sqlite3.Connection, input_hash: str) -> str | None:
    r = con.execute("SELECT payload FROM llm_cache WHERE input_hash = ?", (input_hash,)).fetchone()
    return r["payload"] if r else None


def put_llm(con: sqlite3.Connection, input_hash: str, payload: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO llm_cache (input_hash, payload, ts) VALUES (?,?,?)",
        (input_hash, payload, date.today().isoformat()),
    )
    con.commit()
