from __future__ import annotations

from typing import Protocol

from legal_radar.core.models import Vorgang


class Source(Protocol):
    name: str

    def fetch(self, since: str) -> list[Vorgang]: ...
