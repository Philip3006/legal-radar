"""EUR-Lex / CELLAR SPARQL. Kein Auth, aber 60s Timeout und IP-Throttling.

Immer LIMIT/OFFSET, CELEX->URI lokal cachen.
TODO(claude): Query auf Verordnungen/Richtlinien mit Anwendungsbeginn im Fenster.
"""

from __future__ import annotations

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"


class Cellar:
    name = "cellar"

    def fetch(self, since: str) -> list:
        raise NotImplementedError("Stub — siehe CLAUDE.md, Reihenfolge: erst DIP.")
