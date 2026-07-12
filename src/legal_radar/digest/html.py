"""Statisches HTML-Dashboard. Kein JS.

Aesthetik: Modern-Dark, Linear/Vercel-inspired.
Struktur: Header -> Filter -> Summary-Card -> Watchlist-Rubrik -> Neu diese Woche
          -> Gruppen nach Stadium -> Footer.

Filter via :checked-Radio-Buttons, Onboarding via <details>, Watchlist via
GitHub Issues (Klick oeffnet Issue-Formular vorbelegt).
"""

from __future__ import annotations

import html
import json
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
    "referentenentwurf": "#f59e0b",
    "kabinett": "#f59e0b",
    "bt": "#f59e0b",
    "ausschuss": "#f59e0b",
    "verkuendet": "#737373",
    "anwendbar": "#10b981",
    "tot": "#ef4444",
}

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

TOP_N_NEU = 5


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


def _fmt_datum(iso: str | None) -> str:
    if not iso:
        return "offen"
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    r = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None


def _watchlist_action(row: sqlite3.Row, watched: set[str]) -> str:
    if row["id"] in watched:
        return '<span class="watch-badge" title="Auf deiner Watchlist">★ Auf Watchlist</span>'
    # data-Attribute für das JS unten. Klick öffnet KEIN GitHub mehr,
    # sondern schickt POST an den Watch-Worker.
    vid = html.escape(row["id"])
    titel_attr = html.escape((row["titel"] or "").replace('"', "'"), quote=True)
    return (
        f'<button type="button" class="watch-add" '
        f'data-vorgang="{vid}" data-titel="{titel_attr}" '
        f'title="Auf Watchlist setzen">+ Merken</button>'
    )


def _card(row: sqlite3.Row, pflichten: list[sqlite3.Row], is_neu: bool, watched: set[str]) -> str:
    stadium = row["stadium"] or "bt"
    farbe = STADIUM_FARBE.get(stadium, "#737373")
    stadium_txt = html.escape(STADIUM_LABEL.get(stadium, stadium))
    muster_key = row["muster"] or "keins"
    muster_txt = html.escape(MUSTER_LABEL.get(muster_key, "-"))
    titel = html.escape(row["titel"] or "")
    url = html.escape(row["quelle_url"] or "")
    aufwand = html.escape(_fmt_eur(row["erf_aufwand_eur"]))
    anwendung = html.escape(_fmt_datum(row["anwendungsbeginn"]))
    behoerde = html.escape(row["behoerde"] or "-")
    try:
        betroffene_val = row["betroffene"]
    except (IndexError, KeyError):
        betroffene_val = None
    betroffene = html.escape(_fmt_zahl(betroffene_val))

    pflichten_block = ""
    if pflichten:
        items = "".join(
            f"<li><strong>{html.escape(p['typ'])}</strong>: "
            f"{html.escape(p['gegenstand'])}"
            f"{
                ' <span class=freq>' + html.escape(p['frequenz']) + '</span>'
                if p['frequenz']
                else ''
            }"
            f"</li>"
            for p in pflichten
        )
        pflichten_block = f'<ul class="pflichten">{items}</ul>'

    neu_badge = '<span class="badge badge-neu">Neu</span>' if is_neu else ""
    watch_action = _watchlist_action(row, watched)

    # Kompakte Kern-Info: Aufwand (linke Seite) + Anwendung (rechte Seite)
    quick_bits = []
    if row["erf_aufwand_eur"]:
        quick_bits.append(f'<span class="q-aufwand">{aufwand}</span>')
    if row["anwendungsbeginn"]:
        quick_bits.append(f'<span class="q-anwendung">ab {anwendung}</span>')
    quick_meta = f'<div class="card-quickmeta">{" · ".join(quick_bits)}</div>' if quick_bits else ""

    return f"""
    <details class="card" data-stadium="{stadium}" data-muster="{muster_key}">
      <summary class="card-summary">
        <div class="card-summary-main">
          <div class="card-badges">
            <span class="badge" style="--dot:{farbe}">{stadium_txt}</span>
            <span class="badge badge-outline">{muster_txt}</span>
            {neu_badge}
          </div>
          <h3 class="card-titel">{titel}</h3>
          {quick_meta}
        </div>
        <span class="card-chevron" aria-hidden="true"></span>
      </summary>
      <div class="card-body">
        <dl class="meta">
          <div><dt>Anwendung</dt><dd>{anwendung}</dd></div>
          <div><dt>Erfuellungsaufwand</dt><dd>{aufwand}</dd></div>
          <div><dt>Betroffene</dt><dd>{betroffene}</dd></div>
          <div><dt>Behoerde</dt><dd>{behoerde}</dd></div>
        </dl>
        {pflichten_block}
        <div class="card-footer">
          <a class="card-link" href="{url}" target="_blank" rel="noopener">
            Zum Vorgang &rarr;
          </a>
          {watch_action}
        </div>
      </div>
    </details>
    """


