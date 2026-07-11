"""Nearest Neighbor auf den kuratierten Faellen aus data/cases.yaml.

Negativbeispiele sind die wertvollen. Positive bestaetigen nur, was das
Modell ohnehin tun will: in jedem Gesetz eine Chance sehen.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

FEATURES = ("log_aufwand", "log_betroffene", "monate_bis_frist", "hat_sanktion", "zweiseitig")


def load_cases(path: Path = Path("data/cases.yaml")) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _vec(c: dict) -> list[float]:
    return [float(c.get(f, 0) or 0) for f in FEATURES]


def nearest(kandidat: dict, cases: list[dict], k: int = 3) -> list[dict]:
    v = _vec(kandidat)
    ranked = sorted(cases, key=lambda c: math.dist(v, _vec(c)))
    return ranked[:k]
