"""Statisches HTML-Dashboard fuer Legal Radar.

Aesthetik: Light-Mode, Stripe/Notion-inspiriert, ruhig und lesbar.
Struktur: Header -> Filter+Suche -> Summary -> Watchlist -> Neu -> Gruppen -> Footer.

Verwendet clientseitiges JS fuer Suche und Watchlist-Interaktion.
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
    "verkuendet": "Verkündet",
    "anwendbar": "Anwendbar",
    "tot": "Eingestellt",
}

STADIUM_FARBE = {
    "referentenentwurf": "#a3a3a3",
    "kabinett": "#a3a3a3",
    "bt": "#737373",
    "ausschuss": "#737373",
    "verkuendet": "#525252",
    "anwendbar": "#171717",
    "tot": "#d4d4d4",
}

GRUPPEN = [
    (
        "aktiv",
        "Aktive Verfahren",
        "Referentenentwurf, Kabinettsbeschluss, Bundestag oder Ausschuss.",
        ["referentenentwurf", "kabinett", "bt", "ausschuss"],
    ),
    (
        "anwendbar",
        "Bereits geltend",
        "Verkündet oder in Anwendung.",
        ["anwendbar", "verkuendet"],
    ),
    (
        "tot",
        "Nicht weiterverfolgt",
        "Vom Bundestag eingestellt oder abgelaufen.",
        ["tot"],
    ),
]

MUSTER_LABEL = {
    "compliance": "Compliance",
    "nachweis": "Nachweis",
    "vermittlung": "Vermittlung",
    "datenprodukt": "Datenprodukt",
    "keins": "-",
}

TOP_N_NEU = 3

_SUCH_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'"
    " stroke='%23737373' stroke-width='2' stroke-linecap='round'"
    " stroke-linejoin='round'>"
    "<circle cx='11' cy='11' r='7'/><path d='m20 20-3-3'/></svg>"
)
SUCH_ICON = "data:image/svg+xml;utf8," + _SUCH_SVG


def _fmt_eur(v: int | None) -> str:
    if v is None:
        return "-"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f} Mrd €"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} Mio €"
    return f"{v:,} €".replace(",", ".")


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


def _fmt_relativ(iso: str | None) -> str:
    """`vor 3 Tagen` / `heute` / `gestern` aus Datumsstring."""
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return ""
    diff = (date.today() - d).days
    if diff <= 0:
        return "heute"
    if diff == 1:
        return "gestern"
    if diff < 14:
        return f"vor {diff} Tagen"
    if diff < 60:
        return f"vor {diff // 7} Wochen"
    return f"vor {diff // 30} Monaten"


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    r = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None


def _watchlist_action(row: sqlite3.Row, watched: set[str]) -> str:
    vid = html.escape(row["id"])
    titel_attr = html.escape((row["titel"] or "").replace('"', "'"), quote=True)
    if row["id"] in watched:
        return (
            f'<button type="button" class="watch-remove" '
            f'data-vorgang="{vid}" '
            f'title="Klick zum Entfernen">★ Auf Watchlist</button>'
        )
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
    titel_such = (row["titel"] or "").lower()
    url = html.escape(row["quelle_url"] or "")
    behoerde = html.escape(row["behoerde"] or "")
    try:
        betroffene_val = row["betroffene"]
    except (IndexError, KeyError):
        betroffene_val = None

    # Meta-Zeile (kollabiert): Stadium · Kosten · Gilt ab · vor X Tagen
    meta_bits = [f'<span class="q-stadium">{stadium_txt}</span>']
    if row["erf_aufwand_eur"]:
        meta_bits.append(
            f'<span class="q-kosten">{html.escape(_fmt_eur(row["erf_aufwand_eur"]))}</span>'
        )
    if row["anwendungsbeginn"]:
        meta_bits.append(
            f'<span class="q-datum">ab {html.escape(_fmt_datum(row["anwendungsbeginn"]))}</span>'
        )
    rel = _fmt_relativ(row["erstgesehen"])
    if rel:
        meta_bits.append(f'<span class="q-zeit">{rel}</span>')
    meta_zeile = f'<div class="card-meta">{" · ".join(meta_bits)}</div>'

    # Neu-Punkt vor dem Titel
    neu_dot = (
        '<span class="neu-dot" title="Neu diese Woche" aria-label="Neu"></span>' if is_neu else ""
    )

    # Expanded details
    dl_rows = []
    if row["anwendungsbeginn"]:
        gilt_ab = html.escape(_fmt_datum(row["anwendungsbeginn"]))
        dl_rows.append(f"<div><dt>Gilt ab</dt><dd>{gilt_ab}</dd></div>")
    if row["erf_aufwand_eur"]:
        dl_rows.append(
            f'<div><dt title="Erfüllungsaufwand">Kosten für Wirtschaft</dt>'
            f"<dd>{html.escape(_fmt_eur(row['erf_aufwand_eur']))}</dd></div>"
        )
    if betroffene_val:
        betr = html.escape(_fmt_zahl(betroffene_val))
        dl_rows.append(f"<div><dt>Betroffene Unternehmen</dt><dd>{betr}</dd></div>")
    if behoerde:
        dl_rows.append(f"<div><dt>Zuständige Behörde</dt><dd>{behoerde}</dd></div>")
    if muster_key != "keins":
        dl_rows.append(f"<div><dt>Typ</dt><dd>{muster_txt}</dd></div>")
    dl_block = f'<dl class="meta">{"".join(dl_rows)}</dl>' if dl_rows else ""

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
        pflichten_block = (
            '<div class="pflichten-titel">Zentrale Pflichten</div>'
            f'<ul class="pflichten">{items}</ul>'
        )

    watch_action = _watchlist_action(row, watched)
    such_attr = html.escape(titel_such, quote=True)

    return f"""
    <details class="card" data-stadium="{stadium}" data-muster="{muster_key}"
             data-titel="{such_attr}">
      <summary class="card-summary">
        <div class="card-summary-main">
          <div class="card-titel-zeile">
            <span class="stadium-dot" style="--dot:{farbe}"
                  aria-label="{stadium_txt}"></span>
            {neu_dot}
            <h3 class="card-titel">{titel}</h3>
          </div>
          {meta_zeile}
        </div>
        <span class="card-chevron" aria-hidden="true"></span>
      </summary>
      <div class="card-body">
        {dl_block}
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
    ct_line = " &middot; ".join(ct_bits) or f"{n_total} Vorgänge im Radar"

    return f"""
    <section class="summary-card">
      <div class="summary-label">Zusammenfassung diese Woche</div>
      <p class="summary-text">{html.escape(summary_text)}</p>
      <div class="summary-counts">{ct_line}</div>
    </section>
    """


