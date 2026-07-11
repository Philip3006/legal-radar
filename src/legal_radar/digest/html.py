"""Statisches HTML-Dashboard aus DB-Stand. Kein Score sichtbar, sortiert intern."""

from __future__ import annotations

import html
import sqlite3
from datetime import date

STADIUM_LABEL = {
    "referentenentwurf": "Referentenentwurf",
    "kabinett": "Kabinett",
    "bt": "Bundestag",
    "ausschuss": "Ausschuss",
    "verkuendet": "Verkuendet",
    "anwendbar": "Anwendbar",
    "tot": "Gestorben",
}

# gruen = aktiv im Verfahren, gelb = im Parlament, grau = verkuendet, rot = tot
STADIUM_FARBE = {
    "referentenentwurf": "#eab308",
    "kabinett": "#eab308",
    "bt": "#f59e0b",
    "ausschuss": "#f59e0b",
    "verkuendet": "#6b7280",
    "anwendbar": "#16a34a",
    "tot": "#dc2626",
}

MUSTER_LABEL = {
    "compliance": "Compliance",
    "nachweis": "Nachweis",
    "vermittlung": "Vermittlung",
    "datenprodukt": "Datenprodukt",
    "keins": "-",
}


def _fmt_eur(v: int | None) -> str:
    if v is None:
        return "-"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f} Mrd EUR"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} Mio EUR"
    return f"{v:,} EUR".replace(",", ".")


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    r = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None


def _fmt_datum(iso: str | None) -> str:
    if not iso:
        return "offen"
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _card(row: sqlite3.Row, pflichten: list[sqlite3.Row]) -> str:
    stadium = row["stadium"] or "bt"
    farbe = STADIUM_FARBE.get(stadium, "#6b7280")
    stadium_txt = html.escape(STADIUM_LABEL.get(stadium, stadium))
    muster_txt = html.escape(MUSTER_LABEL.get(row["muster"] or "keins", "-"))
    titel = html.escape(row["titel"] or "")
    url = html.escape(row["quelle_url"] or "")
    aufwand = html.escape(_fmt_eur(row["erf_aufwand_eur"]))
    anwendung = html.escape(_fmt_datum(row["anwendungsbeginn"]))
    behoerde = html.escape(row["behoerde"] or "-")

    if pflichten:
        items = "".join(
            f"<li><strong>{html.escape(p['typ'])}</strong>: "
            f"{html.escape(p['gegenstand'])}"
            f"{' (' + html.escape(p['frequenz']) + ')' if p['frequenz'] else ''}"
            f"</li>"
            for p in pflichten
        )
        pflichten_block = f'<ul class="pflichten">{items}</ul>'
    else:
        pflichten_block = ""

    return f"""
    <article class="card">
      <div class="card-head">
        <span class="badge" style="background:{farbe}">{stadium_txt}</span>
        <span class="badge badge-outline">{muster_txt}</span>
      </div>
      <h2><a href="{url}" target="_blank" rel="noopener">{titel}</a></h2>
      <dl class="meta">
        <div><dt>Anwendung</dt><dd>{anwendung}</dd></div>
        <div><dt>Erfuellungsaufwand</dt><dd>{aufwand}</dd></div>
        <div><dt>Behoerde</dt><dd>{behoerde}</dd></div>
      </dl>
      {pflichten_block}
    </article>
    """


def render_html(con: sqlite3.Connection) -> str:
    rows = con.execute(
        """
        SELECT id, titel, stadium, muster, anwendungsbeginn, erf_aufwand_eur,
               behoerde, quelle_url, score
        FROM vorgang
        WHERE input_hash IS NOT NULL
        ORDER BY COALESCE(score, 0) DESC, titel ASC
        """
    ).fetchall()

    pflichten_by_vid: dict[str, list[sqlite3.Row]] = {}
    if _has_table(con, "pflicht"):
        for p in con.execute("SELECT vorgang_id, typ, gegenstand, frequenz FROM pflicht"):
            pflichten_by_vid.setdefault(p["vorgang_id"], []).append(p)

    stand = date.today().strftime("%d.%m.%Y")
    n = len(rows)
    cards = "\n".join(_card(r, pflichten_by_vid.get(r["id"], [])) for r in rows) or (
        '<p class="empty">Noch keine Vorgaenge im Radar.</p>'
    )

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Legal Radar</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #f5f6f8; --surface: #ffffff; --text: #111827; --muted: #6b7280;
    --border: #e5e7eb; --accent: #1f2937;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); margin: 0;
    line-height: 1.5;
  }}
  header {{
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 24px 32px;
  }}
  header h1 {{ margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.01em; }}
  header .sub {{ color: var(--muted); font-size: 14px; margin-top: 4px; }}
  main {{ max-width: 1000px; margin: 0 auto; padding: 32px; }}
  .cards {{ display: grid; gap: 16px; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 20px 24px;
  }}
  .card-head {{ display: flex; gap: 8px; margin-bottom: 8px; }}
  .card h2 {{
    margin: 4px 0 16px; font-size: 17px; font-weight: 600;
  }}
  .card h2 a {{ color: var(--text); text-decoration: none; }}
  .card h2 a:hover {{ text-decoration: underline; }}
  .badge {{
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 500; color: white;
  }}
  .badge-outline {{
    background: transparent !important; color: var(--muted);
    border: 1px solid var(--border);
  }}
  .meta {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
    margin: 0; font-size: 14px;
  }}
  .meta div {{ display: flex; flex-direction: column; }}
  .meta dt {{ color: var(--muted); font-size: 12px; text-transform: uppercase;
             letter-spacing: 0.03em; }}
  .meta dd {{ margin: 2px 0 0; font-weight: 500; }}
  .pflichten {{
    margin: 16px 0 0; padding: 12px 16px 12px 20px; list-style: disc;
    background: #f9fafb; border-radius: 6px; font-size: 14px;
  }}
  .pflichten li {{ margin: 2px 0; color: var(--text); }}
  .pflichten strong {{ color: var(--accent); font-weight: 600; }}
  .empty {{ color: var(--muted); text-align: center; padding: 48px; }}
  @media (max-width: 640px) {{
    .meta {{ grid-template-columns: 1fr 1fr; }}
    header, main {{ padding: 20px; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Legal Radar</h1>
  <div class="sub">Stand: {stand} &middot; {n} Vorgang{"e" if n != 1 else ""} im Radar</div>
</header>
<main>
  <div class="cards">
    {cards}
  </div>
</main>
</body>
</html>
"""
