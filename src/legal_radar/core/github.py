"""GitHub-Issues-API fuer die Watchlist.

Watchlist-Eintrag = offenes Issue mit Label 'watchlist' und einer Zeile
'vorgang_id: dip:XXX' im Body. Der Dashboard-Button oeffnet die 'Neues Issue'-
Seite mit diesen Feldern vorbelegt.
"""

from __future__ import annotations

import re

from legal_radar.core.http import get_json

_VORGANG_LINE = re.compile(r"^\s*vorgang_id\s*:\s*(\S+)\s*$", re.MULTILINE)
_STATUS_LINE = re.compile(r"^\s*status\s*:\s*(\S+)\s*$", re.MULTILINE)
ERLAUBTE_STATUS = {"interessant", "beobachten", "verworfen"}


def liste_watchlist_ids(repo: str, token: str | None) -> list[str]:
    """Rueckgabe: sortierte Liste eindeutiger Vorgangs-IDs auf der Watchlist.

    Bei fehlendem Token oder Repo: leere Liste (kein Fehler, so bleibt lokales
    Rendern ohne GitHub-Konfiguration moeglich).
    """
    if not repo or not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo}/issues"
    data = get_json(
        url, params={"labels": "watchlist", "state": "open", "per_page": 100}, headers=headers
    )

    ids: set[str] = set()
    for issue in data if isinstance(data, list) else []:
        body = issue.get("body") or ""
        m = _VORGANG_LINE.search(body)
        if m:
            ids.add(m.group(1))
    return sorted(ids)


def liste_bewertungen(repo: str, token: str | None) -> dict[str, str]:
    """{vorgang_id: status} aus offenen Issues mit Label 'bewertung'."""
    if not repo or not token:
        return {}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = get_json(
        f"https://api.github.com/repos/{repo}/issues",
        params={"labels": "bewertung", "state": "open", "per_page": 100},
        headers=headers,
    )
    out: dict[str, str] = {}
    for issue in data if isinstance(data, list) else []:
        body = issue.get("body") or ""
        vid_m = _VORGANG_LINE.search(body)
        st_m = _STATUS_LINE.search(body)
        if not (vid_m and st_m):
            continue
        status = st_m.group(1)
        if status not in ERLAUBTE_STATUS:
            continue
        out[vid_m.group(1)] = status
    return out
