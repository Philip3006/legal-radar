"""HTML-Mail-Rendering. Dark-Layout, inline styles.

Zwei Varianten:
- render_mail:            wochendigest (weiss/neutral abgesetzt vom radar)
- render_watchlist_mail:  taegliche watchlist-mail (amber-akzent, klar abgesetzt)
"""

from __future__ import annotations

import html

from legal_radar.digest.events import Event

DASHBOARD_URL = "https://philip3006.github.io/legal-radar/"

TITEL = {
    "neu": "Neu im Radar",
    "fenster": "Fenster bewegt sich",
    "aufwand": "Aufwand geändert",
    "stadium": "Stadienwechsel",
    "wettbewerb": "Wettbewerber aufgetaucht",
    "tot": "Eingestellt",
}
ORDER = ["neu", "fenster", "aufwand", "stadium", "wettbewerb", "tot"]

FARBE = {
    "neu": "#3b82f6",
    "fenster": "#f59e0b",
    "aufwand": "#f59e0b",
    "stadium": "#f59e0b",
    "wettbewerb": "#a78bfa",
    "tot": "#ef4444",
}

# Dark-Palette (fest, kein prefers-color-scheme - Mail-Clients unzuverlaessig)
_BG = "#0a0a0a"
_SURFACE = "#141414"
_TEXT = "#f5f5f5"
_SOFT = "#a3a3a3"
_MUTED = "#737373"
_BORDER = "#262626"
_ACCENT = "#10b981"
_AMBER = "#f59e0b"


def _card(e: Event) -> str:
    farbe = FARBE.get(e.kind, _MUTED)
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin-bottom:10px;border-collapse:collapse;">
      <tr>
        <td style="background:{_SURFACE};border:1px solid {_BORDER};
                   border-left:3px solid {farbe};border-radius:12px;
                   padding:18px 22px;
                   font-family:-apple-system,'Segoe UI',Roboto,sans-serif;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;
                      color:{farbe};font-weight:600;margin-bottom:8px;">
            {html.escape(TITEL.get(e.kind, e.kind))}
          </div>
          <div style="font-size:15px;font-weight:600;color:{_TEXT};
                      margin-bottom:6px;line-height:1.4;letter-spacing:-0.005em;">
            {html.escape(e.titel)}
          </div>
          <div style="font-size:13px;color:{_SOFT};margin-bottom:12px;
                      font-variant-numeric:tabular-nums;">
            {html.escape(e.detail)}
          </div>
          <div>
            <a href="{html.escape(e.url)}"
               style="color:{farbe};text-decoration:none;font-size:13px;font-weight:500;">
              Zum Vorgang &rarr;
            </a>
          </div>
        </td>
      </tr>
    </table>
    """


def _summary_zeile(events: list[Event]) -> str:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    teile = []
    if counts.get("neu"):
        teile.append(f"<strong style='color:{_TEXT}'>{counts['neu']}</strong> neu")
    wechsel = counts.get("stadium", 0) + counts.get("fenster", 0)
    if wechsel:
        teile.append(f"<strong style='color:{_TEXT}'>{wechsel}</strong> Wechsel")
    if counts.get("aufwand"):
        teile.append(f"<strong style='color:{_TEXT}'>{counts['aufwand']}</strong> Aufwand-Update")
    if counts.get("tot"):
        teile.append(f"<strong style='color:{_TEXT}'>{counts['tot']}</strong> eingestellt")
    return " &middot; ".join(teile) or "Keine relevanten Änderungen"


def _body_inner(events: list[Event]) -> str:
    if not events:
        return f"""
        <p style="color:{_MUTED};text-align:center;padding:40px 0;font-size:14px;">
          Diese Woche keine relevanten Änderungen im Radar.
        </p>
        """
    parts = []
    for kind in ORDER:
        group = [e for e in events if e.kind == kind]
        if not group:
            continue
        parts.append(
            f'<div style="font-size:11px;text-transform:uppercase;'
            f"letter-spacing:0.08em;color:{_MUTED};font-weight:600;"
            f'margin:24px 0 10px;padding:0 4px;">'
            f"{html.escape(TITEL[kind])} ({len(group)})</div>"
        )
        parts.extend(_card(e) for e in group)
    return "\n".join(parts)


def _shell(
    headline: str, subline: str, body_inner: str, accent_color: str, button_label: str
) -> str:
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark only">
<title>Legal Radar</title>
</head>
<body bgcolor="{_BG}" style="margin:0;padding:0;background:{_BG};
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
             color:{_TEXT};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       bgcolor="{_BG}" style="background:{_BG};border-collapse:collapse;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;border-collapse:collapse;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:{_SURFACE};border:1px solid {_BORDER};
                     border-radius:14px;padding:28px 30px;position:relative;">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;
                        color:{accent_color};font-weight:600;margin-bottom:8px;">
              {html.escape(headline)}
            </div>
            <div style="font-size:22px;font-weight:600;color:{_TEXT};
                        letter-spacing:-0.02em;line-height:1.2;">
              {subline}
            </div>
            <div style="margin-top:20px;">
              <a href="{DASHBOARD_URL}"
                 style="display:inline-block;background:{_TEXT};color:{_BG};
                        text-decoration:none;font-size:13px;font-weight:600;
                        padding:10px 18px;border-radius:8px;letter-spacing:-0.005em;">
                {html.escape(button_label)} &rarr;
              </a>
            </div>
          </td>
        </tr>

        <tr><td style="height:16px;line-height:16px;font-size:0;">&nbsp;</td></tr>

        <tr>
          <td>
            {body_inner}
          </td>
        </tr>

        <tr>
          <td style="padding:28px 12px 8px;text-align:center;color:{_MUTED};font-size:12px;">
            Automatisch generiert &nbsp;·&nbsp;
            <a href="{DASHBOARD_URL}" style="color:{_SOFT};text-decoration:none;">Dashboard</a>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


def render_mail(events: list[Event], kw: str) -> str:
    subline = f"{_summary_zeile(events)}"
    return _shell(
        headline=f"Legal Radar &nbsp;·&nbsp; {html.escape(kw)}",
        subline=subline,
        body_inner=_body_inner(events),
        accent_color=_ACCENT,
        button_label="Dashboard oeffnen",
    )


def render_watchlist_mail(events: list[Event], kw: str) -> str:
    n_ids = len({e.vorgang_id for e in events})
    subline = (
        f"{n_ids} Vorgang{'e' if n_ids != 1 else ''} deiner Watchlist "
        f"{'haben' if n_ids != 1 else 'hat'} sich bewegt"
    )
    return _shell(
        headline=f"Watchlist &nbsp;·&nbsp; {html.escape(kw)}",
        subline=subline,
        body_inner=_body_inner(events),
        accent_color=_AMBER,
        button_label="Watchlist oeffnen",
    )
