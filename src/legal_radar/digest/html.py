"""Statisches HTML-Dashboard. Kein JS.

Filter via :checked-Radio-Buttons, Onboarding via <details>.
Score bleibt intern (nur Sortierung), wird nirgendwo angezeigt.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import date, timedelta

STADIUM_LABEL = {
    "referentenentwurf": "Referentenentwurf",
    "kabinett": "Kabinett",
    "bt": "Bundestag",
    "ausschuss": "Ausschuss",
    "verkuendet": "Verkuendet",
    "anwendbar": "Anwendbar",
    "tot": "Gestorben",
}

STADIUM_FARBE = {
    "referentenentwurf": "#eab308",
    "kabinett": "#eab308",
    "bt": "#f59e0b",
    "ausschuss": "#f59e0b",
    "verkuendet": "#6b7280",
    "anwendbar": "#16a34a",
    "tot": "#dc2626",
}

# Welche Stadien in welcher Gruppen-Sektion landen (Reihenfolge = Anzeige-Reihenfolge)
GRUPPEN = [
    ("aktiv", "Im Verfahren", ["referentenentwurf", "kabinett", "bt", "ausschuss"]),
    ("anwendbar", "Anwendbar / Verkuendet", ["anwendbar", "verkuendet"]),
    ("tot", "Gestorben", ["tot"]),
]

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


def _fmt_zahl(v: int | None) -> str:
    if v is None:
        return "-"
    return f"{v:,}".replace(",", ".")


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


def _gruppe_fuer_stadium(stadium: str) -> str:
    for key, _label, stadien in GRUPPEN:
        if stadium in stadien:
            return key
    return "aktiv"


def _card(row: sqlite3.Row, pflichten: list[sqlite3.Row], is_neu: bool = False) -> str:
    stadium = row["stadium"] or "bt"
    farbe = STADIUM_FARBE.get(stadium, "#6b7280")
    stadium_txt = html.escape(STADIUM_LABEL.get(stadium, stadium))
    muster_key = row["muster"] or "keins"
    muster_txt = html.escape(MUSTER_LABEL.get(muster_key, "-"))
    titel = html.escape(row["titel"] or "")
    url = html.escape(row["quelle_url"] or "")
    aufwand = html.escape(_fmt_eur(row["erf_aufwand_eur"]))
    anwendung = html.escape(_fmt_datum(row["anwendungsbeginn"]))
    behoerde = html.escape(row["behoerde"] or "-")
    betroffene = html.escape(_fmt_zahl(row["betroffene"]) if "betroffene" in row.keys() else "-")

    if pflichten:
        items = "".join(
            f"<li><strong>{html.escape(p['typ'])}</strong>: "
            f"{html.escape(p['gegenstand'])}"
            f"{' &middot; ' + html.escape(p['frequenz']) if p['frequenz'] else ''}"
            f"</li>"
            for p in pflichten
        )
        pflichten_block = f'<ul class="pflichten">{items}</ul>'
    else:
        pflichten_block = ""

    neu_badge = '<span class="badge badge-neu">Neu</span>' if is_neu else ""

    return f"""
    <article class="card" data-stadium="{stadium}" data-muster="{muster_key}">
      <div class="card-head">
        <span class="badge" style="background:{farbe}">{stadium_txt}</span>
        <span class="badge badge-outline">{muster_txt}</span>
        {neu_badge}
      </div>
      <h2><a href="{url}" target="_blank" rel="noopener">{titel}</a></h2>
      <dl class="meta">
        <div><dt>Anwendung</dt><dd>{anwendung}</dd></div>
        <div><dt>Erfuellungsaufwand</dt><dd>{aufwand}</dd></div>
        <div><dt>Betroffene</dt><dd>{betroffene}</dd></div>
        <div><dt>Behoerde</dt><dd>{behoerde}</dd></div>
      </dl>
      {pflichten_block}
    </article>
    """


def _events_diese_woche(con: sqlite3.Connection, tage: int = 7) -> dict[str, list[dict]]:
    """{vorgang_id: [event, ...]} fuer alles was in den letzten `tage` Tagen passiert ist."""
    if not _has_table(con, "vorgang_history"):
        return {}
    rows = con.execute(
        """
        SELECT vorgang_id, feld, alt, neu, ts
        FROM vorgang_history
        WHERE ts >= date('now', ?)
        ORDER BY ts DESC
        """,
        (f"-{tage} days",),
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["vorgang_id"], []).append(dict(r))
    return out


def _event_label(ev: dict) -> str:
    feld, alt, neu = ev["feld"], ev["alt"], ev["neu"]
    if feld == "stadium":
        alt_txt = STADIUM_LABEL.get(alt, alt or "?")
        neu_txt = STADIUM_LABEL.get(neu, neu or "?")
        return f"Stadium: {alt_txt} &rarr; {neu_txt}"
    if feld == "erf_aufwand_eur":
        return f"Aufwand: {_fmt_eur(int(alt) if alt else None)} &rarr; {_fmt_eur(int(neu) if neu else None)}"
    if feld == "anwendungsbeginn":
        return f"Anwendungsbeginn: {_fmt_datum(alt)} &rarr; {_fmt_datum(neu)}"
    return f"{html.escape(feld)}: {html.escape(str(alt))} &rarr; {html.escape(str(neu))}"


def _neu_sektion(rows: list[sqlite3.Row], events: dict[str, list[dict]]) -> str:
    neu_ids = set()
    grenzdatum = (date.today() - timedelta(days=7)).isoformat()
    for r in rows:
        if r["erstgesehen"] and r["erstgesehen"] >= grenzdatum:
            neu_ids.add(r["id"])
    neu_ids.update(events.keys())

    if not neu_ids:
        return ""

    row_by_id = {r["id"]: r for r in rows}
    items = []
    for vid in neu_ids:
        r = row_by_id.get(vid)
        if not r:
            continue
        titel = html.escape(r["titel"] or "")
        url = html.escape(r["quelle_url"] or "")
        ev_list = events.get(vid, [])
        is_neu_ganz = r["erstgesehen"] and r["erstgesehen"] >= grenzdatum

        details = []
        if is_neu_ganz and not ev_list:
            details.append("Neu im Radar")
        for ev in ev_list[:3]:
            details.append(_event_label(ev))
        detail_txt = " &middot; ".join(details)

        items.append(
            f'<li><a href="{url}" target="_blank" rel="noopener">{titel}</a>'
            f'<span class="ev-detail">{detail_txt}</span></li>'
        )

    return f"""
    <section class="neu-sektion">
      <h2>Neu diese Woche <span class="count">({len(items)})</span></h2>
      <ul class="ev-list">
        {"".join(items)}
      </ul>
    </section>
    """


def _gruppen_sektionen(rows: list[sqlite3.Row], pflichten: dict) -> str:
    out_parts = []
    for key, label, stadien in GRUPPEN:
        gruppe_rows = [r for r in rows if (r["stadium"] or "bt") in stadien]
        if not gruppe_rows:
            continue
        cards = "\n".join(_card(r, pflichten.get(r["id"], [])) for r in gruppe_rows)
        out_parts.append(
            f'<section class="gruppe gruppe-{key}">'
            f'<h2 class="gruppe-titel">{label} '
            f'<span class="count">({len(gruppe_rows)})</span></h2>'
            f'<div class="cards">{cards}</div>'
            f"</section>"
        )
    return "\n".join(out_parts) or '<p class="empty">Noch keine Vorgaenge im Radar.</p>'


def render_html(con: sqlite3.Connection) -> str:
    rows = con.execute(
        """
        SELECT id, titel, stadium, muster, anwendungsbeginn, erf_aufwand_eur,
               behoerde, quelle_url, score, betroffene, erstgesehen
        FROM vorgang
        WHERE input_hash IS NOT NULL
        ORDER BY COALESCE(score, 0) DESC, titel ASC
        """
    ).fetchall()

    pflichten_by_vid: dict[str, list[sqlite3.Row]] = {}
    if _has_table(con, "pflicht"):
        for p in con.execute("SELECT vorgang_id, typ, gegenstand, frequenz FROM pflicht"):
            pflichten_by_vid.setdefault(p["vorgang_id"], []).append(p)

    events = _events_diese_woche(con)

    stand = date.today().strftime("%d.%m.%Y")
    n = len(rows)

    neu_sektion = _neu_sektion(rows, events)
    gruppen = _gruppen_sektionen(rows, pflichten_by_vid)

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Legal Radar</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #f5f6f8; --surface: #ffffff; --text: #111827; --muted: #6b7280;
    --border: #e5e7eb; --accent: #1f2937; --accent-soft: #eef2ff;
    --neu: #2563eb;
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
  header .titelzeile {{ display: flex; align-items: baseline; justify-content: space-between;
                       flex-wrap: wrap; gap: 12px; max-width: 1000px; margin: 0 auto; }}
  header h1 {{ margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.01em; }}
  header .sub {{ color: var(--muted); font-size: 14px; }}

  details.info {{
    max-width: 1000px; margin: 12px auto 0; padding: 0;
    font-size: 14px;
  }}
  details.info summary {{
    cursor: pointer; color: var(--neu); font-weight: 500;
    padding: 4px 0; user-select: none;
  }}
  details.info summary::-webkit-details-marker {{ display: none; }}
  details.info summary::before {{ content: "› "; display: inline-block;
    transition: transform 0.15s; }}
  details.info[open] summary::before {{ transform: rotate(90deg); }}
  details.info .info-body {{
    background: var(--accent-soft); border-radius: 8px; padding: 16px 20px;
    margin-top: 8px; color: var(--text);
  }}
  details.info .info-body p {{ margin: 0 0 8px; }}
  details.info .info-body p:last-child {{ margin: 0; }}
  details.info .info-body strong {{ color: var(--accent); }}

  main {{ max-width: 1000px; margin: 0 auto; padding: 24px 32px 48px; }}

  .filter-bar {{
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px;
  }}
  .filter-bar input[type=radio] {{ position: absolute; opacity: 0; pointer-events: none; }}
  .filter-bar label {{
    padding: 6px 14px; border: 1px solid var(--border); border-radius: 999px;
    background: var(--surface); font-size: 13px; cursor: pointer; user-select: none;
    color: var(--text);
  }}
  .filter-bar label:hover {{ background: #f3f4f6; }}
  #f-all:checked ~ .filter-bar label[for=f-all],
  #f-aktiv:checked ~ .filter-bar label[for=f-aktiv],
  #f-anwendbar:checked ~ .filter-bar label[for=f-anwendbar],
  #f-tot:checked ~ .filter-bar label[for=f-tot],
  #f-compliance:checked ~ .filter-bar label[for=f-compliance],
  #f-nachweis:checked ~ .filter-bar label[for=f-nachweis] {{
    background: var(--accent); color: white; border-color: var(--accent);
  }}

  /* Filter-Logik: default alle sichtbar */
  #f-aktiv:checked ~ main .card {{ display: none; }}
  #f-aktiv:checked ~ main .card[data-stadium="referentenentwurf"],
  #f-aktiv:checked ~ main .card[data-stadium="kabinett"],
  #f-aktiv:checked ~ main .card[data-stadium="bt"],
  #f-aktiv:checked ~ main .card[data-stadium="ausschuss"] {{ display: block; }}
  #f-aktiv:checked ~ main .gruppe-anwendbar,
  #f-aktiv:checked ~ main .gruppe-tot {{ display: none; }}

  #f-anwendbar:checked ~ main .card {{ display: none; }}
  #f-anwendbar:checked ~ main .card[data-stadium="anwendbar"],
  #f-anwendbar:checked ~ main .card[data-stadium="verkuendet"] {{ display: block; }}
  #f-anwendbar:checked ~ main .gruppe-aktiv,
  #f-anwendbar:checked ~ main .gruppe-tot {{ display: none; }}

  #f-tot:checked ~ main .card {{ display: none; }}
  #f-tot:checked ~ main .card[data-stadium="tot"] {{ display: block; }}
  #f-tot:checked ~ main .gruppe-aktiv,
  #f-tot:checked ~ main .gruppe-anwendbar {{ display: none; }}

  #f-compliance:checked ~ main .card {{ display: none; }}
  #f-compliance:checked ~ main .card[data-muster="compliance"] {{ display: block; }}
  #f-nachweis:checked ~ main .card {{ display: none; }}
  #f-nachweis:checked ~ main .card[data-muster="nachweis"] {{ display: block; }}

  .neu-sektion {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 20px 24px; margin-bottom: 24px;
    border-left: 4px solid var(--neu);
  }}
  .neu-sektion h2 {{ margin: 0 0 12px; font-size: 15px; font-weight: 600;
                    text-transform: uppercase; letter-spacing: 0.04em; color: var(--neu); }}
  .neu-sektion .count {{ color: var(--muted); font-weight: 400; }}
  .ev-list {{ list-style: none; padding: 0; margin: 0; }}
  .ev-list li {{ padding: 8px 0; border-top: 1px solid var(--border); }}
  .ev-list li:first-child {{ border-top: none; padding-top: 0; }}
  .ev-list a {{ color: var(--text); font-weight: 500; text-decoration: none; }}
  .ev-list a:hover {{ text-decoration: underline; }}
  .ev-detail {{ display: block; color: var(--muted); font-size: 13px; margin-top: 2px; }}

  .gruppe {{ margin-bottom: 32px; }}
  .gruppe-titel {{ font-size: 13px; font-weight: 600; color: var(--muted);
                   text-transform: uppercase; letter-spacing: 0.06em;
                   margin: 0 0 12px; padding-left: 4px; }}
  .gruppe-titel .count {{ font-weight: 400; }}

  .cards {{ display: grid; gap: 12px; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 20px 24px;
  }}
  .card-head {{ display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
  .card h2 {{ margin: 4px 0 16px; font-size: 17px; font-weight: 600; }}
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
  .badge-neu {{
    background: var(--neu) !important; color: white;
  }}
  .meta {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
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
  footer {{ max-width: 1000px; margin: 0 auto; padding: 24px 32px 48px;
            color: var(--muted); font-size: 12px; text-align: center; }}

  @media (max-width: 640px) {{
    .meta {{ grid-template-columns: 1fr 1fr; }}
    header, main, footer {{ padding-left: 20px; padding-right: 20px; }}
  }}
</style>
</head>
<body>
<input type="radio" name="filter" id="f-all" checked>
<input type="radio" name="filter" id="f-aktiv">
<input type="radio" name="filter" id="f-anwendbar">
<input type="radio" name="filter" id="f-tot">
<input type="radio" name="filter" id="f-compliance">
<input type="radio" name="filter" id="f-nachweis">

<header>
  <div class="titelzeile">
    <h1>Legal Radar</h1>
    <div class="sub">Stand: {stand} &middot; {n} Vorgang{"e" if n != 1 else ""} im Radar</div>
  </div>
  <details class="info">
    <summary>Was ist das hier?</summary>
    <div class="info-body">
      <p><strong>Legal Radar</strong> beobachtet Gesetzgebungsverfahren des Deutschen
      Bundestages und meldet fruehzeitig, welche neuen Pflichten, Aufwaende oder
      Marktchancen entstehen koennten.</p>
      <p>Die Karten unten zeigen jeweils <strong>Titel &amp; Link zum Vorgang</strong>,
      das aktuelle <strong>Stadium</strong>, das erkannte <strong>Muster</strong>
      (Compliance, Nachweis, Vermittlung, Datenprodukt), sowie
      <strong>Anwendungsbeginn</strong>, <strong>Erfuellungsaufwand</strong> und die
      resultierenden <strong>Pflichten</strong> - falls das Vorblatt der Drucksache
      diese Angaben enthaelt.</p>
      <p>Ganz oben findest du <strong>&quot;Neu diese Woche&quot;</strong>: alles was
      in den letzten 7 Tagen neu ins Radar kam oder wo sich der Status geaendert hat.</p>
      <p>Mit den <strong>Filter-Buttons</strong> kannst du die Ansicht auf ein
      bestimmtes Verfahrensstadium oder Muster einschraenken. Sortierung innerhalb
      der Sektionen ist bewusst nicht sichtbar - das System priorisiert intern.</p>
    </div>
  </details>
</header>
<main>
  <div class="filter-bar">
    <label for="f-all">Alle</label>
    <label for="f-aktiv">Im Verfahren</label>
    <label for="f-anwendbar">Anwendbar</label>
    <label for="f-tot">Gestorben</label>
    <span style="width:12px"></span>
    <label for="f-compliance">Compliance</label>
    <label for="f-nachweis">Nachweis</label>
  </div>

  {neu_sektion}
  {gruppen}
</main>
<footer>
  Automatisch aktualisiert &middot;
  <a href="https://github.com/Philip3006/legal-radar" style="color:inherit">Quelle</a>
</footer>
</body>
</html>
"""
