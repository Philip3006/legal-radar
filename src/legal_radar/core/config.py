"""Konfiguration aus Umgebung + data/config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class Settings(BaseModel):
    dip_api_key: str = ""
    anthropic_api_key: str = ""
    db_path: Path = Path("data/radar.db")
    prefilter_min_aufwand_eur: int = 10_000_000
    smtp_url: str = ""
    digest_empfaenger: list[str] = []
    digest_absender: str = "radar@legal-radar.local"

    @classmethod
    def load(cls) -> Settings:
        cfg: dict = {}
        cfg_file = Path("data/config.yaml")
        if cfg_file.exists():
            cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        return cls(
            dip_api_key=os.getenv("DIP_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            db_path=Path(os.getenv("RADAR_DB", "data/radar.db")),
            prefilter_min_aufwand_eur=cfg.get("prefilter_min_aufwand_eur", 10_000_000),
            smtp_url=os.getenv("SMTP_URL", ""),
            digest_empfaenger=cfg.get("digest_empfaenger", []) or [],
            digest_absender=cfg.get("digest_absender", "radar@legal-radar.local"),
        )
