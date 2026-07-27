"""sync-bewertungen spiegelt GitHub-Bewertungen in bewertung_user."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from legal_radar.core import db
from legal_radar.core.models import Vorgang

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIP_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar.db"))
    monkeypatch.setenv("GITHUB_TOKEN", "test")
    monkeypatch.setenv("RADAR_REPO", "test/repo")
    (tmp_path / "migrations").symlink_to(REPO_ROOT / "migrations")
    return tmp_path


def _seed_vorgang(env_path: Path, vid: str) -> None:
    con = db.connect(env_path / "radar.db")
    db.migrate(con)
    v = Vorgang(id=vid, quelle="dip", titel="Test", stadium="bt", quelle_url="http://x")
    row = {
        "id": v.id,
        "quelle": v.quelle,
        "titel": v.titel,
        "stadium": v.stadium,
        "quelle_url": v.quelle_url,
        "muster": "keins",
        "input_hash": "hash",
    }
    db.upsert(con, row)


def test_sync_schreibt_neue_bewertungen(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgang(env, "dip:1")
    _seed_vorgang(env, "dip:2")
    monkeypatch.setattr(
        cli.github,
        "liste_bewertungen",
        lambda repo, token: {"dip:1": "interessant", "dip:2": "verworfen"},
    )

    result = CliRunner().invoke(cli.app, ["sync-bewertungen"])
    assert result.exit_code == 0, result.output
    assert "2 neu" in result.output

    con = db.connect(env / "radar.db")
    rows = {r["vorgang_id"]: r["status"] for r in con.execute("SELECT * FROM bewertung_user")}
    assert rows == {"dip:1": "interessant", "dip:2": "verworfen"}


def test_sync_ist_idempotent_bei_gleichem_status(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgang(env, "dip:1")
    monkeypatch.setattr(cli.github, "liste_bewertungen", lambda r, t: {"dip:1": "interessant"})
    runner = CliRunner()
    runner.invoke(cli.app, ["sync-bewertungen"])
    result = runner.invoke(cli.app, ["sync-bewertungen"])
    assert "0 neu, 0 aktualisiert" in result.output


def test_sync_updated_bei_geaenderter_bewertung(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgang(env, "dip:1")
    state = {"status": "interessant"}
    monkeypatch.setattr(cli.github, "liste_bewertungen", lambda r, t: {"dip:1": state["status"]})
    runner = CliRunner()
    runner.invoke(cli.app, ["sync-bewertungen"])
    state["status"] = "verworfen"
    result = runner.invoke(cli.app, ["sync-bewertungen"])
    assert "0 neu, 1 aktualisiert" in result.output

    con = db.connect(env / "radar.db")
    row = con.execute("SELECT status FROM bewertung_user WHERE vorgang_id = 'dip:1'").fetchone()
    assert row["status"] == "verworfen"


def test_sync_ueberspringt_unbekannte_vorgang_ids(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgang(env, "dip:1")
    monkeypatch.setattr(
        cli.github,
        "liste_bewertungen",
        lambda r, t: {"dip:1": "interessant", "dip:phantom": "interessant"},
    )
    result = CliRunner().invoke(cli.app, ["sync-bewertungen"])
    assert "1 neu" in result.output
    assert "1 unbekannte" in result.output


def test_sync_leere_liste_meldet_nichts_zu_tun(env, monkeypatch):
    from legal_radar import cli

    monkeypatch.setattr(cli.github, "liste_bewertungen", lambda r, t: {})
    result = CliRunner().invoke(cli.app, ["sync-bewertungen"])
    assert "Nichts zu tun" in result.output
