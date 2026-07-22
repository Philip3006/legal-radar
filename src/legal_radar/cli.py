from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import anthropic
import typer

from legal_radar.core import db, github, hashing, smtp
from legal_radar.core.config import Settings
from legal_radar.digest import summary as summary_mod
from legal_radar.digest.events import Event, events_since
from legal_radar.digest.html import render_html
from legal_radar.digest.mail import render_mail, render_watchlist_mail
from legal_radar.digest.render import render
from legal_radar.extract import llm, rules, verify
from legal_radar.score import deterministic
from legal_radar.sources.bgbl_rss import BgblRss
from legal_radar.sources.dip import Dip

app = typer.Typer(add_completion=False, help="legal-radar")


def _require_env(s: Settings, keys: list[str]) -> None:
    fehlend = [k for k in keys if not getattr(s, k)]
    if fehlend:
        typer.echo(
            f"Fehlende Konfiguration: {', '.join(fehlend)}. "
            f"Setze sie in .env oder als Umgebungsvariable.",
            err=True,
        )
        raise typer.Exit(1)


def _parse_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_datum(v) -> str | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        return None


@app.command()
def init() -> None:
    """Datenbank anlegen / migrieren."""
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)
    typer.echo(f"ok: {s.db_path}")


@app.command()
def fetch(source: str = "dip", since: str = "2024-01-01", dry_run: bool = False) -> None:
    """Quelle einlesen, Vorgaenge upserten, Historie schreiben."""
    s = Settings.load()
    _require_env(s, ["anthropic_api_key"])
    con = db.connect(s.db_path)
    db.migrate(con)

    if source == "dip":
        _require_env(s, ["dip_api_key"])
        adapter = Dip(s.dip_api_key)
    elif source == "bgbl":
        adapter = BgblRss()
    else:
        typer.echo(f"Unbekannte Quelle: {source}. Verfuegbar: dip, bgbl.", err=True)
        raise typer.Exit(1)

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    # Append-only, sonst ist der Prefilter blind (CLAUDE.md).
    # Ein Run-Marker macht spaetere Auswertungen pro Run moeglich.
    rejected = Path("data/rejected.jsonl")
    rejected.parent.mkdir(parents=True, exist_ok=True)
    run_ts = date.today().isoformat()
    with rejected.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "run_start", "ts": run_ts, "source": source}) + "\n")

    def log_rejected(vid: str, grund: str) -> None:
        entry = {"id": vid, "grund": grund, "ts": run_ts}
        with rejected.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    vorgaenge = adapter.fetch(since)
    typer.echo(f"{source}: {len(vorgaenge)} Vorgaenge geladen")

    n_neu = n_geaendert = n_gefiltert = n_fehler = 0

    for v in vorgaenge:
        text = adapter.text_fuer_vorgang(v.id)
        v.rohtext = text

        # Textlose Quellen (BGBl-RSS): Metadaten trotzdem persistieren,
        # damit Stadienwechsel (bt -> verkuendet) in der History landen.
        if not text:
            row = {
                "id": v.id,
                "quelle": v.quelle,
                "titel": v.titel,
                "stadium": v.stadium,
                "quelle_url": v.quelle_url,
                "anwendungsbeginn": v.anwendungsbeginn.isoformat() if v.anwendungsbeginn else None,
                "muster": "keins",
                "input_hash": hashing.input_hash(v),
            }
            if dry_run:
                typer.echo(f"  [dry-run] {v.id}: {v.titel[:70]}")
                continue
            changes = db.upsert(con, row)
            if any(c[0] == "__neu__" for c in changes):
                n_neu += 1
            elif changes:
                n_geaendert += 1
            continue

        if not rules.passes_prefilter(text, s.prefilter_min_aufwand_eur):
            n_gefiltert += 1
            log_rejected(v.id, "prefilter")
            continue

        # Deterministische Extraktion — kein LLM-Risiko
        v.erf_aufwand_eur = rules.erfuellungsaufwand_wirtschaft(text)
        v.durchsetzung.bussgeld_eur = rules.bussgeld(text)
        behoerde_str, behoerde_neu = rules.behoerde(text)
        v.durchsetzung.behoerde = behoerde_str
        v.durchsetzung.behoerde_neu = behoerde_neu
        v.zulassung_noetig = rules.zulassung_noetig(text)

        h = hashing.input_hash(v)
        cached = db.cached_llm(con, h)
        if cached:
            llm_data = json.loads(cached)
        else:
            llm_data = llm.extract(client, text)
            if llm_data is None:
                n_fehler += 1
                log_rejected(v.id, "llm_parse_fehler")
                continue
            if not dry_run:
                db.put_llm(con, h, json.dumps(llm_data))

        v.muster = llm_data.get("muster", "keins")

        # LLM-Belege nur akzeptieren, wenn Zitat im Rohtext steht und Zahl konsistent ist.
        # Regex bleibt Primaerquelle; LLM fuellt nur, was die Regex nicht gefunden hat.
        belege = llm_data.get("belege") or {}
        erf_ll = verify.verify_eur(belege.get("erf_aufwand_eur"), text)
        buss_ll = verify.verify_eur(belege.get("bussgeld_eur"), text)
        einm_ll = verify.verify_eur(belege.get("einmalaufwand_eur"), text)
        betr_ll = verify.verify_int(belege.get("betroffene"), text)

        erf = v.erf_aufwand_eur if v.erf_aufwand_eur is not None else erf_ll
        buss = v.durchsetzung.bussgeld_eur if v.durchsetzung.bussgeld_eur is not None else buss_ll

        # Verworfene LLM-Vorschlaege loggen, damit der Cross-Check auditierbar ist.
        for feld, roh, verifiziert in (
            ("erf_aufwand_eur", belege.get("erf_aufwand_eur"), erf_ll),
            ("bussgeld_eur", belege.get("bussgeld_eur"), buss_ll),
            ("einmalaufwand_eur", belege.get("einmalaufwand_eur"), einm_ll),
            ("betroffene", belege.get("betroffene"), betr_ll),
        ):
            if roh and verifiziert is None:
                log_rejected(v.id, f"llm_verify_fail:{feld}")

        row = {
            "id": v.id,
            "quelle": v.quelle,
            "titel": v.titel,
            "stadium": v.stadium,
            "quelle_url": v.quelle_url,
            "anwendungsbeginn": _parse_datum(llm_data.get("anwendungsbeginn")),
            "betroffene": betr_ll,
            "einmalaufwand_eur": einm_ll,
            "erf_aufwand_eur": erf,
            "bussgeld_eur": buss,
            "behoerde": v.durchsetzung.behoerde,
            "behoerde_neu": 1 if v.durchsetzung.behoerde_neu else 0,
            "zulassung_noetig": 1 if v.zulassung_noetig else 0,
            "muster": v.muster,
            "input_hash": h,
        }

        if dry_run:
            typer.echo(f"  [dry-run] {v.id}: {v.titel[:70]}")
            continue

        changes = db.upsert(con, row)
        if any(c[0] == "__neu__" for c in changes):
            n_neu += 1
        elif changes:
            n_geaendert += 1

        # Pflichten aus LLM neu schreiben (append-only History waere Overkill).
        con.execute("DELETE FROM pflicht WHERE vorgang_id = ?", (v.id,))
        for p in llm_data.get("pflichten") or []:
            if not isinstance(p, dict):
                continue
            typ, geg = p.get("typ"), p.get("gegenstand")
            if not typ or not geg:
                continue
            con.execute(
                "INSERT INTO pflicht (vorgang_id, typ, gegenstand, frequenz) VALUES (?, ?, ?, ?)",
                (v.id, typ, geg, p.get("frequenz")),
            )
        con.commit()

    typer.echo(
        f"Ergebnis: {n_neu} neu, {n_geaendert} geaendert, "
        f"{n_gefiltert} gefiltert, {n_fehler} Fehler"
    )