def _rubrik_kopf(titel: str, count: int | None, untertitel: str, klasse: str = "") -> str:
    count_html = f' <span class="count">({count})</span>' if count is not None else ""
    return (
        f'<header class="rubrik-kopf{" " + klasse if klasse else ""}">'
        f'<h2 class="rubrik-titel">{titel}{count_html}</h2>'
        f'<p class="rubrik-untertitel">{untertitel}</p>'
        f"</header>"
    )


def _watchlist_sektion(rows: list[sqlite3.Row], pflichten: dict, watched: set[str]) -> str:
    if not watched:
        return ""
    wrows = [r for r in rows if r["id"] in watched]
    kopf_titel = "★ Meine Watchlist"
    kopf_untertitel = "Vorgänge, die Sie zum Beobachten markiert haben."
    if not wrows:
        return (
            '<section class="rubrik watchlist-rubrik">'
            + _rubrik_kopf(kopf_titel, None, kopf_untertitel)
            + '<p class="empty-inline">Ihre Watchlist ist gesetzt, aber die Vorgänge '
            "sind derzeit nicht im Radar. Möglicherweise wurden sie eingestellt oder sind "
            "aus dem Fetch-Fenster gefallen.</p>"
            "</section>"
        )
    cards = "\n".join(_card(r, pflichten.get(r["id"], []), False, watched) for r in wrows)
    return (
        '<section class="rubrik watchlist-rubrik">'
        + _rubrik_kopf(kopf_titel, len(wrows), kopf_untertitel)
        + f'<div class="cards cards-watchlist">{cards}</div>'
        + "</section>"
    )


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
    aenderungs_ids = set(events.keys()) - {r["id"] for r in neu_rows}
    aenderungs_rows = [r for r in rows if r["id"] in aenderungs_ids]

    if not neu_rows and not aenderungs_rows:
        return ""

    kombiniert = neu_rows + aenderungs_rows
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

    kopf = _rubrik_kopf(
        "Neu diese Woche",
        len(kombiniert),
        "Im 7-Tage-Fenster erstmals aufgetaucht oder in ein neues Stadium gewechselt.",
    )
    return (
        '<section class="rubrik neu-rubrik">'
        + kopf
        + f'<div class="cards">{top_cards}</div>'
        + rest_block
        + "</section>"
    )


