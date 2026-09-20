import pytest

from agents.stylist.colour import (
    ALL_FAMILIES,
    HUES,
    NEUTRALS,
    SINGLE_WORD_ALIASES,
    analogous,
    complementary,
    family_of,
    pairing_rules,
    skin_adjustment,
    skin_tone_rules,
)


def test_wheel_has_twelve_hues_and_a_fixed_neutral_set():
    assert len(HUES) == 12
    assert len(set(HUES)) == 12
    assert NEUTRALS == ["white", "black", "grey", "beige", "denim", "navy"]


def test_complementary_is_an_involution():
    for h in HUES:
        assert complementary(complementary(h)) == h


def test_analogous_never_contains_self():
    for h in HUES:
        assert h not in analogous(h)


def test_every_alias_resolves_to_a_real_family():
    for word, fam in SINGLE_WORD_ALIASES.items():
        assert fam in ALL_FAMILIES, word
        assert family_of(word) == fam


def test_unknown_word_resolves_to_none():
    assert family_of("aubergine") is None
    assert family_of(None) is None
    assert family_of("") is None


def test_mustard_yellow_is_complementary_to_indigo():
    r = pairing_rules("mustard yellow")
    assert r["known"] and r["family"] == "yellow-orange"
    top = r["pairs"][0]
    assert top["family"] == "blue-violet" and top["reason"] == "complementary"


def test_unknown_colour_yields_only_neutrals():
    r = pairing_rules("aubergine")
    assert not r["known"]
    families = {p["family"] for p in r["pairs"]}
    assert families == set(NEUTRALS)
    assert all(p["reason"] == "neutral anchor" for p in r["pairs"])


def test_office_occasion_favours_neutral_over_complementary():
    r = pairing_rules("mustard yellow", occasion="office")
    by_reason = {p["reason"]: p["score"] for p in r["pairs"]}
    assert by_reason["neutral anchor"] > by_reason["complementary"]


@pytest.mark.parametrize("colour", ["mustard", "navy", "teal", "black", "white", None])
def test_scores_are_in_bounds_and_sorted(colour):
    r = pairing_rules(colour)
    scores = [p["score"] for p in r["pairs"]]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_skin_tone_rules_disjoint_and_metals():
    warm = skin_tone_rules("warm", "medium")
    cool = skin_tone_rules("cool", "medium")
    assert set(warm.favour).isdisjoint(cool.favour) is False or set(warm.favour) == set(cool.soften)
    assert warm.metal == "gold" and cool.metal == "silver"


def test_skin_adjustment_capped_and_face_only():
    warm = skin_tone_rules("warm", "medium")
    up, note = skin_adjustment("yellow-orange", "top", warm)
    assert up == pytest.approx(0.10) and "warm" in note
    down, note2 = skin_adjustment("blue-violet", "top", warm)
    assert down == pytest.approx(-0.10)
    zero, note3 = skin_adjustment("blue-violet", "footwear", warm)
    assert zero == 0.0 and note3 is None
    gold_up, _ = skin_adjustment(None, "accessory", warm, metal="gold", garment_type="earrings")
    assert gold_up == pytest.approx(0.10)
    silver_down, _ = skin_adjustment(None, "accessory", warm, metal="silver", garment_type="earrings")
    assert silver_down < 0
    no_face, _ = skin_adjustment(None, "accessory", warm, metal="gold", garment_type="watch")
    assert no_face == 0.0
