"""input_hash: entscheidet, ob ueberhaupt neu gescort wird."""

from __future__ import annotations

import hashlib

from legal_radar.core.models import Vorgang

# Nur diese Felder duerfen einen Rescore ausloesen. Alles andere ist Rauschen.
SCORE_INPUTS = ("stadium", "anwendungsbeginn", "erf_aufwand_eur", "betroffene")


def dedupe_key(quelle: str, externe_id: str) -> str:
    return hashlib.sha256(f"{quelle}:{externe_id}".encode()).hexdigest()


def input_hash(v: Vorgang) -> str:
    parts = [str(getattr(v, f)) for f in SCORE_INPUTS]
    parts.append(hashlib.sha256(v.rohtext.encode()).hexdigest())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()
