"""GitHub-Issues-API fuer die Watchlist.

Watchlist-Eintrag = offenes Issue mit Label 'watchlist' und einer Zeile
'vorgang_id: dip:XXX' im Body. Der Dashboard-Button oeffnet die 'Neues Issue'-
Seite mit diesen Feldern vorbelegt.
"""

from __future__ import annotations

import re

from legal_radar.core.http import get_json

_VORGANG_LINE = re.compile(r"^\s*vorgang_id\s*:\s*(\S+)\s*$", re.MULTILINE)


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
    data = get_json(url, params={"labels": "watchlist", "state": "open", "per_page": 100},
                    headers=headers)

    ids: set[str] = set()
    for issue in data if isinstance(data, list) else []:
        body = issue.get("body") or ""
        m = _VORGANG_LINE.search(body)
        if m:
            ids.add(m.group(1))
    return sorted(ids)
