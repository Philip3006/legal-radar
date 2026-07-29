"""Health-Check-Command: fuenf Einzelchecks, jeder isoliert testbar."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # backup-Check uebergeht dann
    (tmp_path / "migrations").symlink_to(REPO_ROOT / "migrations")
    return tmp_path


def _seed_vorgaenge(env_path: Path, n: int) -> None:
    con = db.connect(env_path / "radar.db")
    db.migrate(con)
    for i in range(n):
        v = Vorgang(id=f"dip:{i}", quelle="dip", titel=f"T{i}", stadium="bt", quelle_url="x")
        db.upsert(
            con,
            {
                "id": v.id,
                "quelle": v.quelle,
                "titel": v.titel,
                "stadium": v.stadium,
                "quelle_url": v.quelle_url,
                "muster": "keins",
                "input_hash": f"h{i}",
            },
        )


def _rejected_mit_run(env_path: Path, alter_tage: float) -> None:
    p = env_path / "data" / "rejected.jsonl"
    p.parent.mkdir(exist_ok=True)
    ts = (datetime.now(UTC) - timedelta(days=alter_tage)).isoformat()
    p.write_text(json.dumps({"event": "run_start", "ts": ts, "source": "dip"}) + "\n")


def _mock_worker_ok(monkeypatch):
    from legal_radar import cli

    monkeypatch.setattr(cli, "_check_worker", lambda: (True, "Worker OK"))


def test_health_alle_gruen(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgaenge(env, 600)
    _rejected_mit_run(env, alter_tage=2)
    _mock_worker_ok(monkeypatch)
    result = CliRunner().invoke(cli.app, ["health"])
    assert result.exit_code == 0, result.output
    assert "all green" in result.output


def test_health_db_zu_wenig_vorgaenge(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgaenge(env, 100)  # < 500
    _rejected_mit_run(env, alter_tage=1)
    _mock_worker_ok(monkeypatch)
    result = CliRunner().invoke(cli.app, ["health"])
    assert result.exit_code == 1
    assert "FAIL" in result.output and "db" in result.output


def test_health_cron_zu_alt(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgaenge(env, 600)
    _rejected_mit_run(env, alter_tage=10)  # > 8
    _mock_worker_ok(monkeypatch)
    result = CliRunner().invoke(cli.app, ["health"])
    assert result.exit_code == 1
    assert "cron_aktuell" in result.output


def test_health_worker_kaputt(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgaenge(env, 600)
    _rejected_mit_run(env, alter_tage=1)
    monkeypatch.setattr(cli, "_check_worker", lambda: (False, "Worker HTTP 502"))
    result = CliRunner().invoke(cli.app, ["health"])
    assert result.exit_code == 1
    assert "worker" in result.output and "502" in result.output


def test_health_json_output(env, monkeypatch):
    from legal_radar import cli

    _seed_vorgaenge(env, 600)
    _rejected_mit_run(env, alter_tage=1)
    _mock_worker_ok(monkeypatch)
    result = CliRunner().invoke(cli.app, ["health", "--json"])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["all_green"] is True
    erwartet = {"db", "cron_aktuell", "backup_aktuell", "worker", "bewertungs_sync"}
    assert set(report.keys()) >= erwartet
