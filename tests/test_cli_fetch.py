"""Integrationstest: DIP-Adapter + LLM sind gemockt, DB ist echt."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from legal_radar.core import db
from legal_radar.core.models import Vorgang

AUFWAND_TEXT = (
    "E.2 Erfuellungsaufwand fuer die Wirtschaft\n"
    "Der jaehrliche Aufwand betraegt 340 Mio. Euro.\n"
    "Die Aufsicht uebernimmt das Bundesamt fuer Sicherheit."
)
PREFILTER_MISS = "Irrelevanter Text ohne Verpflichtungen und ohne Zahlen."

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIP_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar.db"))
    (tmp_path / "migrations").symlink_to(REPO_ROOT / "migrations")
    return tmp_path


def _mk_vorgang(vid: str, titel: str) -> Vorgang:
    return Vorgang(
        id=f"dip:{vid}",
        quelle="dip",
        titel=titel,
        stadium="bt",
        quelle_url=f"https://dip.bundestag.de/vorgang/-/{vid}",
    )


def test_fetch_end_to_end(env, monkeypatch):
    from legal_radar import cli

    texte = {"dip:1": AUFWAND_TEXT, "dip:2": PREFILTER_MISS}

    monkeypatch.setattr(
        cli.Dip,
        "fetch",
        lambda self, since: [_mk_vorgang("1", "Treffer"), _mk_vorgang("2", "Fehlalarm")],
    )
    monkeypatch.setattr(cli.Dip, "text_fuer_vorgang", lambda self, vid: texte[vid])
    monkeypatch.setattr(
        cli.llm,
        "extract",
        lambda client, text, model="x": {"muster": "compliance"},
    )
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda **_: object())

    result = CliRunner().invoke(cli.app, ["fetch"])
    assert result.exit_code == 0, result.output
    assert "1 neu" in result.output
    assert "1 gefiltert" in result.output

    con = db.connect(env / "radar.db")
    rows = con.execute("SELECT id, muster FROM vorgang").fetchall()
    assert len(rows) == 1
    assert rows[0]["id"] == "dip:1"
    assert rows[0]["muster"] == "compliance"


def test_score_invalidiert_bei_neuem_input_hash(env, monkeypatch):
    """Erstes fetch+score setzt score_hash. Zweiter fetch mit neuem Text
    invalidiert den Score, aber ein zweiter fetch mit gleichem Text nicht.
    """
    from legal_radar import cli

    texte = {"dip:1": AUFWAND_TEXT}

    monkeypatch.setattr(cli.Dip, "fetch", lambda self, since: [_mk_vorgang("1", "T")])
    monkeypatch.setattr(cli.Dip, "text_fuer_vorgang", lambda self, vid: texte["dip:1"])
    monkeypatch.setattr(
        cli.llm,
        "extract",
        lambda client, text, model="x": {"muster": "compliance"},
    )
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda **_: object())

    runner = CliRunner()
    runner.invoke(cli.app, ["fetch"])
    runner.invoke(cli.app, ["score"])

    con = db.connect(env / "radar.db")
    ih1, sh1 = con.execute("SELECT input_hash, score_hash FROM vorgang").fetchone()
    assert ih1 == sh1

    # Text-Update -> anderer input_hash -> score_hash ist stale
    texte["dip:1"] = AUFWAND_TEXT + "\nJetzt sind es 500 Mio. Euro."
    runner.invoke(cli.app, ["fetch"])
    con = db.connect(env / "radar.db")
    ih2, sh2 = con.execute("SELECT input_hash, score_hash FROM vorgang").fetchone()
    assert ih2 != ih1
    assert sh2 == sh1  # score wurde noch nicht neu berechnet

    result = runner.invoke(cli.app, ["score"])
    assert "1 Vorgaenge zu bewerten" in result.output
    con = db.connect(env / "radar.db")
    ih3, sh3 = con.execute("SELECT input_hash, score_hash FROM vorgang").fetchone()
    assert sh3 == ih3


def test_fetch_nutzt_llm_cache(env, monkeypatch):
    """Zweiter Fetch mit gleichem Text darf llm.extract nicht aufrufen."""
    from legal_radar import cli

    monkeypatch.setattr(cli.Dip, "fetch", lambda self, since: [_mk_vorgang("1", "Treffer")])
    monkeypatch.setattr(cli.Dip, "text_fuer_vorgang", lambda self, vid: AUFWAND_TEXT)
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda **_: object())

    calls = {"n": 0}

    def counting_extract(client, text, model="x"):
        calls["n"] += 1
        return {"muster": "compliance"}

    monkeypatch.setattr(cli.llm, "extract", counting_extract)

    runner = CliRunner()
    runner.invoke(cli.app, ["fetch"])
    runner.invoke(cli.app, ["fetch"])

    assert calls["n"] == 1
