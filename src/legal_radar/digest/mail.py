"""HTML-Mail-Rendering fuer den wochentlichen Digest.

Inline Styles - Gmail & Outlook strippen <style>-Bloecke sonst.
Table-Layout - alte Clients ignorieren Flexbox/Grid.
Feste 600px Breite - Standard fuer Newsletter.
"""

from __future__ import annotations

import html

from legal_radar.digest.events import Event

DASHBOARD_URL = "https://philip3006.github.io/legal-radar/"

TITEL = {
    "neu": "Neu im Radar",
    "fenster": "Fenster bewegt sich",
    "aufwand": "Aufwand geaendert",
    "stadium": "Stadienwechsel",
    "wettbewerb": "Wettbewerber aufgetaucht",
    "tot": "Gestorben",
}
ORDER = ["neu", "fenster", "aufwand", "stadium", "wettbewerb", "tot"]

# Akzentfarbe pro Ereignisart (linker Rand jeder Karte)
FARBE = {
    "neu": "#2563eb",
    "fenster": "#f59e0b",
    "aufwand": "#f59e0b",
    "stadium": "#f59e0b",
    "wettbewerb": "#7c3aed",
    "tot": "#dc2626",
}

_TEXT = "#111827"
_MUTED = "#6b7280"
_BORDER = "#e5e7eb"
_BG = "#f5f6f8"
_SURFACE = "#ffffff"
_ACCENT = "#1f2937"


def _card(e: Event) -> str:
    farbe = FARBE.get(e.kind, "#6b7280")
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin-bottom:12px;border-collapse:collapse;">
      <tr>
        <td style="background:{_SURFACE};border:1px solid {_BORDER};
                   border-left:4px solid {farbe};border-radius:6px;
                   padding:16px 20px;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;
                      color:{farbe};font-weight:600;margin-bottom:6px;">
            {html.escape(TITEL.get(e.kind, e.kind))}
          </div>
          <div style="font-size:15px;font-weight:600;color:{_TEXT};
                      margin-bottom:6px;line-height:1.35;">
            {html.escape(e.titel)}
          </div>
          <div style="font-size:13px;color:{_MUTED};margin-bottom:10px;">
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
        teile.append(f"<strong>{counts['neu']}</strong> neu")
    wechsel = counts.get("stadium", 0) + counts.get("fenster", 0)
    if wechsel:
        teile.append(f"<strong>{wechsel}</strong> Wechsel")
    if counts.get("aufwand"):
        teile.append(f"<strong>{counts['aufwand']}</strong> Aufwand-Update")
    if counts.get("tot"):
        teile.append(f"<strong>{counts['tot']}</strong> gestorben")
    return " &middot; ".join(teile) or "nichts Neues"


def render_mail(events: list[Event], kw: str) -> str:
    summary = _summary_zeile(events)

    if not events:
        body_inner = f"""
        <p style="color:{_MUTED};text-align:center;padding:32px 0;font-size:14px;">
          Diese Woche keine relevanten Aenderungen im Radar.
        </p>
        """
    else:
        parts = []
        for kind in ORDER:
            group = [e for e in events if e.kind == kind]
            if not group:
                continue
            parts.append(
                f'<div style="font-size:12px;text-transform:uppercase;'
                f'letter-spacing:0.06em;color:{_MUTED};font-weight:600;'
                f'margin:24px 0 8px;padding:0 4px;">'
                f'{html.escape(TITEL[kind])} ({len(group)})</div>'
            )
            parts.extend(_card(e) for e in group)
        body_inner = "\n".join(parts)

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legal Radar - {html.escape(kw)}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:{_BG};border-collapse:collapse;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;border-collapse:collapse;">

        <!-- Header -->
        <tr>
          <td style="background:{_SURFACE};border:1px solid {_BORDER};
                     border-radius:8px;padding:24px 28px;">
            <div style="font-size:20px;font-weight:600;color:{_TEXT};
                        letter-spacing:-0.01em;">Legal Radar</div>
            <div style="font-size:14px;color:{_MUTED};margin-top:4px;">
              {html.escape(kw)} &middot; {summary}
            </div>
            <div style="margin-top:14px;">
              <a href="{DASHBOARD_URL}"
                 style="display:inline-block;background:{_ACCENT};color:#fff;
                        text-decoration:none;font-size:13px;font-weight:500;
                        padding:8px 16px;border-radius:6px;">
                Dashboard oeffnen &rarr;
              </a>
            </div>
          </td>
        </tr>

        <!-- Spacer -->
        <tr><td style="height:20px;line-height:20px;font-size:0;">&nbsp;</td></tr>

        <!-- Body -->
        <tr>
          <td>
            {body_inner}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:24px 12px;text-align:center;color:{_MUTED};font-size:12px;">
            Automatisch generiert &middot;
            <a href="{DASHBOARD_URL}" style="color:{_MUTED};">Dashboard</a>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""
