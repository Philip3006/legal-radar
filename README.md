# legal-radar

Frühwarnsystem für wirtschaftlich relevante Gesetzgebung (Bund + EU).
Kein Ideengenerator — ein Radar mit Historie.

## Nutzung

```bash
uv sync
cp .env.example .env               # DIP_API_KEY + ANTHROPIC_API_KEY eintragen
uv run radar init                  # DB anlegen
uv run radar fetch --source dip --since 2024-01-01
uv run radar score
uv run radar digest --since 7d     # Digest (+ E-Mail wenn SMTP konfiguriert)
uv run radar render-dashboard      # docs/index.html generieren
```

## Ausgabekanäle

- **Digest per E-Mail**: `SMTP_URL` als ENV setzen, Empfänger in `data/config.yaml`
  unter `digest_empfaenger`. Bis zu 5 Empfänger möglich.
- **Statisches HTML-Dashboard** unter `docs/index.html`. GitHub Pages im Repo auf
  Ordner `docs/` (Branch `main`) konfigurieren → Dashboard ist unter
  `https://<user>.github.io/legal-radar/` erreichbar. Der wöchentliche
  GitHub-Actions-Workflow committed die aktualisierte Seite automatisch.

## GitHub Actions

Der Workflow `.github/workflows/radar.yml` läuft wöchentlich (Montag 05:00 UTC).
Nötige Secrets im Repo:

- `DIP_API_KEY` (eigenen Key beantragen: `parlamentsdokumentation@bundestag.de`)
- `ANTHROPIC_API_KEY`
- `SMTP_URL` (optional, für E-Mail-Versand)

Die SQLite-DB wird zwischen Runs via `actions/cache` persistiert.

## macOS / Python 3.13 Hinweis

Bei `ModuleNotFoundError: No module named 'legal_radar'` nach `uv sync`:
Python 3.13 überspringt `.pth`-Dateien mit `UF_HIDDEN`-Flag, das uv auf macOS
setzt. Fix:

```bash
chflags nohidden .venv/lib/python*/site-packages/*.pth
```