@app.command()
def score(dry_run: bool = False) -> None:
    """Bewertet alle Vorgaenge deren score_hash != input_hash ist."""
    s = Settings.load()
    con = db.connect(s.db_path)

    rows = con.execute(
        "SELECT * FROM vorgang "
        "WHERE input_hash IS NOT NULL "
        "  AND (score_hash IS NULL OR score_hash != input_hash)"
    ).fetchall()
    typer.echo(f"{len(rows)} Vorgaenge zu bewerten")

    n = 0
    for row in rows:
        anw = row["anwendungsbeginn"]
        score_val = deterministic.score(
            erf_aufwand_eur=row["erf_aufwand_eur"],
            betroffene=row["betroffene"],
            anwendungsbeginn=date.fromisoformat(anw) if anw else None,
            muster=row["muster"] or "keins",
            bussgeld_eur=row["bussgeld_eur"],
            behoerde=row["behoerde"],
            behoerde_neu=bool(row["behoerde_neu"]),
            zulassung_noetig=bool(row["zulassung_noetig"]),
        )
        if dry_run:
            typer.echo(f"  {row['id']}: score={score_val:.3f}  {row['titel'][:60]}")
            continue
        con.execute(
            "UPDATE vorgang SET score = ?, score_hash = ? WHERE id = ?",
            (score_val, row["input_hash"], row["id"]),
        )
        n += 1

    if not dry_run:
        con.commit()
        typer.echo(f"{n} Scores geschrieben")


