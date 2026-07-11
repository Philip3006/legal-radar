from legal_radar.extract import rules


def test_erfuellungsaufwand_wird_gefunden():
    t = "E.2 Erfuellungsaufwand fuer die Wirtschaft\nDer jaehrliche Aufwand betraegt 340 Mio. Euro."
    assert rules.erfuellungsaufwand_wirtschaft(t) == 340_000_000


def test_kein_aufwand_gibt_none():
    assert rules.erfuellungsaufwand_wirtschaft("Nichts hier.") is None


def test_prefilter_laesst_meldepflicht_durch():
    assert rules.passes_prefilter("Es besteht eine Meldepflicht.", 10_000_000)
