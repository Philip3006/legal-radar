from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

import anthropic
import typer

from legal_radar.core import db, github, hashing, matching, smtp
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


def _finde_dip_match(con, bgbl_titel: str):
    """Sucht einen DIP-Vorgang mit gleichem Titel-Kern. None wenn kein Treffer.

    Normalisierung siehe core/matching.py. Kein Fuzzy - lieber verpassen als
    falsch verheiraten.
    """
    ziel = matching.titel_normalize(bgbl_titel)
    if len(ziel) < 20:
        return None
    for row in con.execute(
        "SELECT * FROM vorgang WHERE quelle = 'dip' AND stadium != 'verkuendet'"
    ):
        if matching.titel_normalize(row["titel"] or "") == ziel:
            return row
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
            anw = v.anwendungsbeginn.isoformat() if v.anwendungsbeginn else None
            # Existiert der Vorgang schon als DIP-Eintrag? Dann ist die BGBl-
            # Meldung ein Stadienwechsel des DIP-Vorgangs, kein neuer Vorgang.
            dip_match = _finde_dip_match(con, v.titel) if v.quelle == "bgbl" else None
            if dip_match:
                bestehende_row = dict(dip_match)
                update = {
                    "id": bestehende_row["id"],
                    "quelle": bestehende_row["quelle"],
                    "titel": bestehende_row["titel"],
                    "stadium": "verkuendet",
                    "quelle_url": bestehende_row["quelle_url"],
                    "anwendungsbeginn": anw or bestehende_row.get("anwendungsbeginn"),
                    "muster": bestehende_row.get("muster") or "keins",
                    "input_hash": bestehende_row["input_hash"],
                }
                if dry_run:
                    typer.echo(f"  [dry-run] {v.id} -> match {bestehende_row['id']}")
                    continue
                changes = db.upsert(con, update)
                if changes:
                    n_geaendert += 1
                continue
            row = {
                "id": v.id,
                "quelle": v.quelle,
                "titel": v.titel,
                "stadium": v.stadium,
                "quelle_url": v.quelle_url,
                "anwendungsbeginn": anw,
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

    bewertungen = github.liste_bewertungen(s.radar_repo, s.github_token)
    if bewertungen:
        typer.echo(f"Bewertungen: {len(bewertungen)} Vorgang(e)")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_html(
            con,
            summary_text=summary_text,
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
    """Taeglicher Digest der als 'interessant' bewerteten Vorgaenge.

    'Interessant' im Dashboard = automatische Push-Notification. Es gibt keine
    separate Watchlist mehr - eine Bewertung ist die Quelle der Wahrheit.
    """
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)
    tage = int(since.rstrip("d"))

    watched = {
        r["vorgang_id"]
        for r in con.execute("SELECT vorgang_id FROM bewertung_user WHERE status = 'interessant'")
    }
    if not watched:
        typer.echo("Keine 'interessant'-Bewertungen. Keine Mail.")
        return

    alle_events = events_since(con, tage)
    events: list[Event] = [e for e in alle_events if e.vorgang_id in watched]

    if not events:
        typer.echo(f"Keine Aenderungen an {len(watched)} interessanten Vorgaengen. Keine Mail.")
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


@app.command("sync-bewertungen")
def sync_bewertungen() -> None:
    """GitHub-Issue-Bewertungen in die DB-Tabelle bewertung_user spiegeln.

    Klicks im Dashboard landen als Issues mit Label 'bewertung'. Fuer
    Score-Kalibrierung brauchen wir sie aber in der DB. Der Sync ist
    idempotent (INSERT OR REPLACE), also unbedenklich im Cron.
    """
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)

    # Ohne Repo/Token koennen wir nicht sicher zwischen 'keine Bewertungen'
    # und 'GitHub nicht erreichbar' unterscheiden. Also gar nichts anfassen.
    if not (s.radar_repo and s.github_token):
        typer.echo("Kein GITHUB_TOKEN oder RADAR_REPO. Sync uebersprungen.")
        return

    remote = github.liste_bewertungen(s.radar_repo, s.github_token)
    heute = date.today().isoformat()
    n_neu = n_upd = n_skip = n_gel = 0

    for vid, status in remote.items():
        exists = con.execute("SELECT 1 FROM vorgang WHERE id = ?", (vid,)).fetchone()
        if not exists:
            n_skip += 1
            continue
        alt = con.execute(
            "SELECT status FROM bewertung_user WHERE vorgang_id = ?", (vid,)
        ).fetchone()
        if alt is None:
            n_neu += 1
        elif alt["status"] != status:
            n_upd += 1
        else:
            continue
        # UPSERT statt REPLACE: begruendung bleibt erhalten, wenn Zeile schon existiert.
        con.execute(
            "INSERT INTO bewertung_user (vorgang_id, status, begruendung, ts) "
            "VALUES (?, ?, '', ?) "
            "ON CONFLICT(vorgang_id) DO UPDATE SET "
            "status=excluded.status, ts=excluded.ts",
            (vid, status, heute),
        )

    # Lokale Bewertungen loeschen, deren Issue auf GitHub geschlossen wurde
    # (Dashboard-Klick auf aktiven Button = Bewertung entfernen).
    lokal = {r["vorgang_id"] for r in con.execute("SELECT vorgang_id FROM bewertung_user")}
    zu_loeschen = lokal - set(remote.keys())
    for vid in zu_loeschen:
        con.execute("DELETE FROM bewertung_user WHERE vorgang_id = ?", (vid,))
        n_gel += 1

    con.commit()
    typer.echo(
        f"Sync: {n_neu} neu, {n_upd} aktualisiert, {n_gel} entfernt, "
        f"{n_skip} unbekannte IDs uebersprungen."
    )


