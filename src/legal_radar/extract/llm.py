"""LLM-Extraktion. Nur bei geaendertem input_hash. temperature=0. Striktes JSON.

Verboten: URLs erzeugen, Zahlen schaetzen, Kosten in Euro raten.
Erlaubt: Muster-Zuordnung, Pflichten strukturieren, kurze Begruendung.
"""

from __future__ import annotations

import json
import logging

MUSTER_ERLAUBT = {"compliance", "nachweis", "vermittlung", "datenprodukt", "keins"}

log = logging.getLogger(__name__)

SYSTEM = """Du extrahierst Fakten aus deutschen Gesetzestexten. Du erfindest nichts.

Antworte AUSSCHLIESSLICH mit JSON, ohne Markdown, ohne Vorrede.
Fuer "muster" sind AUSSCHLIESSLICH diese fuenf Werte erlaubt und
kein anderer: compliance, nachweis, vermittlung, datenprodukt, keins.
Passt nichts eindeutig: "keins".

{"muster": "compliance|nachweis|vermittlung|datenprodukt|keins",
 "pflichten": [{"typ":"Nachweis|Meldung|Zertifizierung|Register|Beschaffung",
                "gegenstand":"...","frequenz":"einmalig|jaehrlich|laufend"}],
 "anwendungsbeginn": "YYYY-MM-DD oder null",
 "betroffene": "Zahl oder null (Anzahl betroffener Unternehmen)",
 "einmalaufwand_eur": "Zahl oder null (einmaliger Aufwand fuer die Wirtschaft in EUR)",
 "verpflichtete": "...",
 "begruendung": "max. 2 Saetze"}

Steht eine Angabe nicht im Text: null. Niemals schaetzen.
anwendungsbeginn: nur wenn im Text ein konkretes Datum genannt wird
  (Formulierungen wie "tritt am ... in Kraft", "ab dem ...", "gilt ab ...").
Kosten in Euro schaetzt du NIE - die stehen im Vorblatt oder nirgends."""


def parse_strict(raw: str) -> dict | None:
    """Bei Parse-Fehler: Item verwerfen, loggen, nicht raten."""
    try:
        return json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        return None


# Kritische Infos (Erfuellungsaufwand, betroffene, Anwendungsbeginn) stehen im
# Vorblatt = erste ~10k Zeichen. Mehr zu schicken verbrennt nur Tokens.
MAX_TEXT = 15_000


def extract(client, text: str, model: str = "claude-haiku-4-5-20251001") -> dict | None:
    resp = client.messages.create(
        model=model,
        max_tokens=1000,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": text[:MAX_TEXT]}],
    )
    data = parse_strict("".join(b.text for b in resp.content if b.type == "text"))
    if data is not None:
        m = data.get("muster")
        if m not in MUSTER_ERLAUBT:
            log.warning("unbekanntes muster '%s' -> 'keins'", m)
            data["muster"] = "keins"
    return data
