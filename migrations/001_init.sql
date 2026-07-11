CREATE TABLE IF NOT EXISTS vorgang (
  id                TEXT PRIMARY KEY,   -- "dip:12345" | "celex:32024R1234"
  quelle            TEXT NOT NULL,
  titel             TEXT NOT NULL,
  stadium           TEXT NOT NULL,      -- referentenentwurf|kabinett|bt|ausschuss|verkuendet|anwendbar|tot
  anwendungsbeginn  DATE,
  erf_aufwand_eur   INTEGER,            -- jaehrlich, Wirtschaft
  einmalaufwand_eur INTEGER,
  betroffene        INTEGER,
  bussgeld_eur      INTEGER,
  behoerde          TEXT,
  behoerde_neu      INTEGER DEFAULT 0,
  zulassung_noetig  INTEGER DEFAULT 0,
  muster            TEXT,               -- compliance|nachweis|vermittlung|datenprodukt|keins
  score             REAL,
  input_hash        TEXT NOT NULL,
  quelle_url        TEXT NOT NULL,
  erstgesehen       DATE NOT NULL,
  zuletzt_geprueft  DATE NOT NULL
);

-- append-only. Ohne Historie keine Updates, nur Zustaende.
CREATE TABLE IF NOT EXISTS vorgang_history (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  vorgang_id TEXT NOT NULL REFERENCES vorgang(id),
  ts         DATE NOT NULL,
  feld       TEXT NOT NULL,
  alt        TEXT,
  neu        TEXT
);
CREATE INDEX IF NOT EXISTS idx_hist_vorgang ON vorgang_history(vorgang_id, ts);

-- der einzige Feedback-Kanal des Systems
CREATE TABLE IF NOT EXISTS bewertung_user (
  vorgang_id  TEXT PRIMARY KEY REFERENCES vorgang(id),
  status      TEXT NOT NULL CHECK (status IN ('interessant','beobachten','verworfen')),
  begruendung TEXT,
  ts          DATE NOT NULL
);

-- LLM-Cache, Schluessel ist der input_hash
CREATE TABLE IF NOT EXISTS llm_cache (
  input_hash TEXT PRIMARY KEY,
  payload    TEXT NOT NULL,
  ts         DATE NOT NULL
);
