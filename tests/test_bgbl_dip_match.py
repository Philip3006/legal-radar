"""BGBl-Fetch: existierenden DIP-Vorgang updaten statt duplizieren."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from legal_radar.core import db
from legal_radar.core.models import Vorgang

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIP_API_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar.db"))
    (tmp_path / "migrations").symlink_to(REPO_ROOT / "migrations")
    return tmp_path


def _seed_dip(env_path: Path, vid: str, titel: str, stadium: str = "bt") -> None:
    con = db.connect(env_path / "radar.db")
    db.migrate(con)
    row = {
        "id": vid,
        "quelle": "dip",
        "titel": titel,
        "stadium": stadium,
        "quelle_url": f"http://dip/{vid}",
        "muster": "keins",
        "input_hash": f"hash-{vid}",
    }
    db.upsert(con, row)


def test_bgbl_titel_match_updated_dip_vorgang(env, monkeypatch):
    from legal_radar import cli

    _seed_dip(env, "dip:1", "Entwurf eines Gesetzes zur Regelung von XYZ", stadium="bt")

    bgbl_v = Vorgang(
        id="bgbl:abc",
        quelle="bgbl",
        titel="Gesetz zur Regelung von XYZ",
        stadium="verkuendet",
        quelle_url="http://recht.bund.de/eli/xyz",
        anwendungsbeginn=date(2026, 8, 1),
    )
    monkeypatch.setattr(cli.BgblRss, "fetch", lambda self, since: [bgbl_v])
    monkeypatch.setattr(cli.BgblRss, "text_fuer_vorgang", lambda self, vid: "")
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda **_: object())

    result = CliRunner().invoke(cli.app, ["fetch", "--source", "bgbl"])
    assert result.exit_code == 0, result.output

    con = db.connect(env / "radar.db")
    rows = con.execute("SELECT id, stadium, anwendungsbeginn FROM vorgang").fetchall()
    # nur EINE Zeile, dip:1, jetzt verkuendet
    assert len(rows) == 1
    assert rows[0]["id"] == "dip:1"
    assert rows[0]["stadium"] == "verkuendet"
    assert rows[0]["anwendungsbeginn"] == "2026-08-01"

    # History-Eintrag muss den Stadienwechsel dokumentieren
    hist = con.execute(
        "SELECT feld, alt, neu FROM vorgang_history WHERE vorgang_id = 'dip:1'"
    ).fetchall()
    stadium_ev = [h for h in hist if h["feld"] == "stadium"]
    assert stadium_ev == [{"feld": "stadium", "alt": "bt", "neu": "verkuendet"}] or (
        len(stadium_ev) == 1
        and stadium_ev[0]["alt"] == "bt"
        and stadium_ev[0]["neu"] == "verkuendet"
    )


def test_bgbl_ohne_match_legt_neuen_vorgang_an(env, monkeypatch):
    from legal_radar import cli

    _seed_dip(env, "dip:1", "Voellig anderes Thema", stadium="bt")

    bgbl_v = Vorgang(
        id="bgbl:xyz",
        quelle="bgbl",
        titel="Gesetz zur Regelung von XYZ",
        stadium="verkuendet",
        quelle_url="http://recht.bund.de/eli/xyz",
        anwendungsbeginn=date(2026, 8, 1),
    )
    monkeypatch.setattr(cli.BgblRss, "fetch", lambda self, since: [bgbl_v])
    monkeypatch.setattr(cli.BgblRss, "text_fuer_vorgang", lambda self, vid: "")
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda **_: object())

    CliRunner().invoke(cli.app, ["fetch", "--source", "bgbl"])

    con = db.connect(env / "radar.db")
    ids = {r["id"] for r in con.execute("SELECT id FROM vorgang")}
    assert ids == {"dip:1", "bgbl:xyz"}


def test_bgbl_ueberschreibt_kein_bereits_verkuendetes_dip(env, monkeypatch):
    """Vorgang, der schon 'verkuendet' ist, wird nicht erneut vom BGBl geriggert.
    (Der Match-Query schliesst verkuendete DIP-Vorgaenge aus.)
    """
    from legal_radar import cli

    _seed_dip(env, "dip:1", "Entwurf eines Gesetzes zur Regelung von XYZ", stadium="verkuendet")

    bgbl_v = Vorgang(
        id="bgbl:abc",
        quelle="bgbl",
        titel="Gesetz zur Regelung von XYZ",
        stadium="verkuendet",
        quelle_url="http://recht.bund.de/eli/xyz",
    )
    monkeypatch.setattr(cli.BgblRss, "fetch", lambda self, since: [bgbl_v])
    monkeypatch.setattr(cli.BgblRss, "text_fuer_vorgang", lambda self, vid: "")
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda **_: object())

    CliRunner().invoke(cli.app, ["fetch", "--source", "bgbl"])

    con = db.connect(env / "radar.db")
    ids = {r["id"] for r in con.execute("SELECT id FROM vorgang")}
    # BGBl bekommt eigenen Vorgang, weil DIP schon verkuendet ist
    assert ids == {"dip:1", "bgbl:abc"}