def _summary_card(summary_text: str | None, counts: dict[str, int], n_total: int) -> str:
    if not summary_text:
        return ""
    ct_bits = []
    if counts.get("neu"):
        ct_bits.append(f"<strong>{counts['neu']}</strong> neu")
    wechsel = counts.get("stadium", 0) + counts.get("fenster", 0)
    if wechsel:
        ct_bits.append(f"<strong>{wechsel}</strong> Wechsel")
    if counts.get("aufwand"):
        ct_bits.append(f"<strong>{counts['aufwand']}</strong> Aufwand-Update")
    ct_line = " &middot; ".join(ct_bits) or f"{n_total} Vorgaenge im Radar"

    return f"""
    <section class="summary-card">
      <div class="summary-label">Zusammenfassung diese Woche</div>
      <p class="summary-text">{html.escape(summary_text)}</p>
      <div class="summary-counts">{ct_line}</div>
    </section>
    """


def _watchlist_sektion(rows: list[sqlite3.Row], pflichten: dict, watched: set[str]) -> str:
    if not watched:
        return ""
    wrows = [r for r in rows if r["id"] in watched]
    if not wrows:
        return (
            '<section class="rubrik watchlist-rubrik">'
            '<h2 class="rubrik-titel">★ Meine Watchlist</h2>'
            '<p class="empty-inline">Deine Watchlist ist gesetzt, aber die Vorgaenge '
            "sind derzeit nicht im Radar. Vielleicht sind sie gestorben oder aus dem "
            "Fetch-Fenster gefallen.</p>"
            "</section>"
        )
    cards = "\n".join(_card(r, pflichten.get(r["id"], []), False, watched) for r in wrows)
    return f"""
    <section class="rubrik watchlist-rubrik">
      <h2 class="rubrik-titel">★ Meine Watchlist <span class="count">({len(wrows)})</span></h2>
      <div class="cards cards-watchlist">{cards}</div>
    </section>
    """


def _events_diese_woche(con: sqlite3.Connection, tage: int = 7) -> dict[str, list[dict]]:
    if not _has_table(con, "vorgang_history"):
        return {}
    rows = con.execute(
        "SELECT vorgang_id, feld, alt, neu, ts FROM vorgang_history "
        "WHERE ts >= date('now', ?) ORDER BY ts DESC",
        (f"-{tage} days",),
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["vorgang_id"], []).append(dict(r))
    return out


def _event_counts(events: dict[str, list[dict]], neu_ids: set[str]) -> dict[str, int]:
    counts = {"neu": len(neu_ids), "stadium": 0, "fenster": 0, "aufwand": 0, "tot": 0}
    for ev_list in events.values():
        for ev in ev_list:
            if ev["feld"] == "stadium":
                counts["tot" if ev["neu"] == "tot" else "stadium"] += 1
            elif ev["feld"] == "erf_aufwand_eur":
                counts["aufwand"] += 1
            elif ev["feld"] == "anwendungsbeginn":
                counts["fenster"] += 1
    return counts


