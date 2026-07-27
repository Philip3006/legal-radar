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


_BEWERTEN_LABEL = {
    "interessant": "★ Interessant",
    "beobachten": "◐ Beobachten",
    "verworfen": "✕ Verworfen",
}


def _bewerten_actions(row: sqlite3.Row, bewertungen: dict[str, str]) -> str:
    """Drei Radio-Buttons pro Karte. Klick auf aktiven Status hebt ihn auf."""
    vid = html.escape(row["id"])
    titel_attr = html.escape((row["titel"] or "").replace('"', "'"), quote=True)
    aktuell = bewertungen.get(row["id"], "")
    knoepfe = []
    for status, label in _BEWERTEN_LABEL.items():
        aktiv = " aktiv" if status == aktuell else ""
        knoepfe.append(
            f'<button type="button" class="bewerten{aktiv}" '
            f'data-vorgang="{vid}" data-titel="{titel_attr}" '
            f'data-status="{status}">{label}</button>'
        )
    return f'<div class="bewerten-gruppe">{"".join(knoepfe)}</div>'


def _card(
    row: sqlite3.Row,
    pflichten: list[sqlite3.Row],
    is_neu: bool,
    bewertungen: dict[str, str] | None = None,
) -> str:
    bewertungen = bewertungen or {}
    stadium = row["stadium"] or "bt"
    farbe = STADIUM_FARBE.get(stadium, "#737373")
    stadium_txt = html.escape(STADIUM_LABEL.get(stadium, stadium))
    muster_key = row["muster"] or "keins"
    muster_txt = html.escape(MUSTER_LABEL.get(muster_key, "-"))
    titel_raw = html.escape(row["titel"] or "")
    if muster_key != "keins":
        titel = f'{titel_raw} <span class="titel-muster">({muster_txt})</span>'
    else:
        titel = titel_raw
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

    bewerten_block = _bewerten_actions(row, bewertungen)
    such_attr = html.escape(titel_such, quote=True)
    kosten_val = int(row["erf_aufwand_eur"] or 0)
    erst_val = html.escape(row["erstgesehen"] or "")
    anw_val = html.escape(row["anwendungsbeginn"] or "")
    vid_attr = html.escape(row["id"], quote=True)
    aktuelle_bewertung = bewertungen.get(row["id"], "")
    dot_html = ""
    if aktuelle_bewertung:
        symbol = {"interessant": "★", "beobachten": "◐", "verworfen": "✕"}.get(
            aktuelle_bewertung, ""
        )
        dot_html = (
            f'<span class="bewertung-dot" data-status="{aktuelle_bewertung}" '
            f'title="Bewertung: {aktuelle_bewertung}">{symbol}</span>'
        )

    return f"""
    <details class="card" data-stadium="{stadium}" data-muster="{muster_key}"
             data-vorgang="{vid_attr}" data-bewertung="{aktuelle_bewertung}"
             data-titel="{such_attr}" data-kosten="{kosten_val}"
             data-erstgesehen="{erst_val}" data-anwendungsbeginn="{anw_val}">
      <summary class="card-summary">
        <div class="card-summary-main">
          <div class="card-titel-zeile">
            <span class="stadium-dot" style="--dot:{farbe}"
                  aria-label="{stadium_txt}"></span>
            {neu_dot}
            {dot_html}
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
        </div>
        {bewerten_block}
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


_BEWERTUNG_SEKTIONEN = [
    (
        "interessant",
        "★ Interessant",
        "Automatischer Watchlist-Digest per Mail bei Aenderungen.",
    ),
    (
        "beobachten",
        "◐ Beobachten",
        "Zurueckgestellt - noch keine Push-Alerts.",
    ),
    (
        "verworfen",
        "✕ Verworfen",
        "Als nicht relevant markiert. Bleiben sichtbar fuer Nachvollziehbarkeit.",
    ),
]


def _bewertung_sektion(
    status: str,
    label: str,
    untertitel: str,
    rows: list[sqlite3.Row],
    pflichten: dict,
    bewertungen: dict[str, str],
) -> str:
    """Eine Sektion pro Bewertungs-Kategorie. Leer -> nichts rendern."""
    matches = [r for r in rows if bewertungen.get(r["id"]) == status]
    if not matches:
        return ""
    kollabiert = status == "verworfen"  # verworfen ist standardmaessig zu
    cards = "\n".join(_card(r, pflichten.get(r["id"], []), False, bewertungen) for r in matches)
    tag_open = (
        f'<details class="rubrik bewertung-rubrik bewertung-{status}"'
        + ("" if kollabiert else " open")
        + ">"
    )
    kopf = _rubrik_kopf(label, len(matches), untertitel)
    return f'{tag_open}<summary>{kopf}</summary><div class="cards">{cards}</div></details>'


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
    bewertungen: dict[str, str] | None = None,
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

    top_cards = "\n".join(_card(r, pflichten.get(r["id"], []), True, bewertungen) for r in top)
    rest_block = ""
    if rest:
        rest_cards = "\n".join(
            _card(r, pflichten.get(r["id"], []), True, bewertungen) for r in rest
        )
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


def _gruppen_sektionen(
    rows: list[sqlite3.Row],
    pflichten: dict,
    bewertungen: dict[str, str] | None = None,
) -> str:
    out_parts = []
    for key, label, unter, stadien in GRUPPEN:
        gruppe_rows = [r for r in rows if (r["stadium"] or "bt") in stadien]
        if not gruppe_rows:
            continue
        cards = "\n".join(
            _card(r, pflichten.get(r["id"], []), False, bewertungen) for r in gruppe_rows
        )
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
        "datenprodukt": 0,
        "vermittlung": 0,
        "k10": 0,
        "k100": 0,
        "k1000": 0,
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
        if m in counts:
            counts[m] += 1
        k = int(r["erf_aufwand_eur"] or 0)
        if k > 10_000_000:
            counts["k10"] += 1
        if k > 100_000_000:
            counts["k100"] += 1
        if k > 1_000_000_000:
            counts["k1000"] += 1
    return counts


def render_html(
    con: sqlite3.Connection,
    summary_text: str | None = None,
    radar_repo: str = "Philip3006/legal-radar",
    watch_endpoint: str = "",
    watch_token: str = "",
    bewertungen: dict[str, str] | None = None,
) -> str:
    bewertungen = bewertungen or {}

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
    bewertung_html = "\n".join(
        _bewertung_sektion(status, label, untertitel, rows, pflichten_by_vid, bewertungen)
        for status, label, untertitel in _BEWERTUNG_SEKTIONEN
    )
    neu_html = _neu_sektion(rows, pflichten_by_vid, events, bewertungen)
    gruppen_html = _gruppen_sektionen(rows, pflichten_by_vid, bewertungen)

    return _shell(
        stand,
        n,
        fc,
        summary_html,
        bewertung_html,
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
    bewertung: str,
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

  input[type=radio][name=fs], input[type=radio][name=ft],
  input[type=radio][name=fk], input[type=radio][name=fo] {{
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

  /* Bewertungs-Hero: prominenteste Steuerung, direkt unter Header */
  .bewertungs-hero {{
    max-width: 1100px; margin: 0 auto; padding: 20px 32px 8px;
  }}
  .hero-inner {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  }}
  .hero-tile {{
    display: flex; flex-direction: column; align-items: flex-start;
    gap: 4px; padding: 14px 16px; min-height: 88px;
    border: 1.5px solid var(--border); border-radius: 12px;
    background: var(--surface); text-align: left; cursor: pointer;
    font-family: inherit; transition: all 150ms ease;
  }}
  .hero-tile:hover {{
    border-color: var(--border-strong); background: var(--surface-2);
    transform: translateY(-1px);
  }}
  .hero-tile .tile-count {{
    font-size: 26px; font-weight: 700; line-height: 1;
    font-variant-numeric: tabular-nums; color: var(--text);
  }}
  .hero-tile .tile-label {{
    font-size: 13px; font-weight: 600; color: var(--text-soft);
  }}
  .hero-tile .tile-hint {{
    font-size: 11px; color: var(--muted); margin-top: auto;
  }}
  /* Aktive Kachel: farbig gefuellt je nach Status */
  .hero-tile.aktiv {{
    border-width: 1.5px; box-shadow: 0 2px 10px rgba(0,0,0,0.06);
  }}
  .hero-tile[data-hero="ball"].aktiv {{
    background: var(--text); border-color: var(--text);
  }}
  .hero-tile[data-hero="ball"].aktiv .tile-count,
  .hero-tile[data-hero="ball"].aktiv .tile-label {{ color: var(--bg); }}
  .hero-tile[data-hero="ball"].aktiv .tile-hint {{ color: rgba(255,255,255,0.6); }}

  .hero-tile[data-hero="binteressant"].aktiv {{
    background: var(--amber); border-color: var(--amber);
  }}
  .hero-tile[data-hero="binteressant"].aktiv .tile-count,
  .hero-tile[data-hero="binteressant"].aktiv .tile-label {{ color: #fff; }}
  .hero-tile[data-hero="binteressant"].aktiv .tile-hint {{ color: rgba(255,255,255,0.75); }}
  .hero-tile[data-hero="binteressant"] .tile-label {{ color: var(--amber); }}

  .hero-tile[data-hero="bbeobachten"].aktiv {{
    background: var(--text-soft); border-color: var(--text-soft);
  }}
  .hero-tile[data-hero="bbeobachten"].aktiv .tile-count,
  .hero-tile[data-hero="bbeobachten"].aktiv .tile-label {{ color: var(--bg); }}
  .hero-tile[data-hero="bbeobachten"].aktiv .tile-hint {{ color: rgba(255,255,255,0.65); }}

  .hero-tile[data-hero="bverworfen"].aktiv {{
    background: var(--surface-3); border-color: var(--border-strong);
  }}
  .hero-tile[data-hero="bverworfen"] .tile-label {{ color: var(--muted); }}

  @media (max-width: 900px) {{
    .bewertungs-hero {{ padding: 16px 18px 4px; }}
    .hero-inner {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
    .hero-tile {{ min-height: 72px; padding: 10px 12px; }}
    .hero-tile .tile-count {{ font-size: 20px; }}
    .hero-tile .tile-hint {{ display: none; }}
  }}

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
    display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
    font-size: 13px;
  }}
  .filter-label {{
    color: var(--muted); font-weight: 600; padding-right: 10px;
    min-width: 68px; text-transform: uppercase; letter-spacing: 0.04em;
    font-size: 11px;
  }}
  /* Basis-Chip: sichtbar als Button, aber ruhig */
  .filter-row label {{
    padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px;
    background: var(--bg); cursor: pointer;
    color: var(--text-soft); font-weight: 500;
    transition: all 120ms ease;
    display: inline-flex; align-items: center; gap: 4px;
  }}
  .filter-row label:hover {{
    color: var(--text); background: var(--surface-3);
    border-color: var(--border-strong);
  }}
  .filter-row label .fc {{
    font-variant-numeric: tabular-nums; font-size: 11px;
    opacity: 0.7;
  }}
  /* Default-Chip ('Alle'): auch aktiv nur subtil hervorgehoben */
  #f-all:checked ~ * label[for=f-all],
  #f-mall:checked ~ * label[for=f-mall],
  #f-kall:checked ~ * label[for=f-kall],
  #f-oscore:checked ~ * label[for=f-oscore] {{
    color: var(--text); background: var(--surface-3);
    border-color: var(--border);
  }}
  /* Nicht-Default aktiv: stark markiert mit dunkler Fuellung */
  #f-aktiv:checked ~ * label[for=f-aktiv],
  #f-anwendbar:checked ~ * label[for=f-anwendbar],
  #f-tot:checked ~ * label[for=f-tot],
  #f-compliance:checked ~ * label[for=f-compliance],
  #f-nachweis:checked ~ * label[for=f-nachweis],
  #f-datenprodukt:checked ~ * label[for=f-datenprodukt],
  #f-vermittlung:checked ~ * label[for=f-vermittlung],
  #f-k10:checked ~ * label[for=f-k10],
  #f-k100:checked ~ * label[for=f-k100],
  #f-k1000:checked ~ * label[for=f-k1000],
  #f-oneu:checked ~ * label[for=f-oneu],
  #f-obald:checked ~ * label[for=f-obald],
  #f-okosten:checked ~ * label[for=f-okosten] {{
    background: var(--text); color: var(--bg); border-color: var(--text);
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    font-weight: 600;
  }}
  #f-aktiv:checked ~ * label[for=f-aktiv] .fc,
  #f-anwendbar:checked ~ * label[for=f-anwendbar] .fc,
  #f-tot:checked ~ * label[for=f-tot] .fc,
  #f-compliance:checked ~ * label[for=f-compliance] .fc,
  #f-nachweis:checked ~ * label[for=f-nachweis] .fc,
  #f-datenprodukt:checked ~ * label[for=f-datenprodukt] .fc,
  #f-vermittlung:checked ~ * label[for=f-vermittlung] .fc,
  #f-k10:checked ~ * label[for=f-k10] .fc,
  #f-k100:checked ~ * label[for=f-k100] .fc,
  #f-k1000:checked ~ * label[for=f-k1000] .fc {{ color: rgba(255,255,255,0.75); }}

  /* Body-Marker: sichtbarer Hinweis wenn ueberhaupt gefiltert wird */
  body.filter-aktiv .toolbar {{
    box-shadow: 0 2px 0 var(--text);
  }}

  .empty-filter {{
    text-align: center; padding: 48px 20px;
    color: var(--muted); font-size: 14px;
    background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius);
  }}
  .empty-filter button {{
    margin-left: 8px; padding: 4px 12px;
    border: 1px solid var(--border-strong); border-radius: 999px;
    background: transparent; color: var(--text); cursor: pointer;
    font-family: inherit; font-size: 13px;
  }}
  .empty-filter button:hover {{ background: var(--text); color: var(--bg); }}

  /* Filter/Suche via JS: kombiniert Status x Typ x Suche */
  .card.hidden-filter {{ display: none !important; }}
  .rubrik.hidden-filter {{ display: none !important; }}

  .titel-muster {{
    color: var(--muted); font-weight: 500; font-size: 13.5px;
    margin-left: 4px; letter-spacing: 0;
  }}

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
  .bewertung-rubrik {{ margin-bottom: 20px; }}
  .bewertung-rubrik > summary {{
    list-style: none; cursor: pointer;
    padding: 6px 0;
  }}
  .bewertung-rubrik > summary::-webkit-details-marker {{ display: none; }}
  .bewertung-rubrik > summary::before {{
    content: "▸"; margin-right: 8px; color: var(--muted);
    display: inline-block; transition: transform 150ms ease;
  }}
  .bewertung-rubrik[open] > summary::before {{ transform: rotate(90deg); }}
  .bewertung-interessant .rubrik-titel {{ color: var(--amber); }}
  .bewertung-verworfen .rubrik-titel {{ color: var(--muted); }}

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
  .bewertung-dot {{
    flex-shrink: 0; display: inline-flex; align-items: center;
    justify-content: center;
    width: 18px; height: 18px; border-radius: 50%;
    font-size: 11px; font-weight: 700; line-height: 1;
    background: var(--surface-3); color: var(--muted);
    border: 1px solid var(--border);
  }}
  .bewertung-dot[data-status="interessant"] {{
    color: var(--amber); border-color: var(--amber);
    background: rgba(146,64,14,0.08);
  }}
  .bewertung-dot[data-status="beobachten"] {{
    color: var(--text-soft); border-color: var(--border-strong);
  }}
  .bewertung-dot[data-status="verworfen"] {{
    color: var(--muted); border-color: var(--border);
    background: var(--surface-3);
  }}
  .card[data-bewertung="verworfen"] .card-titel {{
    opacity: 0.55; text-decoration: line-through;
    text-decoration-color: rgba(0,0,0,0.2);
  }}
  .card.faded-out {{
    opacity: 0.35; transition: opacity 400ms ease;
    pointer-events: none;
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

  .bewerten-gruppe {{
    display: flex; gap: 6px; margin-top: 12px;
    padding-top: 12px; border-top: 1px dashed var(--border);
  }}
  .bewerten {{
    flex: 1; font-size: 12px; padding: 5px 8px; border-radius: 6px;
    font-family: inherit; cursor: pointer; text-align: center;
    color: var(--muted); background: transparent;
    border: 1px solid var(--border); transition: all 120ms ease;
    white-space: nowrap;
  }}
  .bewerten:hover {{ color: var(--text); border-color: var(--border-strong); }}
  .bewerten.aktiv {{
    color: var(--text); font-weight: 600;
    background: var(--surface-3); border-color: var(--border-strong);
  }}
  .bewerten.aktiv[data-status="interessant"] {{
    color: var(--amber); border-color: var(--amber);
    background: rgba(146,64,14,0.08);
  }}
  .bewerten.aktiv[data-status="verworfen"] {{
    color: var(--muted); border-color: var(--muted);
    background: var(--surface-3); text-decoration: line-through;
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
<input type="radio" name="ft" id="f-datenprodukt">
<input type="radio" name="ft" id="f-vermittlung">
<input type="radio" name="fk" id="f-kall" checked>
<input type="radio" name="fk" id="f-k10">
<input type="radio" name="fk" id="f-k100">
<input type="radio" name="fk" id="f-k1000">
<input type="radio" name="fo" id="f-oscore" checked>
<input type="radio" name="fo" id="f-oneu">
<input type="radio" name="fo" id="f-obald">
<input type="radio" name="fo" id="f-okosten">
<input type="radio" name="fb" id="f-ball" checked>
<input type="radio" name="fb" id="f-bbewertet">
<input type="radio" name="fb" id="f-binteressant">
<input type="radio" name="fb" id="f-bbeobachten">
<input type="radio" name="fb" id="f-bverworfen">

<header class="site-header">
  <div class="header-inner">
    <div class="titelzeile">
      <h1>Legal Radar</h1>
      <div class="sub">
        Stand {stand} &nbsp;·&nbsp; {n} Vorgang{"e" if n != 1 else ""}
        &nbsp;·&nbsp;
        <span id="bewertungs-fortschritt" class="fortschritt">0 von {n} bewertet</span>
      </div>
    </div>
    <p class="claim">
      Frühwarnsystem für Bundestags-Gesetzgebung: welche neuen Pflichten,
      Kosten oder Marktchancen entstehen aktuell für die Wirtschaft.
    </p>
  </div>
</header>

<section class="bewertungs-hero" aria-label="Bewertungs-Uebersicht">
  <div class="hero-inner">
    <button type="button" class="hero-tile aktiv" data-hero="ball">
      <span class="tile-count" data-count="all">{n}</span>
      <span class="tile-label">Alle Vorgaenge</span>
    </button>
    <button type="button" class="hero-tile hero-interessant" data-hero="binteressant">
      <span class="tile-count" data-count="interessant">0</span>
      <span class="tile-label">★ Interessant</span>
      <span class="tile-hint">Push-Alerts per Mail</span>
    </button>
    <button type="button" class="hero-tile hero-beobachten" data-hero="bbeobachten">
      <span class="tile-count" data-count="beobachten">0</span>
      <span class="tile-label">◐ Beobachten</span>
      <span class="tile-hint">Zurueckgestellt</span>
    </button>
    <button type="button" class="hero-tile hero-verworfen" data-hero="bverworfen">
      <span class="tile-count" data-count="verworfen">0</span>
      <span class="tile-label">✕ Verworfen</span>
      <span class="tile-hint">Als irrelevant markiert</span>
    </button>
  </div>
</section>

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
      <label for="f-datenprodukt">Datenprodukt
        <span class="fc">({fc["datenprodukt"]})</span></label>
      <label for="f-vermittlung">Vermittlung
        <span class="fc">({fc["vermittlung"]})</span></label>
    </div>
    <div class="filter-row">
      <span class="filter-label">Kosten</span>
      <label for="f-kall">Alle</label>
      <label for="f-k10">&gt; 10 Mio € <span class="fc">({fc["k10"]})</span></label>
      <label for="f-k100">&gt; 100 Mio € <span class="fc">({fc["k100"]})</span></label>
      <label for="f-k1000">&gt; 1 Mrd € <span class="fc">({fc["k1000"]})</span></label>
    </div>
    <div class="filter-row">
      <span class="filter-label">Sortiert</span>
      <label for="f-oscore">Relevanz</label>
      <label for="f-oneu">Neueste</label>
      <label for="f-obald">Bald geltend</label>
      <label for="f-okosten">Höchste Kosten</label>
    </div>
  </div>
</div>

<main>
  {summary}
  {bewertung}
  {neu}
  {gruppen}
  <p id="empty-filter" class="empty-filter" style="display:none">
    Keine Treffer für diese Filterkombination.
    <button type="button" id="reset-filter">Filter zurücksetzen</button>
  </p>
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

  // Watchlist/Unwatch entfernt - 'Interessant' uebernimmt die Rolle.

  // --- Bewerten: setzen / umbewerten / entfernen ---
  var BEWERTUNG_SYMBOL = {{interessant: '★', beobachten: '◐', verworfen: '✕'}};

  function alterStatusVon(id) {{
    var vorhandener = document.querySelector(
      '.card[data-vorgang="' + CSS.escape(id) + '"] button.bewerten.aktiv'
    );
    return vorhandener ? vorhandener.getAttribute('data-status') : '';
  }}

  function syncKartenUI(id, neuerStatus) {{
    // Alle Karten-Instanzen mit gleicher vorgang-id synchron aktualisieren
    // (Karten koennen doppelt vorkommen: einmal in Bewertungs-Sektion,
    //  einmal in Gruppen-Sektion).
    var karten = document.querySelectorAll('.card[data-vorgang="' + CSS.escape(id) + '"]');
    karten.forEach(function(card) {{
      card.setAttribute('data-bewertung', neuerStatus);
      // Buttons updaten
      card.querySelectorAll('button.bewerten').forEach(function(b) {{
        var isNeu = b.getAttribute('data-status') === neuerStatus;
        b.classList.toggle('aktiv', isNeu);
      }});
      // Dot im Header aktualisieren
      var zeile = card.querySelector('.card-titel-zeile');
      var alterDot = card.querySelector('.bewertung-dot');
      if (alterDot) alterDot.remove();
      if (neuerStatus) {{
        var dot = document.createElement('span');
        dot.className = 'bewertung-dot';
        dot.setAttribute('data-status', neuerStatus);
        dot.title = 'Bewertung: ' + neuerStatus;
        dot.textContent = BEWERTUNG_SYMBOL[neuerStatus] || '';
        // vor h3.card-titel einfuegen
        var titel = zeile.querySelector('.card-titel');
        zeile.insertBefore(dot, titel);
      }}
      // Karte in Bewertungs-Sektion, die jetzt nicht mehr passt: ausblenden
      var sektion = card.closest('details.bewertung-rubrik');
      if (sektion) {{
        var sektStatus = sektion.className.match(/bewertung-(interessant|beobachten|verworfen)/);
        if (sektStatus && sektStatus[1] !== neuerStatus) {{
          card.classList.add('faded-out');
        }} else {{
          card.classList.remove('faded-out');
        }}
      }}
    }});
    updateFortschritt();
  }}

  document.addEventListener('click', async function(e) {{
    var btn = e.target.closest('button.bewerten');
    if (!btn) return;
    e.preventDefault();

    if (!WATCH_ENDPOINT || !WATCH_TOKEN) {{
      toast('Bewerten braucht Worker-Konfiguration.', true);
      return;
    }}

    var id     = btn.getAttribute('data-vorgang');
    var titel  = btn.getAttribute('data-titel') || '';
    var status = btn.getAttribute('data-status');
    var istAktiv = btn.classList.contains('aktiv');
    var effektiverStatus = istAktiv ? 'entfernen' : status;

    // Downgrade-Warnung: von interessant nach verworfen ohne Mail-Loop-Verlust nachfragen
    if (!istAktiv && status === 'verworfen') {{
      var alter = alterStatusVon(id);
      if (alter === 'interessant') {{
        if (!confirm('Von Interessant nach Verworfen degradieren? Push-Alerts entfallen.')) {{
          return;
        }}
      }}
    }}

    btn.disabled = true;
    try {{
      var r = await callWorker('/bewerten', {{id: id, titel: titel, status: effektiverStatus}});
      if (r.ok) {{
        var neuerStatus = effektiverStatus === 'entfernen' ? '' : status;
        syncKartenUI(id, neuerStatus);
        toast(neuerStatus ? 'Bewertung: ' + neuerStatus : 'Bewertung entfernt');
      }} else {{
        toast('Fehler: ' + (r.data.error || r.status), true);
      }}
    }} catch (err) {{
      toast('Netzwerkfehler: ' + err.message, true);
    }} finally {{
      btn.disabled = false;
    }}
  }});

  // Fortschritt + Hero-Kachel-Counts. Alle Werte werden aus dem DOM
  // berechnet und deduped ueber data-vorgang, weil Karten doppelt
  // gerendert werden (Bewertungs-Sektion + Gruppen-Sektion).
  function updateFortschritt() {{
    var alleIds = new Set();
    var perStatus = {{interessant: new Set(), beobachten: new Set(), verworfen: new Set()}};
    document.querySelectorAll('.card[data-vorgang]').forEach(function(card) {{
      var id = card.getAttribute('data-vorgang');
      alleIds.add(id);
      var s = card.getAttribute('data-bewertung');
      if (s && perStatus[s]) perStatus[s].add(id);
    }});
    var bewertetN = perStatus.interessant.size + perStatus.beobachten.size
                  + perStatus.verworfen.size;
    var el = document.getElementById('bewertungs-fortschritt');
    if (el) el.textContent = bewertetN + ' von ' + alleIds.size + ' bewertet';

    var counts = {{
      all: alleIds.size,
      interessant: perStatus.interessant.size,
      beobachten: perStatus.beobachten.size,
      verworfen: perStatus.verworfen.size,
    }};
    Object.keys(counts).forEach(function(k) {{
      var el = document.querySelector('[data-count="' + k + '"]');
      if (el) el.textContent = counts[k];
    }});
  }}
  updateFortschritt();

  // Hero-Kacheln als Bewertungs-Filter
  document.querySelectorAll('.hero-tile').forEach(function(tile) {{
    tile.addEventListener('click', function() {{
      var ziel = tile.getAttribute('data-hero');  // ball|binteressant|...
      // Toggle: Klick auf aktive Kachel = zurueck zu ball
      var istAktiv = tile.classList.contains('aktiv');
      var neuesRadio = istAktiv ? 'f-ball' : 'f-' + ziel;
      var input = document.getElementById(neuesRadio);
      if (input) {{
        input.checked = true;
        applyFilters();
      }}
    }});
  }});

  function updateHeroAktiv() {{
    var aktuell = selected('fb');  // ball|bbewertet|bunbewertet|binteressant|...
    document.querySelectorAll('.hero-tile').forEach(function(tile) {{
      tile.classList.toggle('aktiv', tile.getAttribute('data-hero') === aktuell);
    }});
  }}

  // --- Filter/Suche/Sortierung kombiniert ---
  var suche = document.getElementById('suche');
  var suchTimer = null;
  var emptyEl = document.getElementById('empty-filter');

  var STATUS_STADIEN = {{
    aktiv: ['referentenentwurf', 'kabinett', 'bt', 'ausschuss'],
    anwendbar: ['anwendbar', 'verkuendet'],
    tot: ['tot'],
  }};
  var KOSTEN_MIN = {{ kall: 0, k10: 10000000, k100: 100000000, k1000: 1000000000 }};

  function selected(name) {{
    var el = document.querySelector('input[name=' + name + ']:checked');
    return el ? el.id.replace(/^f-/, '') : '';
  }}

  function sortValue(card, mode) {{
    if (mode === 'oneu')    return card.getAttribute('data-erstgesehen') || '';
    if (mode === 'obald')   {{
      var v = card.getAttribute('data-anwendungsbeginn');
      return v || '9999-12-31';  // ohne Datum ans Ende
    }}
    if (mode === 'okosten') return parseInt(card.getAttribute('data-kosten') || '0', 10);
    return null;  // 'oscore' = DOM-Reihenfolge = SQL-Sortierung
  }}

  function applySort(mode) {{
    if (mode === 'oscore') return;  // Server-Reihenfolge belassen
    document.querySelectorAll('main .cards').forEach(function(container) {{
      var cards = Array.prototype.slice.call(container.querySelectorAll(':scope > .card'));
      cards.sort(function(a, b) {{
        var va = sortValue(a, mode), vb = sortValue(b, mode);
        if (mode === 'okosten') return vb - va;             // hoch -> tief
        if (mode === 'oneu')    return vb.localeCompare(va); // neu -> alt
        return va.localeCompare(vb);                         // bald -> spaet
      }});
      cards.forEach(function(c) {{ container.appendChild(c); }});
    }});
  }}

  function applyFilters() {{
    var status = selected('fs');
    var muster = selected('ft');
    var kosten = selected('fk');
    var sort   = selected('fo');
    var bew    = selected('fb');
    var q = (suche && suche.value || '').trim().toLowerCase();
    var stadien = STATUS_STADIEN[status] || null;
    var minK = KOSTEN_MIN[kosten] || 0;
    var anySichtbar = false;

    document.querySelectorAll('.card').forEach(function(c) {{
      var hide = false;
      if (stadien && stadien.indexOf(c.getAttribute('data-stadium')) < 0) hide = true;
      if (!hide && muster !== 'mall' && c.getAttribute('data-muster') !== muster) hide = true;
      if (!hide && minK > 0) {{
        var k = parseInt(c.getAttribute('data-kosten') || '0', 10);
        if (k <= minK) hide = true;
      }}
      if (!hide && q && (c.getAttribute('data-titel') || '').indexOf(q) < 0) hide = true;
      var cBew = c.getAttribute('data-bewertung');
      if (!hide && bew === 'bbewertet' && !cBew) hide = true;
      if (!hide && bew === 'binteressant' && cBew !== 'interessant') hide = true;
      if (!hide && bew === 'bbeobachten' && cBew !== 'beobachten') hide = true;
      if (!hide && bew === 'bverworfen' && cBew !== 'verworfen') hide = true;
      c.classList.toggle('hidden-filter', hide);
      if (!hide) anySichtbar = true;
    }});

    document.querySelectorAll('main .rubrik').forEach(function(r) {{
      var any = r.querySelector('.card:not(.hidden-filter)');
      r.classList.toggle('hidden-filter', !any);
    }});
    if (emptyEl) emptyEl.style.display = anySichtbar ? 'none' : '';

    applySort(sort);
    syncUrl(status, muster, kosten, sort, q, bew);
    if (typeof updateHeroAktiv === 'function') updateHeroAktiv();

    // Body-Klasse fuer sichtbaren Filter-Aktiv-Zustand (Toolbar-Underline).
    var istGefiltert = (
      status !== 'all' || muster !== 'mall' || kosten !== 'kall'
      || sort !== 'oscore' || bew !== 'ball' || q
    );
    document.body.classList.toggle('filter-aktiv', !!istGefiltert);
  }}

  // --- URL-State ---
  function syncUrl(s, t, k, o, q, b) {{
    var p = new URLSearchParams();
    if (s !== 'all')     p.set('s', s);
    if (t !== 'mall')    p.set('t', t);
    if (k !== 'kall')    p.set('k', k);
    if (o !== 'oscore')  p.set('o', o);
    if (b && b !== 'ball') p.set('b', b);
    if (q)               p.set('q', q);
    var qs = p.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
  }}
  function restoreFromUrl() {{
    var p = new URLSearchParams(location.search);
    var map = {{ s: 'fs', t: 'ft', k: 'fk', o: 'fo', b: 'fb' }};
    Object.keys(map).forEach(function(key) {{
      var v = p.get(key);
      if (!v) return;
      var el = document.getElementById('f-' + v);
      if (el && el.name === map[key]) el.checked = true;
    }});
    var q = p.get('q');
    if (q && suche) suche.value = q;
  }}

  document.querySelectorAll(
    'input[name=fs], input[name=ft], input[name=fk], input[name=fo], input[name=fb]'
  ).forEach(function(el) {{ el.addEventListener('change', applyFilters); }});
  if (suche) {{
    suche.addEventListener('input', function() {{
      if (suchTimer) clearTimeout(suchTimer);
      suchTimer = setTimeout(applyFilters, 120);
    }});
  }}
  var resetBtn = document.getElementById('reset-filter');
  if (resetBtn) resetBtn.addEventListener('click', function() {{
    ['f-all', 'f-mall', 'f-kall', 'f-oscore', 'f-ball'].forEach(function(id) {{
      var el = document.getElementById(id);
      if (el) el.checked = true;
    }});
    if (suche) suche.value = '';
    applyFilters();
  }});

  restoreFromUrl();
  applyFilters();

  // --- Keyboard ---
  document.addEventListener('keydown', function(e) {{
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') {{
      if (e.key === 'Escape' && e.target === suche) {{
        suche.value = '';
        applyFilters();
        suche.blur();
      }}
      return;
    }}
    if (e.key === '/' && suche) {{
      e.preventDefault();
      suche.focus();
    }} else if (e.key === 'Escape') {{
      ['f-all', 'f-mall', 'f-kall', 'f-oscore', 'f-ball'].forEach(function(id) {{
        var el = document.getElementById(id);
        if (el) el.checked = true;
      }});
      if (suche) suche.value = '';
      applyFilters();
    }} else if (['1', '2', '3', '0'].indexOf(e.key) >= 0) {{
      // Keyboard-Bewertung: aktive Karte finden (aufgeklappte details.card)
      var karte = document.querySelector('details.card[open]');
      if (!karte) return;
      var mapping = {{'1': 'interessant', '2': 'beobachten', '3': 'verworfen', '0': 'entfernen'}};
      var ziel = mapping[e.key];
      if (ziel === 'entfernen') {{
        var aktiv = karte.querySelector('button.bewerten.aktiv');
        if (aktiv) aktiv.click();
      }} else {{
        var btn = karte.querySelector('button.bewerten[data-status="' + ziel + '"]');
        // Klick nur auslosen wenn nicht schon aktiv (Klick wuerde sonst entfernen)
        if (btn && !btn.classList.contains('aktiv')) btn.click();
      }}
      e.preventDefault();
    }}
  }});
}})();
</script>
</body>
</html>
"""
