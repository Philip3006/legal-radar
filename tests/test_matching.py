"""Titel-Normalisierung fuer BGBl<->DIP-Matching."""

from __future__ import annotations

from legal_radar.core.matching import titel_normalize


def test_entwurf_praefix_wird_gestrippt():
    dip = "Entwurf eines Gesetzes zur Regelung von XYZ"
    bgbl = "Gesetzes zur Regelung von XYZ"
    assert titel_normalize(dip) == titel_normalize(bgbl)


def test_gesetzes_und_gesetz_matchen():
    a = "Gesetzes zur Foerderung von Reparaturen"
    b = "Gesetz zur Foerderung von Reparaturen"
    assert titel_normalize(a) == titel_normalize(b)


def test_verschiedene_titel_matchen_nicht():
    a = "Entwurf eines Gesetzes zur Regelung von X"
    b = "Gesetz zur Regelung von Y"
    assert titel_normalize(a) != titel_normalize(b)


def test_case_und_whitespace_egal():
    a = "  Entwurf  Eines Gesetzes  zur X  "
    b = "gesetz zur x"
    assert titel_normalize(a) == titel_normalize(b)


def test_kein_entwurf_praefix_bleibt_stabil():
    assert titel_normalize("Verordnung ueber X") == "verordnung ueber x"
