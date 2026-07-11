from datetime import date, timedelta

from legal_radar.score.deterministic import durchsetzung, score, zeitfenster


def test_fenster_zu_frueh_und_zu_spaet():
    heute = date(2026, 1, 1)
    assert zeitfenster(heute + timedelta(days=90), heute) == 0.0  # < 6 Monate
    assert zeitfenster(heute + timedelta(days=1200), heute) == 0.2  # > 36 Monate
    assert zeitfenster(heute + timedelta(days=550), heute) == 1.0  # Sweet Spot


def test_ohne_durchsetzung_kein_score():
    assert durchsetzung(None, None, False) == 0.0


def test_ko_kriterium_zieht_produkt_auf_null():
    """Hoher Aufwand darf fehlende Durchsetzung nicht kompensieren."""
    s = score(
        erf_aufwand_eur=900_000_000,
        betroffene=50_000,
        anwendungsbeginn=date.today() + timedelta(days=550),
        muster="compliance",
        bussgeld_eur=None,
        behoerde=None,
        behoerde_neu=False,
        zulassung_noetig=False,
    )
    assert s == 0.0


def test_vermittlung_schlechter_als_compliance():
    kw = dict(
        erf_aufwand_eur=300_000_000,
        betroffene=12_000,
        anwendungsbeginn=date.today() + timedelta(days=550),
        bussgeld_eur=500_000,
        behoerde="Bundesamt fuer X",
        behoerde_neu=False,
        zulassung_noetig=False,
    )
    assert score(muster="vermittlung", **kw) < score(muster="compliance", **kw)