# --- Health-Check ------------------------------------------------------------
# Wird taeglich vom health.yml-Workflow ausgefuehrt. Exit-Code != 0
# triggert den Failure-Alert-Step, der eine Mail an ALERT_EMAIL schickt.
# Alle Schwellwerte konservativ gewaehlt: Silent-Fails erkennen, ohne
# bei jedem Wackler zu piepsen.

_MIN_VORGAENGE = 500
_MAX_CRON_ALTER_TAGE = 8
_MAX_BACKUP_ALTER_TAGE = 3
_MAX_SYNC_ALTER_TAGE = 3
_WORKER_URL = "https://legal-radar-watch.sportsbrain-philip.workers.dev/"


def _alter_tage(iso: str) -> float:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 86400


def _check_db(con) -> tuple[bool, str]:
    n = con.execute("SELECT COUNT(*) FROM vorgang").fetchone()[0]
    if n < _MIN_VORGAENGE:
        return False, f"Nur {n} Vorgaenge (Schwelle {_MIN_VORGAENGE})"
    return True, f"{n} Vorgaenge"


def _check_cron_aktuell(rejected_pfad: Path) -> tuple[bool, str]:
    if not rejected_pfad.exists():
        return False, "rejected.jsonl fehlt - Cron nie gelaufen?"
    juengster: str | None = None
    for line in rejected_pfad.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("event") == "run_start" and (juengster is None or entry["ts"] > juengster):
            juengster = entry["ts"]
    if juengster is None:
        return False, "kein run_start-Eintrag in rejected.jsonl"
    alter = _alter_tage(juengster)
    if alter > _MAX_CRON_ALTER_TAGE:
        return False, f"letzter Cron vor {alter:.1f} Tagen (max {_MAX_CRON_ALTER_TAGE})"
    return True, f"letzter Cron vor {alter:.1f} Tagen"


def _check_backup_aktuell() -> tuple[bool, str]:
    if not os.getenv("GITHUB_TOKEN"):
        return True, "GITHUB_TOKEN fehlt, Check uebersprungen"
    try:
        r = subprocess.run(
            [
                "gh",
                "release",
                "list",
                "--limit",
                "20",
                "--json",
                "tagName,createdAt",
                "--jq",
                '[.[] | select(.tagName | startswith("backup-"))] | max_by(.createdAt)',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(r.stdout or "null")
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return False, f"gh release list fehlgeschlagen: {e}"
    if not data:
        return False, "kein backup-Release gefunden"
    alter = _alter_tage(data["createdAt"])
    if alter > _MAX_BACKUP_ALTER_TAGE:
        return False, f"letztes Backup vor {alter:.1f} Tagen (max {_MAX_BACKUP_ALTER_TAGE})"
    return True, f"letztes Backup vor {alter:.1f} Tagen ({data['tagName']})"


def _check_worker() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(_WORKER_URL, headers={"User-Agent": "radar-health"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return False, f"Worker HTTP {resp.status}"
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        return False, f"Worker unerreichbar: {e}"
    if not body.get("ok"):
        return False, f"Worker antwortet ohne ok=true: {body}"
    return True, "Worker OK"


def _check_bewertungs_sync(con) -> tuple[bool, str]:
    row = con.execute("SELECT MAX(ts) AS max_ts, COUNT(*) AS n FROM bewertung_user").fetchone()
    if not row or row["n"] == 0:
        return True, "keine Bewertungen, Check uebersprungen"
    max_ts = row["max_ts"]
    if not max_ts:
        return True, "MAX(ts) leer, Check uebersprungen"
    alter = _alter_tage(max_ts)
    if alter > _MAX_SYNC_ALTER_TAGE:
        return False, f"juengste Bewertung vor {alter:.1f} Tagen (max {_MAX_SYNC_ALTER_TAGE})"
    return True, f"juengste Bewertung vor {alter:.1f} Tagen"


@app.command()
def health(as_json: bool = typer.Option(False, "--json", help="JSON-Report ausgeben")) -> None:
    """Prueft DB, Cron-Aktualitaet, Backup, Worker, Bewertungs-Sync. Exit 1 bei rot."""
    s = Settings.load()
    con = db.connect(s.db_path)
    db.migrate(con)

    checks: dict[str, tuple[bool, str]] = {
        "db": _check_db(con),
        "cron_aktuell": _check_cron_aktuell(Path("data/rejected.jsonl")),
        "backup_aktuell": _check_backup_aktuell(),
        "worker": _check_worker(),
        "bewertungs_sync": _check_bewertungs_sync(con),
    }

    alle_gruen = all(ok for ok, _ in checks.values())

    if as_json:
        report = {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()}
        report["all_green"] = alle_gruen
        typer.echo(json.dumps(report, indent=2))
    else:
        for name, (ok, detail) in checks.items():
            marker = "OK  " if ok else "FAIL"
            typer.echo(f"[{marker}] {name}: {detail}")
        typer.echo("---")
        typer.echo("health: all green" if alle_gruen else "health: DEGRADED")

    if not alle_gruen:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
