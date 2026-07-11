"""Der Digest zeigt KEINEN Score. Er sortiert nur intern.

Sobald du eine Zahl siehst, faengst du an, ihr zu glauben.
"""

from __future__ import annotations

from legal_radar.digest.events import Event

TITEL = {
    "fenster": "FENSTER BEWEGT SICH",
    "aufwand": "AUFWAND GEAENDERT",
    "stadium": "STADIENWECHSEL",
    "neu": "NEU IM RADAR",
    "wettbewerb": "WETTBEWERBER AUFGETAUCHT",
    "tot": "GESTORBEN",
}
ORDER = ["fenster", "aufwand", "stadium", "neu", "wettbewerb", "tot"]


def render(events: list[Event], kw: str) -> str:
    lines = [f"LEGAL RADAR — {kw}", ""]
    for kind in ORDER:
        group = [e for e in events if e.kind == kind]
        if not group:
            continue
        lines.append(f"{TITEL[kind]} ({len(group)})")
        for e in group:
            lines += [f"  · {e.titel}", f"    {e.detail}", f"    -> {e.url}"]
        lines.append("")
    return "\n".join(lines) if len(lines) > 2 else "LEGAL RADAR — nichts Neues.\n"