@app.command()
def digest(since: str = "7d", send_mail: bool = False) -> None:
    """Ereignis-Digest ausgeben und optional per E-Mail versenden.

    Default: nur stdout. Mit --send-mail geht die Mail an digest_empfaenger.
    """
    s = Settings.load()
    con = db.connect(s.db_path)
    tage = int(since.rstrip("d"))
    events = events_since(con, tage)
    kw = f"letzte {tage} Tage"
    text = render(events, kw=kw)
    typer.echo(text)

    if send_mail and s.smtp_url and s.digest_empfaenger:
        gesendet = smtp.send(
            subject=f"Legal Radar — {kw}",
            body=text,
            html_body=render_mail(events, kw=kw),
            smtp_url=s.smtp_url,
            recipients=s.digest_empfaenger,
            sender=s.digest_absender,
        )
        if gesendet:
            typer.echo(f"\n-> Digest an {len(s.digest_empfaenger)} Empfaenger versandt.")


@app.command("render-dashboard")
def render_dashboard(
    out: Path = Path("docs/index.html"),
    skip_summary: bool = False,
) -> None:
    """Statisches HTML-Dashboard aus DB erzeugen.

    Liest Watchlist von GitHub (wenn GITHUB_TOKEN gesetzt) und ruft die
    LLM-Wochenzusammenfassung (wenn ANTHROPIC_API_KEY gesetzt und nicht --skip-summary).
    """
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)

    summary_text = None
    if not skip_summary and s.anthropic_api_key:
        try:
            client = anthropic.Anthropic(api_key=s.anthropic_api_key)
            summary_text = summary_mod.erzeuge_summary(con, client)
        except Exception as e:
            # LLM-Fehler soll das Dashboard-Rendering nicht killen
            typer.echo(f"Summary-Fehler ignoriert: {e}", err=True)

    watched = set(github.liste_watchlist_ids(s.radar_repo, s.github_token))
    if watched:
        typer.echo(f"Watchlist: {len(watched)} Vorgang(e)")

    bewertungen = github.liste_bewertungen(s.radar_repo, s.github_token)
    if bewertungen:
        typer.echo(f"Bewertungen: {len(bewertungen)} Vorgang(e)")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_html(
            con,
            summary_text=summary_text,
            watched_ids=watched,
            radar_repo=s.radar_repo,
            watch_endpoint=s.watch_endpoint,
            watch_token=s.watch_token,
            bewertungen=bewertungen,
        ),
        encoding="utf-8",
    )
    typer.echo(f"ok: {out}")


@app.command("watchlist-digest")
def watchlist_digest(since: str = "1d", send_mail: bool = False) -> None:
    """Taeglicher Watchlist-Digest.

    Liest die Watchlist von GitHub, prueft Aenderungen der letzten N Tage,
    schickt Mail nur wenn tatsaechlich Aenderungen vorliegen.
    """
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)
    tage = int(since.rstrip("d"))

    watched = set(github.liste_watchlist_ids(s.radar_repo, s.github_token))
    if not watched:
        typer.echo("Watchlist ist leer. Keine Mail.")
        return

    alle_events = events_since(con, tage)
    events: list[Event] = [e for e in alle_events if e.vorgang_id in watched]

    if not events:
        typer.echo(f"Keine Aenderungen an {len(watched)} beobachteten Vorgaengen. Keine Mail.")
        return

    kw = f"letzte {tage} Tag{'e' if tage != 1 else ''}"
    text = render(events, kw=kw)
    typer.echo(text)

    if send_mail and s.smtp_url and s.digest_empfaenger:
        gesendet = smtp.send(
            subject=f"Watchlist-Update — {len(events)} Bewegung(en)",
            body=text,
            html_body=render_watchlist_mail(events, kw=kw),
            smtp_url=s.smtp_url,
            recipients=s.digest_empfaenger,
            sender=s.digest_absender,
        )
        if gesendet:
            typer.echo(f"\n-> Watchlist-Digest an {len(s.digest_empfaenger)} Empfaenger.")


@app.command()
def bewerten(vorgang_id: str, status: str, begruendung: str = "") -> None:
    """Nutzer-Bewertung setzen: interessant | beobachten | verworfen."""
    if status not in ("interessant", "beobachten", "verworfen"):
        typer.echo(f"Ungueltiger Status: {status}", err=True)
        raise typer.Exit(1)

    s = Settings.load()
    con = db.connect(s.db_path)
    exists = con.execute("SELECT 1 FROM vorgang WHERE id = ?", (vorgang_id,)).fetchone()
    if not exists:
        typer.echo(f"Vorgang {vorgang_id} nicht in DB.", err=True)
        raise typer.Exit(1)

    con.execute(
        "INSERT OR REPLACE INTO bewertung_user (vorgang_id, status, begruendung, ts) "
        "VALUES (?, ?, ?, ?)",
        (vorgang_id, status, begruendung, date.today().isoformat()),
    )
    con.commit()
    typer.echo(f"ok: {vorgang_id} -> {status}")


if __name__ == "__main__":
    app()