def _gruppen_sektionen(rows: list[sqlite3.Row], pflichten: dict, watched: set[str]) -> str:
    out_parts = []
    for key, label, unter, stadien in GRUPPEN:
        gruppe_rows = [r for r in rows if (r["stadium"] or "bt") in stadien]
        if not gruppe_rows:
            continue
        cards = "\n".join(_card(r, pflichten.get(r["id"], []), False, watched) for r in gruppe_rows)
        out_parts.append(
            f'<section class="rubrik gruppe gruppe-{key}">'
            + _rubrik_kopf(label, len(gruppe_rows), unter)
            + f'<div class="cards">{cards}</div>'
            + "</section>"
        )
    return "\n".join(out_parts) or '<p class="empty">Noch keine Vorgänge im Radar.</p>'


def _filter_counts(rows: list[sqlite3.Row]) -> dict[str, int]:
    """Zaehlt Vorgaenge je Filter-Kategorie."""
    counts = {
        "all": len(rows),
        "aktiv": 0,
        "anwendbar": 0,
        "tot": 0,
        "compliance": 0,
        "nachweis": 0,
    }
    aktiv_stadien = {"referentenentwurf", "kabinett", "bt", "ausschuss"}
    anwendbar_stadien = {"anwendbar", "verkuendet"}
    for r in rows:
        st = r["stadium"] or "bt"
        if st in aktiv_stadien:
            counts["aktiv"] += 1
        elif st in anwendbar_stadien:
            counts["anwendbar"] += 1
        elif st == "tot":
            counts["tot"] += 1
        m = r["muster"] or "keins"
        if m == "compliance":
            counts["compliance"] += 1
        elif m == "nachweis":
            counts["nachweis"] += 1
    return counts


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
    fc = _filter_counts(rows)

    summary_html = _summary_card(summary_text, counts, n)
    watchlist_html = _watchlist_sektion(rows, pflichten_by_vid, watched)
    neu_html = _neu_sektion(rows, pflichten_by_vid, events, watched)
    gruppen_html = _gruppen_sektionen(rows, pflichten_by_vid, watched)

    return _shell(
        stand,
        n,
        fc,
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
    fc: dict[str, int],
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
<meta name="color-scheme" content="light">
<link rel="preconnect" href="https://rsms.me/">
<link rel="stylesheet" href="https://rsms.me/inter/inter.css">
<style>
  :root {{
    color-scheme: light;
    --bg: #ffffff;
    --surface: #ffffff;
    --surface-2: #fafafa;
    --surface-3: #f5f5f5;
    --text: #171717;
    --text-soft: #525252;
    --muted: #737373;
    --border: rgba(0,0,0,0.08);
    --border-strong: rgba(0,0,0,0.14);
    --accent: #171717;
    --neu: #10b981;
    --amber: #92400e;
    --red: #7f1d1d;
    --radius: 12px;
    --radius-sm: 8px;
  }}

  input[type=radio][name=fs], input[type=radio][name=ft] {{
    position: absolute; opacity: 0; pointer-events: none;
    width: 0; height: 0; margin: 0;
  }}

  * {{ box-sizing: border-box; }}
  html {{ -webkit-text-size-adjust: 100%; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0;
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text",
                 "Segoe UI", Roboto, sans-serif;
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
    font-size: 15px; line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }}
  @supports (font-variation-settings: normal) {{
    body {{ font-family: "Inter var", -apple-system, sans-serif; }}
  }}
  a {{ color: inherit; }}

  /* Header */
  header.site-header {{
    padding: 48px 32px 24px;
    border-bottom: 1px solid var(--border);
  }}
  .header-inner {{ max-width: 1100px; margin: 0 auto; }}
  .titelzeile {{
    display: flex; align-items: baseline; justify-content: space-between;
    flex-wrap: wrap; gap: 12px;
  }}
  h1 {{
    margin: 0; font-size: 32px; font-weight: 700;
    letter-spacing: -0.025em; line-height: 1.1;
  }}
  .sub {{
    color: var(--muted); font-size: 13px;
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }}
  .claim {{
    margin: 10px 0 0; max-width: 62ch;
    color: var(--text-soft); font-size: 15px; line-height: 1.55;
  }}

  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 32px 80px; }}

  /* Filter + Suche */
  .toolbar {{
    position: sticky; top: 0; z-index: 20;
    background: color-mix(in oklab, var(--bg) 94%, transparent);
    backdrop-filter: saturate(180%) blur(20px);
    -webkit-backdrop-filter: saturate(180%) blur(20px);
    margin: 0 -32px 32px; padding: 12px 32px;
    border-bottom: 1px solid var(--border);
  }}
  .toolbar-inner {{ max-width: 1100px; margin: 0 auto; display: grid; gap: 10px; }}

  .search-wrap {{ position: relative; }}
  .search-wrap::before {{
    content: ""; position: absolute; left: 14px; top: 50%;
    transform: translateY(-50%);
    width: 14px; height: 14px;
    background-image: url("{SUCH_ICON}");
    background-repeat: no-repeat; background-size: contain;
    pointer-events: none;
  }}
  #suche {{
    width: 100%; padding: 10px 14px 10px 40px;
    border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface-3); color: var(--text);
    font-family: inherit; font-size: 14px;
    transition: border-color 150ms ease, background 150ms ease;
  }}
  #suche:focus {{ outline: none; border-color: var(--text); background: var(--surface); }}
  #suche::placeholder {{ color: var(--muted); }}

  .filter-row {{
    display: flex; gap: 4px; flex-wrap: wrap; align-items: center;
    font-size: 13px;
  }}
  .filter-label {{
    color: var(--muted); font-weight: 500; padding-right: 8px;
    min-width: 62px;
  }}
  .filter-row label {{
    padding: 5px 12px; border: 1px solid var(--border); border-radius: 999px;
    background: transparent; cursor: pointer;
    color: var(--text-soft); font-weight: 500;
    transition: all 120ms ease;
  }}
  .filter-row label:hover {{
    background: var(--surface-3); color: var(--text);
  }}
  .filter-row label .fc {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
  #f-all:checked ~ * label[for=f-all],
  #f-aktiv:checked ~ * label[for=f-aktiv],
  #f-anwendbar:checked ~ * label[for=f-anwendbar],
  #f-tot:checked ~ * label[for=f-tot],
  #f-mall:checked ~ * label[for=f-mall],
  #f-compliance:checked ~ * label[for=f-compliance],
  #f-nachweis:checked ~ * label[for=f-nachweis] {{
    background: var(--text); color: var(--bg); border-color: var(--text);
  }}
  #f-all:checked ~ * label[for=f-all] .fc,
  #f-aktiv:checked ~ * label[for=f-aktiv] .fc,
  #f-anwendbar:checked ~ * label[for=f-anwendbar] .fc,
  #f-tot:checked ~ * label[for=f-tot] .fc,
  #f-mall:checked ~ * label[for=f-mall] .fc,
  #f-compliance:checked ~ * label[for=f-compliance] .fc,
  #f-nachweis:checked ~ * label[for=f-nachweis] .fc {{ color: rgba(255,255,255,0.7); }}

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

  /* Karten via JS-Suche versteckt */
  .card.hidden-search {{ display: none !important; }}

  /* Summary */
  .summary-card {{
    background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 24px 28px; margin-bottom: 40px;
  }}
  .summary-label {{
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); font-weight: 600; margin-bottom: 10px;
  }}
  .summary-text {{
    margin: 0; font-size: 17px; line-height: 1.6; color: var(--text);
    font-weight: 400; max-width: 68ch;
  }}
  .summary-counts {{
    margin-top: 14px; font-size: 13px; color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .summary-counts strong {{ color: var(--text); font-weight: 600; }}

  /* Rubriken */
  .rubrik {{ margin-bottom: 48px; }}
  .rubrik-kopf {{ margin-bottom: 16px; }}
  .rubrik-titel {{
    font-size: 20px; font-weight: 700; letter-spacing: -0.01em;
    color: var(--text); margin: 0;
  }}
  .rubrik-titel .count {{
    color: var(--muted); font-weight: 500; margin-left: 6px;
    font-variant-numeric: tabular-nums;
  }}
  .rubrik-untertitel {{
    margin: 4px 0 0; font-size: 13.5px; color: var(--text-soft);
    max-width: 68ch;
  }}
  .watchlist-rubrik .rubrik-titel {{ color: var(--amber); }}

  /* Cards */
  .cards {{ display: grid; gap: 10px; }}
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
    background: var(--surface);
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}

  .card-summary {{
    display: flex; align-items: center; gap: 14px;
    padding: 16px 20px; cursor: pointer;
    list-style: none;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
  }}
  .card-summary::-webkit-details-marker {{ display: none; }}
  .card-summary::marker {{ display: none; content: ""; }}
  .card-summary-main {{ flex: 1; min-width: 0; }}

  .card-titel-zeile {{
    display: flex; align-items: center; gap: 8px;
  }}
  .stadium-dot {{
    flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%;
    background: var(--dot, var(--muted));
  }}
  .neu-dot {{
    flex-shrink: 0; width: 7px; height: 7px; border-radius: 50%;
    background: var(--neu);
    box-shadow: 0 0 0 3px rgba(16,185,129,0.15);
  }}

  .card-titel {{
    margin: 0; font-size: 16px; font-weight: 600;
    letter-spacing: -0.005em; line-height: 1.4; color: var(--text);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
    flex: 1;
  }}

  .card-meta {{
    margin-top: 6px; padding-left: 16px;
    font-size: 12.5px; color: var(--muted);
    font-variant-numeric: tabular-nums;
    display: flex; gap: 8px; flex-wrap: wrap;
  }}
  .card-meta > span:not(:last-child)::after {{
    content: "·"; margin-left: 8px; opacity: 0.5;
  }}
  .card-meta .q-kosten {{ color: var(--text-soft); font-weight: 500; }}
  .card-meta .q-stadium {{ color: var(--text-soft); }}

  .card-chevron {{
    flex-shrink: 0; width: 22px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); transition: transform 250ms ease;
  }}
  .card-chevron::before {{
    content: ""; display: block; width: 7px; height: 7px;
    border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor;
    transform: rotate(45deg) translate(-2px, -2px);
  }}
  .card[open] .card-chevron {{ color: var(--text); transform: rotate(180deg); }}

  .card-body {{
    padding: 4px 20px 20px;
    border-top: 1px solid var(--border);
    margin-top: 2px;
  }}

  .card-footer {{
    display: flex; justify-content: space-between; align-items: center;
    gap: 10px; margin-top: 18px; padding-top: 16px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
  }}
  .card-link {{
    color: var(--text); text-decoration: none; font-size: 13px;
    font-weight: 500;
    border-bottom: 1px solid var(--border-strong);
    padding-bottom: 1px;
  }}
  .card-link:hover {{ border-color: var(--text); }}

  .watch-add, .watch-remove {{
    font-size: 12.5px; padding: 5px 12px; border-radius: 8px;
    font-weight: 500; white-space: nowrap; cursor: pointer;
    font-family: inherit;
  }}
  .watch-add {{
    color: var(--muted);
    border: 1px solid var(--border); background: transparent;
    transition: all 120ms ease;
  }}
  .watch-add:hover {{ color: var(--amber); border-color: var(--amber);
                      background: rgba(146,64,14,0.05); }}
  .watch-remove {{
    color: var(--amber); background: rgba(146,64,14,0.06);
    border: 1px solid rgba(146,64,14,0.2);
    transition: all 120ms ease;
  }}
  .watch-remove:hover {{
    color: var(--red); border-color: var(--red);
    background: rgba(127,29,29,0.06);
  }}

  .meta {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px;
    margin: 16px 0 0; font-size: 13px;
    font-variant-numeric: tabular-nums;
  }}
  .meta > div {{ display: flex; flex-direction: column; min-width: 0; }}
  .meta dt {{
    color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.06em; font-weight: 600; margin-bottom: 4px;
  }}
  .meta dd {{ margin: 0; font-weight: 500; color: var(--text); }}

  .pflichten-titel {{
    margin: 20px 0 8px; font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.06em; font-weight: 600; color: var(--muted);
  }}
  .pflichten {{
    margin: 0; padding: 14px 16px 14px 20px;
    background: var(--surface-3); border-radius: var(--radius-sm);
    list-style: disc; font-size: 13px;
    color: var(--text-soft);
  }}
  .pflichten li {{ margin: 3px 0; }}
  .pflichten strong {{ color: var(--text); font-weight: 600; }}
  .pflichten .freq {{ color: var(--muted); font-size: 12px; }}

  /* Rest-Fold */
  .rest-fold {{ margin-top: 14px; }}
  .rest-fold summary {{
    cursor: pointer; color: var(--text-soft); font-size: 13px;
    padding: 10px 16px; border-radius: var(--radius-sm);
    background: var(--surface-3); border: 1px solid var(--border);
    list-style: none; user-select: none;
    transition: all 120ms ease;
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

  /* Toast */
  #toast {{
    position: fixed; bottom: 24px; right: 24px; z-index: 100;
    background: var(--text); color: var(--bg);
    padding: 12px 18px; border-radius: 10px; font-size: 14px;
    font-weight: 500; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    opacity: 0; transform: translateY(10px);
    transition: opacity 200ms ease, transform 200ms ease;
    pointer-events: none;
    max-width: 320px;
  }}
  #toast.show {{ opacity: 1; transform: translateY(0); }}
  #toast.err {{ background: var(--red); }}

  footer {{
    max-width: 1100px; margin: 0 auto; padding: 32px;
    color: var(--muted); font-size: 12px; text-align: center;
    border-top: 1px solid var(--border);
  }}
  footer a {{ color: var(--text-soft); text-decoration: none; }}
  footer a:hover {{ color: var(--text); }}

  @media (max-width: 720px) {{
    header.site-header {{ padding: 28px 18px 16px; }}
    main {{ padding: 18px 18px 60px; }}
    .toolbar {{ margin: 0 -18px 20px; padding: 10px 18px; }}
    h1 {{ font-size: 24px; }}
    .claim {{ font-size: 14px; }}
    .filter-label {{ min-width: 100%; padding-right: 0; padding-bottom: 4px; }}
    .summary-card {{ padding: 20px 22px; margin-bottom: 32px; }}
    .summary-text {{ font-size: 15px; }}
    .rubrik {{ margin-bottom: 36px; }}
    .rubrik-titel {{ font-size: 18px; }}
    .card-summary {{ padding: 14px 16px; gap: 10px; }}
    .card-titel {{ font-size: 15px; }}
    .card-meta {{ font-size: 12px; padding-left: 0; }}
    .card-body {{ padding: 4px 16px 16px; }}
    .meta {{ grid-template-columns: 1fr 1fr; gap: 14px; font-size: 12.5px; }}
    .card-footer {{ flex-direction: column-reverse; align-items: stretch; gap: 8px; }}
    .card-footer .card-link {{ text-align: center; padding: 8px;
                               border: 1px solid var(--border); border-radius: 8px;
                               border-bottom-color: var(--border); }}
    .watch-add, .watch-remove {{ text-align: center; }}
    #toast {{ left: 16px; right: 16px; bottom: 16px; max-width: none; }}
  }}

  @media print {{
    .toolbar, .card-footer, .card-chevron, footer {{ display: none !important; }}
    .card, .rest-fold {{ break-inside: avoid; }}
    details, .rest-fold {{ }}
    details[open] > * {{ display: block; }}
    details:not([open]) .card-body {{ display: none; }}
    body {{ font-size: 11pt; }}
  }}
