"""GitHub-API-Client blaettert alle Seiten - sonst fehlen Bewertungen ab Nr. 101."""

from __future__ import annotations

from legal_radar.core import github


def _issue(vid: str, label: str = "watchlist", status: str = "interessant") -> dict:
    if label == "bewertung":
        body = f"vorgang_id: {vid}\nstatus: {status}\n"
    else:
        body = f"vorgang_id: {vid}\n"
    return {"body": body}


def test_liste_watchlist_ids_paginiert(monkeypatch):
    seiten = {
        1: [_issue(f"dip:{i}") for i in range(100)],
        2: [_issue("dip:extra")],
        3: [],
    }

    def fake_get_json(url, params, headers):
        return seiten.get(params["page"], [])

    monkeypatch.setattr(github, "get_json", fake_get_json)
    ids = github.liste_watchlist_ids("test/repo", "token")
    assert len(ids) == 101
    assert "dip:extra" in ids


def test_liste_bewertungen_paginiert(monkeypatch):
    seiten = {
        1: [_issue(f"dip:{i}", label="bewertung") for i in range(100)],
        2: [_issue("dip:letzte", label="bewertung", status="verworfen")],
    }

    def fake_get_json(url, params, headers):
        return seiten.get(params["page"], [])

    monkeypatch.setattr(github, "get_json", fake_get_json)
    result = github.liste_bewertungen("test/repo", "token")
    assert len(result) == 101
    assert result["dip:letzte"] == "verworfen"


def test_bricht_bei_teilweise_gefuellter_seite_ab(monkeypatch):
    """Weniger als 100 Items = letzte Seite, kein weiterer Call."""
    calls = []

    def fake_get_json(url, params, headers):
        calls.append(params["page"])
        return [_issue("dip:1")] if params["page"] == 1 else []

    monkeypatch.setattr(github, "get_json", fake_get_json)
    github.liste_watchlist_ids("test/repo", "token")
    assert calls == [1]
