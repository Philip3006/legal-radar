"""LLM-Belege gegen Rohtext cross-checken."""

from __future__ import annotations

from legal_radar.extract.verify import verify_eur, verify_int

ROHTEXT = (
    "Vorblatt\nErfuellungsaufwand fuer die Wirtschaft: laufender Aufwand von "
    "23 Mio. Euro pro Jahr, davon 12 Millionen Euro Buerokratiekosten. "
    "Bussgelder bis zu 500.000 Euro sind vorgesehen. "
    "Betroffen sind rund 3.200 Unternehmen."
)


def test_verify_eur_akzeptiert_zitat_mit_passender_zahl():
    beleg = {"wert": 23_000_000, "textspan": "laufender Aufwand von 23 Mio. Euro pro Jahr"}
    assert verify_eur(beleg, ROHTEXT) == 23_000_000


def test_verify_eur_lehnt_erfundene_zahl_ab():
    beleg = {"wert": 99_000_000, "textspan": "laufender Aufwand von 23 Mio. Euro pro Jahr"}
    assert verify_eur(beleg, ROHTEXT) is None


def test_verify_eur_lehnt_span_ausserhalb_ab():
    beleg = {"wert": 40_000_000, "textspan": "Aufwand von 40 Mio. Euro pro Jahr"}
    assert verify_eur(beleg, ROHTEXT) is None


def test_verify_eur_lehnt_span_ohne_einheit_ab():
    beleg = {"wert": 3_200, "textspan": "rund 3.200 Unternehmen"}
    assert verify_eur(beleg, ROHTEXT) is None


def test_verify_int_akzeptiert_betroffene():
    beleg = {"wert": 3_200, "textspan": "rund 3.200 Unternehmen"}
    assert verify_int(beleg, ROHTEXT) == 3_200


def test_verify_int_lehnt_erfundene_zahl_ab():
    beleg = {"wert": 50_000, "textspan": "rund 3.200 Unternehmen"}
    assert verify_int(beleg, ROHTEXT) is None


def test_verify_gibt_none_bei_missing_beleg():
    assert verify_eur(None, ROHTEXT) is None
    assert verify_eur({}, ROHTEXT) is None
    assert verify_int({"wert": 100}, ROHTEXT) is None  # kein textspan