</style>
</head>
<body>
<input type="radio" name="fs" id="f-all" checked>
<input type="radio" name="fs" id="f-aktiv">
<input type="radio" name="fs" id="f-anwendbar">
<input type="radio" name="fs" id="f-tot">
<input type="radio" name="ft" id="f-mall" checked>
<input type="radio" name="ft" id="f-compliance">
<input type="radio" name="ft" id="f-nachweis">

<header class="site-header">
  <div class="header-inner">
    <div class="titelzeile">
      <h1>Legal Radar</h1>
      <div class="sub">Stand {stand} &nbsp;·&nbsp; {n} Vorgang{"e" if n != 1 else ""}</div>
    </div>
    <p class="claim">
      Frühwarnsystem für Bundestags-Gesetzgebung: welche neuen Pflichten,
      Kosten oder Marktchancen entstehen aktuell für die Wirtschaft.
    </p>
  </div>
</header>

<div class="toolbar">
  <div class="toolbar-inner">
    <div class="search-wrap">
      <input type="search" id="suche" placeholder="Vorgang suchen &hellip; (Titel)"
             autocomplete="off">
    </div>
    <div class="filter-row">
      <span class="filter-label">Stadium</span>
      <label for="f-all">Alle <span class="fc">({fc["all"]})</span></label>
      <label for="f-aktiv">Aktive Verfahren <span class="fc">({fc["aktiv"]})</span></label>
      <label for="f-anwendbar">Bereits geltend <span class="fc">({fc["anwendbar"]})</span></label>
      <label for="f-tot">Eingestellt <span class="fc">({fc["tot"]})</span></label>
    </div>
    <div class="filter-row">
      <span class="filter-label">Typ</span>
      <label for="f-mall">Alle</label>
      <label for="f-compliance">Compliance <span class="fc">({fc["compliance"]})</span></label>
      <label for="f-nachweis">Nachweis <span class="fc">({fc["nachweis"]})</span></label>
    </div>
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

