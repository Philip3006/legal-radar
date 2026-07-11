from pathlib import Path

import pytest

from legal_radar.core import db
from legal_radar.digest.events import events_since
from legal_radar.digest.html import render_html
from legal_radar.digest.render import render


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
        "input_hash": "h1",
    }
    base.update(over)
    return base


def test_render_leerer_digest_zeigt_platzhalter():
    out = render([], kw="letzte 7 Tage")
    assert "nichts Neues" in out


def test_events_since_erkennt_stadium_wechsel(con):
    db.upsert(con, _row(stadium="bt"))
    db.upsert(con, _row(stadium="ausschuss"))
    events = events_since(con, 30)
    assert any(e.kind == "stadium" for e in events)


def test_html_zeigt_titel_und_link(con):
    db.upsert(con, _row(titel="Lieferkettengesetz", quelle_url="https://x.invalid/42"))
    html = render_html(con)
    assert "Lieferkettengesetz" in html
    assert "https://x.invalid/42" in html
    assert "<!doctype html>" in html


def test_html_bei_leerer_db_zeigt_platzhalter(con):
    html = render_html(con)
    assert "Noch keine Vorgaenge" in html
