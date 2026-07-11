# legal-radar

Ein **Radar**, kein Ideengenerator. Der Agent bewertet Gesetzgebungsvorgaenge nach
wirtschaftlichem Potenzial und meldet **Aenderungen** ueber Jahre hinweg.
Das Geschaeftsmodell baut der Mensch, nicht dieses Repo.

`sammeln -> extrahieren -> deterministisch scoren -> historisieren -> Ereignis-Digest`

## Module
- `sources/`  — ein Adapter je Quelle, `fetch(cfg) -> list[RawVorgang]`
- `extract/`  — `rules.py` (Regex, deterministisch) vor `llm.py` (nur bei Hash-Aenderung)
- `score/`    — `deterministic.py` traegt die Last, LLM nur fuer Muster-Zuordnung
- `digest/`   — `events.py` erzeugt Ereignisse aus `vorgang_history`, nicht aus Zustaenden
- `core/`     — geteilte Bausteine. Neue Logik gehoert hierhin, nicht in die Module.

## Harte Regeln
- **URLs und Zahlen werden nie vom LLM erzeugt**, immer aus dem Rohdokument durchgereicht.
  Erfindet das Modell eine Zahl: Item verwerfen, loggen, nicht raten.
- **Ein Score wird nur neu berechnet, wenn `input_hash` sich geaendert hat.**
  Sonst rauscht der Digest und niemand liest ihn nach Woche drei.
- LLM-Calls immer `temperature=0`, striktes JSON, Ergebnis unter `input_hash` gecacht.
- `vorgang_history` ist **append-only**. Nie ueberschreiben. Ohne Historie keine Updates.
- Score = **Produkt**, nicht Summe. Ein K.-o.-Kriterium zieht alles auf null.
  Bei einer Summe kompensiert hoher Erfuellungsaufwand die fehlende Zulassung.
- Der Digest zeigt **keinen Score an**. Er sortiert nur intern.
- `status = verworfen` klebt. Rueckkehr nur bei Aenderung von `stadium` oder
  `erf_aufwand_eur` — niemals wegen Score-Drift.
- Optimiere auf **Recall, nicht Precision**. Basisrate ~1 %. 25 Fehlalarme kosten einen
  Abend, ein verpasster Treffer kostet alles. Schwellwert niemals still hochziehen.
- Dedupe-Key: `sha256(quelle + externe_id)`. Ein Vorgang durchlaeuft Stadien —
  nicht neu melden, sondern **Stadienwechsel** melden.
- Jedes verworfene Item loggen (`data/rejected.jsonl`), sonst ist der Prefilter blind.

## Prefilter (vor jedem LLM-Call)
Erfuellungsaufwand Wirtschaft > 10 Mio EUR/Jahr **oder** neue Melde-/Nachweispflicht
im Text. Spart ~95 % der Calls.

## Durchsetzung ist ein Feature, kein Detail
Ohne benannte Behoerde und ohne Bussgeldrahmen gibt es keine Zahlungsbereitschaft.
Eine neu zu schaffende Behoerde heisst: Pflicht auf dem Papier ab 2028, real ab 2031.

## Befehle
    uv sync
    uv run ruff check --fix . && uv run ruff format .
    uv run pytest
    uv run radar fetch --source dip --since 2024-01-01
    uv run radar score --dry-run
    uv run radar digest --since 7d