<div id="toast" role="status" aria-live="polite"></div>

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

  var toastEl = document.getElementById('toast');
  var toastTimer = null;
  function toast(msg, isError) {{
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.toggle('err', !!isError);
    toastEl.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function() {{ toastEl.classList.remove('show'); }}, 3000);
  }}

  async function callWorker(pfad, body) {{
    var url = WATCH_ENDPOINT.replace(/\\/watch$/, '') + pfad
            + '?token=' + encodeURIComponent(WATCH_TOKEN);
    var res = await fetch(url, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(body),
    }});
    var data = await res.json();
    return {{ok: res.ok && data.ok, data: data, status: res.status}};
  }}

  document.addEventListener('click', async function(e) {{
    var addBtn = e.target.closest('button.watch-add');
    var rmBtn  = e.target.closest('button.watch-remove');
    if (!addBtn && !rmBtn) return;
    e.preventDefault();
    var btn = addBtn || rmBtn;
    var id = btn.getAttribute('data-vorgang');

    if (!WATCH_ENDPOINT || !WATCH_TOKEN) {{
      if (addBtn) {{
        var titel = addBtn.getAttribute('data-titel');
        window.open(fallbackGithubUrl(id, titel), '_blank', 'noopener');
      }}
      return;
    }}

    btn.disabled = true;
    var alter = btn.textContent;
    btn.textContent = '…';

    try {{
      var r;
      if (addBtn) {{
        var titel = addBtn.getAttribute('data-titel');
        r = await callWorker('/watch', {{id: id, titel: titel}});
      }} else {{
        r = await callWorker('/unwatch', {{id: id}});
      }}
      if (r.ok) {{
        if (addBtn) {{
          btn.classList.remove('watch-add');
          btn.classList.add('watch-remove');
          btn.textContent = '★ Auf Watchlist';
          btn.title = 'Klick zum Entfernen';
          toast('Auf Watchlist gemerkt');
        }} else {{
          btn.classList.remove('watch-remove');
          btn.classList.add('watch-add');
          btn.textContent = '+ Merken';
          btn.title = 'Auf Watchlist setzen';
          btn.removeAttribute('data-titel');
          toast('Von Watchlist entfernt');
        }}
        btn.disabled = false;
      }} else {{
        btn.disabled = false;
        btn.textContent = alter;
        toast('Fehler: ' + (r.data.error || r.status), true);
      }}
    }} catch (err) {{
      btn.disabled = false;
      btn.textContent = alter;
      toast('Netzwerkfehler: ' + err.message, true);
    }}
  }});

  // --- Suche ---
  var suche = document.getElementById('suche');
  var suchTimer = null;
  function applySearch(q) {{
    q = (q || '').trim().toLowerCase();
    var cards = document.querySelectorAll('.card');
    cards.forEach(function(c) {{
      if (!q) {{ c.classList.remove('hidden-search'); return; }}
      var t = c.getAttribute('data-titel') || '';
      if (t.indexOf(q) >= 0) c.classList.remove('hidden-search');
      else c.classList.add('hidden-search');
    }});
  }}
  if (suche) {{
    suche.addEventListener('input', function(e) {{
      if (suchTimer) clearTimeout(suchTimer);
      suchTimer = setTimeout(function() {{ applySearch(e.target.value); }}, 120);
    }});
  }}

  // --- Keyboard ---
  document.addEventListener('keydown', function(e) {{
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') {{
      if (e.key === 'Escape' && e.target === suche) {{
        suche.value = '';
        applySearch('');
        suche.blur();
      }}
      return;
    }}
    if (e.key === '/' && suche) {{
      e.preventDefault();
      suche.focus();
    }} else if (e.key === 'Escape') {{
      var allRadio = document.getElementById('f-all');
      var mallRadio = document.getElementById('f-mall');
      if (allRadio) allRadio.checked = true;
      if (mallRadio) mallRadio.checked = true;
      if (suche) {{ suche.value = ''; applySearch(''); }}
    }}
  }});
}})();
</script>
</body>
</html>
"""
