from pathlib import Path

import pytest

from legal_radar.core import db


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.migrate(c, migrations=Path("migrations"))
    return c


def _row(**over) -> dict:
    base = {
        "id": "dip:1",
        "quelle": "dip",
        "titel": "Testgesetz",
        "stadium": "bt",
        "quelle_url": "https://example.invalid/1",
        "erf_aufwand_eur": 100_000_000,
        "muster": "compliance",
        "input_hash": "abc123",
    }
    base.update(over)
    return base


def test_upsert_neu_liefert_neu_marker(con):
    changes = db.upsert(con, _row())
    assert changes == [("__neu__", None, "Testgesetz")]


def test_upsert_unveraendert_ohne_history(con):
    db.upsert(con, _row())
    changes = db.upsert(con, _row())
    assert changes == []


def test_upsert_erkennt_stadium_wechsel(con):
    db.upsert(con, _row(stadium="bt"))
    changes = db.upsert(con, _row(stadium="ausschuss"))
    assert ("stadium", "bt", "ausschuss") in changes


def test_upsert_schreibt_history_zeile(con):
    db.upsert(con, _row(erf_aufwand_eur=100_000_000))
    db.upsert(con, _row(erf_aufwand_eur=250_000_000))
    rows = con.execute("SELECT feld, alt, neu FROM vorgang_history").fetchall()
    assert (rows[0]["feld"], rows[0]["alt"], rows[0]["neu"]) == (
        "erf_aufwand_eur",
        "100000000",
        "250000000",
    )


def test_llm_cache_round_trip(con):
    assert db.cached_llm(con, "hash1") is None
    db.put_llm(con, "hash1", '{"muster": "compliance"}')
    assert db.cached_llm(con, "hash1") == '{"muster": "compliance"}'
