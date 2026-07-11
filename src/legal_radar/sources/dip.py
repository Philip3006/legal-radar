"""DIP (Bundestag). Der Kern. Volltexte kommen aus /drucksache-text.

Eigenen API-Key beantragen: parlamentsdokumentation@bundestag.de
Der oeffentliche Sammelschluessel rotiert und laeuft regelmaessig ab.
"""

from __future__ import annotations

from legal_radar.core.http import get_json
from legal_radar.core.models import Vorgang

BASE = "https://search.dip.bundestag.de/api/v1"

STADIUM_MAP = {
    "Noch nicht beraten": "bt",
    "Verkündet": "verkuendet",
    "Erledigt durch Ablauf der Wahlperiode": "tot",
    "Zurückgezogen": "tot",
}


class Dip:
    name = "dip"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("DIP_API_KEY fehlt")
        self.key = api_key

    def _get(self, path: str, params: dict) -> dict:
        return get_json(f"{BASE}/{path}", params={**params, "apikey": self.key})

    def fetch(self, since: str) -> list[Vorgang]:
        """Vorgaenge vom Typ Gesetzgebung ab `since` (YYYY-MM-DD)."""
        out: list[Vorgang] = []
        cursor: str | None = None
        while True:
            params = {"f.vorgangstyp": "Gesetzgebung", "f.datum.start": since}
            if cursor:
                params["cursor"] = cursor
            data = self._get("vorgang", params)
            for d in data.get("documents", []):
                out.append(self._to_vorgang(d))
            new_cursor = data.get("cursor")
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor
        return out

    def drucksache_text(self, drucksache_id: str) -> str:
        return self._get(f"drucksache-text/{drucksache_id}", {}).get("text", "")

    def text_fuer_vorgang(self, vorgang_id: str) -> str:
        """Volltext der Hauptdrucksache. Gesetzentwurf wird bevorzugt.

        Weg: /vorgangsposition?f.vorgang=X -> fundstelle.id -> /drucksache-text/id.
        Der Filter f.vorgang.id auf /drucksache wird von der API ignoriert.
        """
        vid = vorgang_id.removeprefix("dip:")
        data = self._get("vorgangsposition", {"f.vorgang": vid})
        docs = data.get("documents", [])
        if not docs:
            return ""

        def fs_typ(d: dict) -> str:
            return ((d.get("fundstelle") or {}).get("drucksachetyp")) or ""

        def fs_id(d: dict) -> str | None:
            fs = d.get("fundstelle") or {}
            return str(fs["id"]) if fs.get("id") else None

        for prio in ("Gesetzentwurf", "Regierungsentwurf", "Beschlussempfehlung"):
            for d in docs:
                if prio in fs_typ(d) and fs_id(d):
                    return self.drucksache_text(fs_id(d))
        for d in docs:
            if fs_id(d):
                return self.drucksache_text(fs_id(d))
        return ""

    def _to_vorgang(self, d: dict) -> Vorgang:
        vid = str(d["id"])
        return Vorgang(
            id=f"dip:{vid}",
            quelle="dip",
            titel=d.get("titel", ""),
            stadium=STADIUM_MAP.get(d.get("beratungsstand", ""), "bt"),
            # URL wird durchgereicht, niemals konstruiert oder generiert.
            quelle_url=f"https://dip.bundestag.de/vorgang/-/{vid}",
        )