def _neu_sektion(
    rows: list[sqlite3.Row],
    pflichten: dict,
    events: dict[str, list[dict]],
    watched: set[str],
) -> str:
    grenzdatum = (date.today() - timedelta(days=7)).isoformat()
    neu_rows = [r for r in rows if r["erstgesehen"] and r["erstgesehen"] >= grenzdatum]

    # Rows, die zwar nicht "neu" sind, aber ein Event der Woche haben
    aenderungs_ids = set(events.keys()) - {r["id"] for r in neu_rows}
    aenderungs_rows = [r for r in rows if r["id"] in aenderungs_ids]

    if not neu_rows and not aenderungs_rows:
        return ""

    kombiniert = neu_rows + aenderungs_rows
    # Nach Score sortiert (rows sind schon so sortiert)
    top = kombiniert[:TOP_N_NEU]
    rest = kombiniert[TOP_N_NEU:]

    top_cards = "\n".join(_card(r, pflichten.get(r["id"], []), True, watched) for r in top)
    rest_block = ""
    if rest:
        rest_cards = "\n".join(_card(r, pflichten.get(r["id"], []), True, watched) for r in rest)
        rest_block = f"""
        <details class="rest-fold">
          <summary>Alle {len(rest)} weiteren aus dieser Woche anzeigen</summary>
          <div class="cards">{rest_cards}</div>
        </details>
        """

    return f"""
    <section class="rubrik neu-rubrik">
      <h2 class="rubrik-titel">Neu diese Woche
        <span class="count">({len(kombiniert)})</span>
      </h2>
      <div class="cards">{top_cards}</div>
      {rest_block}
    </section>
    """


def _gruppen_sektionen(rows: list[sqlite3.Row], pflichten: dict, watched: set[str]) -> str:
    out_parts = []
    for key, label, stadien in GRUPPEN:
        gruppe_rows = [r for r in rows if (r["stadium"] or "bt") in stadien]
        if not gruppe_rows:
            continue
        cards = "\n".join(_card(r, pflichten.get(r["id"], []), False, watched) for r in gruppe_rows)
        out_parts.append(
            f'<section class="gruppe gruppe-{key}">'
            f'<h2 class="gruppe-titel">{label} '
            f'<span class="count">({len(gruppe_rows)})</span></h2>'
            f'<div class="cards">{cards}</div>'
            f"</section>"
        )
    return "\n".join(out_parts) or '<p class="empty">Noch keine Vorgaenge im Radar.</p>'


def render_html(
    con: sqlite3.Connection,
    summary_text: str | None = None,
    watched_ids: set[str] | None = None,
    radar_repo: str = "Philip3006/legal-radar",
    watch_endpoint: str = "",
    watch_token: str = "",
) -> str:
    watched = watched_ids or set()

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
    grenzdatum = (date.today() - timedelta(days=7)).isoformat()
    neu_ids = {r["id"] for r in rows if r["erstgesehen"] and r["erstgesehen"] >= grenzdatum}
    counts = _event_counts(events, neu_ids)

    stand = date.today().strftime("%d.%m.%Y")
    n = len(rows)

    summary_html = _summary_card(summary_text, counts, n)
    watchlist_html = _watchlist_sektion(rows, pflichten_by_vid, watched)
    neu_html = _neu_sektion(rows, pflichten_by_vid, events, watched)
    gruppen_html = _gruppen_sektionen(rows, pflichten_by_vid, watched)

    return _shell(
        stand,
        n,
        summary_html,
        watchlist_html,
        neu_html,
        gruppen_html,
        watch_endpoint,
        watch_token,
        radar_repo,
    )


