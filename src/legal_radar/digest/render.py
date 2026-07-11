"""Der Digest zeigt KEINEN Score. Er sortiert nur intern.

Sobald du eine Zahl siehst, faengst du an, ihr zu glauben.
"""

from __future__ import annotations

from legal_radar.digest.events import Event

TITEL = {
    "neu": "Neu im Radar",
    "fenster": "Fenster bewegt sich",
    "aufwand": "Aufwand geaendert",
    "stadium": "Stadienwechsel",
    "wettbewerb": "Wettbewerber aufgetaucht",
    "tot": "Gestorben",
}
ORDER = ["neu", "fenster", "aufwand", "stadium", "wettbewerb", "tot"]

DASHBOARD_URL = "https://philip3006.github.io/legal-radar/"
SEP = "-" * 50


def _summary(events: list[Event]) -> str:
    counts = {k: sum(1 for e in events if e.kind == k) for k in ORDER}
    teile = []
    if counts["neu"]:
        teile.append(f"{counts['neu']} neu")
    if counts["stadium"] or counts["fenster"]:
        teile.append(f"{counts['stadium'] + counts['fenster']} Wechsel")
    if counts["aufwand"]:
        teile.append(f"{counts['aufwand']} Aufwand-Update")
    if counts["tot"]:
        teile.append(f"{counts['tot']} gestorben")
    return ", ".join(teile) if teile else "nichts Neues"


def render(events: list[Event], kw: str) -> str:
    if not events:
        return f"LEGAL RADAR\n{kw} - nichts Neues.\n\nDashboard: {DASHBOARD_URL}\n"

    lines = [
        "LEGAL RADAR",
        f"{kw} - {_summary(events)}",
        SEP,
        "",
    ]

    for kind in ORDER:
        group = [e for e in events if e.kind == kind]
        if not group:
            continue
        lines.append(f"> {TITEL[kind]} ({len(group)})")
        lines.append("")
        for e in group:
            lines.append(f"  {e.titel}")
            lines.append(f"    {e.detail}")
            lines.append(f"    {e.url}")
            lines.append("")

    lines.append(SEP)
    lines.append(f"Dashboard: {DASHBOARD_URL}")
    return "\n".join(lines)
