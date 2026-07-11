-- Score-Invalidierung: wenn input_hash != score_hash muss neu bewertet werden.
ALTER TABLE vorgang ADD COLUMN score_hash TEXT;

-- Strukturierte Pflichten aus dem LLM. Wird bei jedem Fetch neu geschrieben.
CREATE TABLE IF NOT EXISTS pflicht (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  vorgang_id  TEXT NOT NULL REFERENCES vorgang(id) ON DELETE CASCADE,
  typ         TEXT NOT NULL,   -- Nachweis|Meldung|Zertifizierung|Register|Beschaffung
  gegenstand  TEXT NOT NULL,
  frequenz    TEXT             -- einmalig|jaehrlich|laufend|NULL
);
CREATE INDEX IF NOT EXISTS idx_pflicht_vorgang ON pflicht(vorgang_id);