def _shell(
    stand: str,
    n: int,
    summary: str,
    watchlist: str,
    neu: str,
    gruppen: str,
    watch_endpoint: str,
    watch_token: str,
    radar_repo: str,
) -> str:
    watch_endpoint_js = json.dumps(watch_endpoint)
    watch_token_js = json.dumps(watch_token)
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Legal Radar</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<link rel="preconnect" href="https://rsms.me/">
<link rel="stylesheet" href="https://rsms.me/inter/inter.css">
<style>
  :root {{
    color-scheme: dark;
    --bg: #0a0a0a;
    --surface: #141414;
    --surface-2: #1a1a1a;
    --text: #f5f5f5;
    --text-soft: #a3a3a3;
    --muted: #737373;
    --border: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.14);
    --accent: #10b981;
    --accent-soft: rgba(16,185,129,0.12);
    --neu: #3b82f6;
    --amber: #f59e0b;
    --red: #ef4444;
    --radius: 14px;
    --radius-sm: 8px;
  }}

  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0;
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text",
                 "Segoe UI", Roboto, sans-serif;
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
    font-size: 15px; line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }}
  @supports (font-variation-settings: normal) {{
    body {{ font-family: "Inter var", -apple-system, sans-serif; }}
  }}

  a {{ color: inherit; }}

  header {{
    padding: 40px 32px 24px;
    border-bottom: 1px solid var(--border);
  }}
  .header-inner {{ max-width: 1100px; margin: 0 auto; }}
  .titelzeile {{ display: flex; align-items: baseline; justify-content: space-between;
                 flex-wrap: wrap; gap: 12px; }}
  h1 {{
    margin: 0; font-size: 30px; font-weight: 600;
    letter-spacing: -0.025em; line-height: 1.1;
  }}
  .sub {{ color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }}

  details.info {{ margin-top: 20px; font-size: 14px; }}
  details.info summary {{
    cursor: pointer; color: var(--text-soft); font-weight: 500;
    padding: 4px 0; user-select: none; list-style: none;
  }}
  details.info summary::-webkit-details-marker {{ display: none; }}
  details.info summary::before {{
    content: "\\203A"; display: inline-block; margin-right: 6px;
    color: var(--muted); transition: transform 150ms ease;
  }}
  details.info[open] summary::before {{ transform: rotate(90deg); color: var(--accent); }}
  details.info .info-body {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px 24px; margin-top: 12px;
    color: var(--text-soft);
  }}
  details.info .info-body p {{ margin: 0 0 10px; }}
  details.info .info-body p:last-child {{ margin: 0; }}
  details.info .info-body strong {{ color: var(--text); font-weight: 500; }}

  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 32px 64px; }}

  /* Filter-Bar: sticky, blur */
  .filter-bar-wrap {{
    position: sticky; top: 0; z-index: 10;
    background: color-mix(in oklab, var(--bg) 88%, transparent);
    backdrop-filter: saturate(180%) blur(20px);
    -webkit-backdrop-filter: saturate(180%) blur(20px);
    margin: 0 -32px 32px; padding: 12px 32px;
    border-bottom: 1px solid var(--border);
  }}
  .filter-bar {{
    max-width: 1100px; margin: 0 auto;
    display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
  }}
  .filter-bar input[type=radio] {{ position: absolute; opacity: 0; pointer-events: none; }}
  .filter-bar label {{
    padding: 6px 14px; border: 1px solid var(--border); border-radius: 999px;
    background: transparent; font-size: 13px; cursor: pointer;
    color: var(--text-soft); font-weight: 500;
    transition: all 150ms ease;
  }}
  .filter-bar label:hover {{
    background: var(--surface); color: var(--text); border-color: var(--border-strong);
  }}
  #f-all:checked ~ * label[for=f-all],
  #f-aktiv:checked ~ * label[for=f-aktiv],
  #f-anwendbar:checked ~ * label[for=f-anwendbar],
  #f-tot:checked ~ * label[for=f-tot],
  #f-compliance:checked ~ * label[for=f-compliance],
  #f-nachweis:checked ~ * label[for=f-nachweis] {{
    background: var(--text); color: var(--bg); border-color: var(--text);
  }}
  .filter-bar .filter-sep {{ width: 1px; height: 20px; background: var(--border);
                             margin: 0 6px; }}

  /* Filter-Logik */
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

  /* Summary-Card */
  .summary-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 24px 28px; margin-bottom: 24px;
    position: relative; overflow: hidden;
  }}
  .summary-card::before {{
    content: ""; position: absolute; inset: 0 auto 0 0; width: 3px;
    background: linear-gradient(180deg, var(--accent), var(--neu));
  }}
  .summary-label {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--muted); font-weight: 600; margin-bottom: 10px;
  }}
  .summary-text {{
    margin: 0; font-size: 17px; line-height: 1.55; color: var(--text);
    font-weight: 400; max-width: 68ch;
  }}
  .summary-counts {{
    margin-top: 14px; font-size: 13px; color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .summary-counts strong {{ color: var(--text); font-weight: 600; }}

  /* Rubrik = Section-Wrapper */
  .rubrik {{ margin-bottom: 32px; }}
  .rubrik-titel {{
    font-size: 14px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted);
    margin: 0 0 16px; padding-left: 2px;
  }}
  .rubrik-titel .count {{ color: var(--muted); font-weight: 400; }}

  .neu-rubrik .rubrik-titel {{ color: var(--neu); }}
  .watchlist-rubrik .rubrik-titel {{ color: var(--amber); }}

  /* Gruppen */
  .gruppe {{ margin-bottom: 40px; }}
  .gruppe-titel {{
    font-size: 12px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--muted);
    margin: 0 0 14px; padding-left: 2px;
  }}
  .gruppe-titel .count {{ font-weight: 400; }}

  /* Cards - collapsible, kompakt by default */
  .cards {{ display: grid; gap: 8px; }}
  .cards-watchlist {{ gap: 8px; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius);
    transition: border-color 150ms ease, background 150ms ease;
    overflow: hidden;
  }}
  .card:hover {{
    border-color: var(--border-strong);
    background: var(--surface-2);
  }}
  .card[open] {{
    border-color: var(--border-strong);
    background: var(--surface-2);
  }}

  .card-summary {{
    display: flex; align-items: center; gap: 12px;
    padding: 14px 18px; cursor: pointer;
    list-style: none;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
  }}
  .card-summary::-webkit-details-marker {{ display: none; }}
  .card-summary::marker {{ display: none; content: ""; }}
  .card-summary-main {{ flex: 1; min-width: 0; }}

  .card-badges {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }}

  .card-titel {{
    margin: 0; font-size: 15px; font-weight: 600;
    letter-spacing: -0.005em; line-height: 1.4; color: var(--text);
    /* Auf Mobile max 2 Zeilen, dann Ellipse */
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
  }}

  .card-quickmeta {{
    margin-top: 6px; font-size: 12px; color: var(--muted);
    font-variant-numeric: tabular-nums;
    display: flex; gap: 6px; flex-wrap: wrap;
  }}
  .card-quickmeta .q-aufwand {{ color: var(--text-soft); font-weight: 500; }}

  .card-chevron {{
    flex-shrink: 0; width: 24px; height: 24px;
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); transition: transform 200ms ease;
  }}
  .card-chevron::before {{
    content: ""; display: block; width: 8px; height: 8px;
    border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor;
    transform: rotate(45deg) translate(-2px, -2px);
  }}
  .card[open] .card-chevron {{ color: var(--accent); transform: rotate(180deg); }}

  .card-body {{
    padding: 4px 18px 18px;
    border-top: 1px solid var(--border);
    margin-top: 2px;
  }}

  .card-footer {{
    display: flex; justify-content: space-between; align-items: center;
    gap: 10px; margin-top: 16px; padding-top: 14px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
  }}
  .card-link {{
    color: var(--accent); text-decoration: none; font-size: 13px;
    font-weight: 500;
  }}
  .card-link:hover {{ text-decoration: underline; }}

  .badge {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px 3px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 500; color: var(--text-soft);
    background: var(--surface-2); border: 1px solid var(--border);
    letter-spacing: 0.01em;
  }}
  .badge::before {{
    content: ""; width: 6px; height: 6px; border-radius: 50%;
    background: var(--dot, var(--muted));
  }}
  .badge-outline {{ background: transparent; }}
  .badge-outline::before {{ display: none; }}
  .badge-neu {{
    background: var(--accent-soft); color: var(--accent);
    border-color: rgba(16,185,129,0.3);
  }}
  .badge-neu::before {{ background: var(--accent); }}

  .watch-add, .watch-badge {{
    font-size: 12px; padding: 4px 10px; border-radius: 6px;
    font-weight: 500; white-space: nowrap;
  }}
  .watch-add {{
    color: var(--muted); text-decoration: none;
    border: 1px solid var(--border); background: transparent;
    transition: all 150ms ease;
  }}
  .watch-add:hover {{ color: var(--amber); border-color: var(--amber);
                      background: rgba(245,158,11,0.08); }}
  .watch-badge {{ color: var(--amber); background: rgba(245,158,11,0.1);
                  border: 1px solid rgba(245,158,11,0.25); }}

  .meta {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
    margin: 16px 0 0; font-size: 13px;
    font-variant-numeric: tabular-nums;
  }}
  .meta div {{ display: flex; flex-direction: column; min-width: 0; }}
  .meta dt {{
    color: var(--muted); font-size: 10px; text-transform: uppercase;
    letter-spacing: 0.08em; font-weight: 500; margin-bottom: 4px;
  }}
  .meta dd {{ margin: 0; font-weight: 500; color: var(--text); }}

  .pflichten {{
    margin: 16px 0 0; padding: 12px 16px 12px 20px;
    background: var(--bg); border-radius: var(--radius-sm);
    list-style: disc; font-size: 13px;
    color: var(--text-soft);
  }}
  .pflichten li {{ margin: 3px 0; }}
  .pflichten strong {{ color: var(--text); font-weight: 600; }}
  .pflichten .freq {{ color: var(--muted); font-size: 12px; }}

  /* Details/Rest-Fold */
  .rest-fold {{ margin-top: 16px; }}
  .rest-fold summary {{
    cursor: pointer; color: var(--text-soft); font-size: 13px;
    padding: 10px 14px; border-radius: var(--radius-sm);
    background: var(--surface); border: 1px solid var(--border);
    list-style: none; user-select: none;
    transition: all 150ms ease;
  }}
  .rest-fold summary::-webkit-details-marker {{ display: none; }}
  .rest-fold summary::before {{
    content: "▸"; margin-right: 8px; color: var(--muted);
    display: inline-block; transition: transform 150ms ease;
  }}
  .rest-fold[open] summary::before {{ transform: rotate(90deg); }}
  .rest-fold summary:hover {{ background: var(--surface-2); color: var(--text); }}
  .rest-fold[open] > .cards {{ margin-top: 10px; }}

  .empty, .empty-inline {{
    color: var(--muted); font-size: 14px; padding: 24px 0;
  }}
  .empty {{ text-align: center; padding: 64px 0; }}

  footer {{
    max-width: 1100px; margin: 0 auto; padding: 32px;
    color: var(--muted); font-size: 12px; text-align: center;
    border-top: 1px solid var(--border);
  }}
  footer a {{ color: var(--text-soft); text-decoration: none; }}
  footer a:hover {{ color: var(--text); }}

  @media (max-width: 720px) {{
    header {{ padding: 28px 18px 16px; }}
    main {{ padding: 18px 18px 48px; }}
    .filter-bar-wrap {{ margin: 0 -18px 20px; padding: 10px 18px; }}
    h1 {{ font-size: 22px; }}
    .summary-card {{ padding: 18px 20px; }}
    .summary-text {{ font-size: 15px; }}
    .card-summary {{ padding: 12px 14px; gap: 8px; }}
    .card-titel {{ font-size: 14px; }}
    .card-quickmeta {{ font-size: 11px; }}
    .card-body {{ padding: 4px 14px 14px; }}
    .meta {{ grid-template-columns: 1fr 1fr; gap: 12px; font-size: 12px; }}
    .card-footer {{ flex-direction: column-reverse; align-items: stretch; gap: 8px; }}
    .card-footer .card-link {{ text-align: center; padding: 8px;
                               border: 1px solid var(--border); border-radius: 8px; }}
    .watch-add, .watch-badge {{ text-align: center; }}
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
  <div class="header-inner">
    <div class="titelzeile">
      <h1>Legal Radar</h1>
      <div class="sub">Stand {stand} &nbsp;·&nbsp; {n} Vorgang{"e" if n != 1 else ""}</div>
    </div>
    <details class="info">
      <summary>Was ist das hier?</summary>
      <div class="info-body">
        <p><strong>Legal Radar</strong> beobachtet Bundestags-Gesetzgebung und
        meldet fruehzeitig, welche neuen Pflichten, Aufwaende oder Marktchancen
        entstehen.</p>
        <p><strong>Neu diese Woche</strong> zeigt die 5 relevantesten
        Bewegungen. Alles Weitere ist unter "Alle N weiteren" ausklappbar.
        Klick auf <strong>+ Merken</strong> setzt einen Vorgang auf deine
        <strong>Watchlist</strong> - dann bekommst du taeglich Updates zu
        genau diesem Vorgang per Mail.</p>
        <p>Die <strong>Filter-Buttons</strong> oben schraenken auf ein
        Verfahrensstadium oder Muster ein. Die interne Sortierung nach Score
        ist bewusst nicht sichtbar.</p>
      </div>
    </details>
  </div>
</header>

<div class="filter-bar-wrap">
  <div class="filter-bar">
    <label for="f-all">Alle</label>
    <label for="f-aktiv">Im Verfahren</label>
    <label for="f-anwendbar">Anwendbar</label>
    <label for="f-tot">Gestorben</label>
    <span class="filter-sep"></span>
    <label for="f-compliance">Compliance</label>
    <label for="f-nachweis">Nachweis</label>
  </div>
</div>

<main>
  {summary}
  {watchlist}
  {neu}
  {gruppen}
</main>
<footer>
  Automatisch aktualisiert &nbsp;·&nbsp;
  <a href="https://github.com/{radar_repo}">Quelle</a>
</footer>

<script>
(function() {{
  var WATCH_ENDPOINT = {watch_endpoint_js};
  var WATCH_TOKEN    = {watch_token_js};

  function fallbackGithubUrl(id, titel) {{
    var body = 'vorgang_id: ' + id + '\\n\\nBitte die erste Zeile nicht ändern.';
    return 'https://github.com/{radar_repo}/issues/new'
         + '?labels=watchlist'
         + '&title=' + encodeURIComponent('Watchlist: ' + titel.slice(0, 80))
         + '&body='  + encodeURIComponent(body);
  }}

  document.addEventListener('click', async function(e) {{
    var btn = e.target.closest('button.watch-add');
    if (!btn) return;
    e.preventDefault();

    var id = btn.getAttribute('data-vorgang');
    var titel = btn.getAttribute('data-titel');

    // Kein Endpoint konfiguriert -> fallback: GitHub-Issue-Formular öffnen (alter Weg)
    if (!WATCH_ENDPOINT || !WATCH_TOKEN) {{
      window.open(fallbackGithubUrl(id, titel), '_blank', 'noopener');
      return;
    }}

    btn.disabled = true;
    var alter = btn.textContent;
    btn.textContent = '…';

    try {{
      var res = await fetch(WATCH_ENDPOINT + '?token=' + encodeURIComponent(WATCH_TOKEN), {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{id: id, titel: titel}}),
      }});
      var data = await res.json();
      if (res.ok && data.ok) {{
        // Nach 1-2s wird das Dashboard eh neu geladen sein - hier optisch bestätigen
        btn.classList.remove('watch-add');
        btn.classList.add('watch-badge');
        btn.textContent = '★ Auf Watchlist';
        btn.disabled = true;
      }} else {{
        btn.disabled = false;
        btn.textContent = alter;
        alert('Konnte nicht merken: ' + (data.error || res.status));
      }}
    }} catch (err) {{
      btn.disabled = false;
      btn.textContent = alter;
      alert('Netzwerkfehler: ' + err.message);
    }}
  }});
}})();
</script>
</body>
</html>
"""
