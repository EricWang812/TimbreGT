"""Baseline transcription-check logic, on text and abstract trials (no audio)."""
import pytest

from ml.baseline_asr import compare, normalize, passes, scoreable, wer


def test_normalize_matches_how_whisper_writes():
    assert normalize("Apple.") == ["apple"]
    assert normalize("  The 4 ducks, didn't they?") == ["the", "four", "ducks", "didn't", "they"]


def test_wer_counts_substitutions_insertions_deletions():
    assert wer("apple", "Apple.") == 0
    assert wer("apple", "a pull") == 2
    assert wer("the quick brown fox", "the quick fox") == .25
    assert wer("yes", "") == 1
    with pytest.raises(ValueError):
        wer("", "anything")


def test_pass_rule_is_generous_but_rejects_a_wrong_word():
    assert passes("the quick brown fox", "the quick fox")
    assert not passes("leak", "Thank you.")


def test_unscoreable_prompts_are_excluded():
    assert not scoreable("[say Ah-P-Eee repeatedly]")
    assert not scoreable("xxx")
    assert not scoreable("He will allow a rare lilyrare lieDDDDDDDDDCCCCCCCCCCC")
    assert scoreable("Except in the winter")


def trial(kind, group, baseline, timbre, claimed="A"):
    return {"kind": kind, "claimed": claimed, "claimed_group": group,
            "baseline_pass": baseline, "timbre_pass": timbre}


def test_compare_separates_right_person_from_someone_else():
    trials = [trial("genuine", "control", True, True), trial("impostor", "control", True, False),
              trial("genuine", "dysarthric", False, True, "B"), trial("genuine", "dysarthric", False, False, "B"),
              trial("impostor", "dysarthric", True, False, "B")]
    rates = compare(trials)
    assert rates["dysarthric"]["baseline_accepts_genuine"] == 0
    assert rates["dysarthric"]["timbre_accepts_genuine"] == .5
    # The transcription check lets anyone who speaks clearly through.
    assert rates["control"]["baseline_accepts_impostor"] == 1
    assert rates["control"]["timbre_accepts_impostor"] == 0
    assert rates["dysarthric"]["speakers"] == 1


def test_compare_requires_both_trial_kinds():
    with pytest.raises(ValueError):
        compare([trial("genuine", "control", True, True)])
