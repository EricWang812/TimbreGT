"""Protocol and metric checks using abstract unit vectors, never simulated speech."""
import numpy as np
import pytest

from ml.evaluate import Clip, error_rates, evaluate, metadata, roc_eer, select_trials, split_speakers


def test_metadata_prefers_status_but_refuses_conflicts():
    assert metadata(r"C:\data\FC01_1_headMic_0001.wav", "healthy") == ("FC01_1_headMic_0001.wav", "FC01", "1", "headmic", "control")
    assert metadata("M01_2_arrayMic_0001.wav")[4] == "dysarthric"
    with pytest.raises(ValueError, match="Conflicting"):
        metadata("M01_2_headMic_0001.wav", "healthy")
    with pytest.raises(ValueError, match="Unknown"):
        metadata("M01_2_headMic_0001.wav", "unknown")
    with pytest.raises(ValueError, match="Unrecognized"):
        metadata("unidentified.wav")


def test_rates_accept_threshold_equality_and_handle_ties():
    assert error_rates([0, 1], [-1, 0]) == (.5, 0)
    assert roc_eer([.8, .9], [.1, .2])["eer"] == 0
    assert roc_eer([.5, .5], [.5, .5])["eer"] == .5
    assert roc_eer([.1, .2], [.8, .9])["eer"] == 1
    with pytest.raises(ValueError):
        roc_eer([], [1])
    with pytest.raises(ValueError):
        roc_eer([np.nan], [1])


def corpus():
    speakers = ["FC01", "FC02", "FC03", "MC01", "F01", "F02", "M01", "M02"]
    clips = []
    for i, speaker in enumerate(speakers):
        vector = np.eye(len(speakers))[i]
        group = "control" if speaker[1] == "C" else "dysarthric"
        for session in ("1", "2"):
            for take in range(7):
                clips.append(Clip(f"{speaker}_{session}_headMic_{take:04}.wav", speaker, session, group, vector))
    return clips


def test_selection_is_disjoint_reproducible_and_cross_session():
    clips = [c for c in corpus() if c.speaker == "FC01"]
    enrollment, probes, mode = select_trials(clips, 7, 4)
    assert len(enrollment) == 5 and len(probes) == 4
    assert mode == "cross-session"
    assert {c.session for c in enrollment}.isdisjoint(c.session for c in probes)
    again = select_trials(list(reversed(clips)), 7, 4)
    assert [c.name for c in enrollment + probes] == [c.name for c in again[0] + again[1]]
    with pytest.raises(ValueError, match="Duplicate"):
        select_trials(clips + [clips[0]], 7, 4)
    enrollment, probes, mode = select_trials(clips[:7], 7, 4)
    assert mode == "same-session fallback"
    assert len(probes) == 2
    assert {c.name for c in enrollment}.isdisjoint(c.name for c in probes)


def test_cohorts_and_evaluation_never_leak_development_speakers():
    result = evaluate(corpus(), 7, 4)
    assert set(result["development_speakers"]).isdisjoint(result["evaluation_speakers"])
    assert len(result["development_speakers"]) == 2
    assert {r["speaker"] for r in result["protocol"]} == set(result["evaluation_speakers"])
    for variants in result["results"].values():
        for cell in variants.values():
            assert cell["eer"] == cell["far_at_operating_point"] == cell["frr_at_operating_point"] == 0
            assert cell["genuine_trials"] == 12
            assert cell["impostor_trials"] == 60
    with pytest.raises(ValueError, match="at least 3"):
        split_speakers({"FC01": "control", "M01": "dysarthric"}, 7)


def test_held_out_spread_reduces_threshold_without_changing_trial_counts():
    rng = np.random.default_rng(10)
    noisy = []
    for c in corpus():
        vector = c.vector + rng.normal(0, .15, len(c.vector))
        vector /= np.linalg.norm(vector)
        noisy.append(Clip(c.name, c.speaker, c.session, c.group, vector))
    result = evaluate(noisy, 7, 4)
    assert all(r["thresholds"]["held_out"] <= r["thresholds"]["in_sample"] for r in result["protocol"])
    for group in ("control", "dysarthric"):
        held, original = (result["results"][v][group] for v in ("held_out", "in_sample"))
        assert held["genuine_trials"] == original["genuine_trials"]
        assert held["impostor_trials"] == original["impostor_trials"]
        assert held["frr_at_operating_point"] <= original["frr_at_operating_point"]
        assert held["far_at_operating_point"] >= original["far_at_operating_point"]
