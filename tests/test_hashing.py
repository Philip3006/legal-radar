from datetime import date

from legal_radar.core.hashing import dedupe_key, input_hash
from legal_radar.core.models import Vorgang


def _vorgang(**over) -> Vorgang:
    base = dict(
        id="dip:1",
        quelle="dip",
        titel="Test",
        stadium="bt",
        quelle_url="https://example.invalid/1",
        rohtext="Grundtext",
    )
    base.update(over)
    return Vorgang(**base)


def test_dedupe_key_ist_stabil():
    a = dedupe_key("dip", "12345")
    b = dedupe_key("dip", "12345")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_dedupe_key_ist_verschieden_pro_quelle():
    assert dedupe_key("dip", "1") != dedupe_key("bgbl", "1")


def test_input_hash_aendert_sich_mit_rohtext():
    v1 = _vorgang(rohtext="Version A")
    v2 = _vorgang(rohtext="Version B")
    assert input_hash(v1) != input_hash(v2)


def test_input_hash_aendert_sich_mit_score_input():
    v1 = _vorgang(anwendungsbeginn=date(2027, 1, 1))
    v2 = _vorgang(anwendungsbeginn=date(2028, 1, 1))
    assert input_hash(v1) != input_hash(v2)


def test_input_hash_ignoriert_titel_aenderung():
    v1 = _vorgang(titel="Alter Titel")
    v2 = _vorgang(titel="Neuer Titel")
    assert input_hash(v1) == input_hash(v2)
