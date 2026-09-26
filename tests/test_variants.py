"""Accuracy candidates (docs/RESEARCH.md): preprocessing on synthetic tones and
scorers on abstract unit vectors. No speech, no model."""
import numpy as np
import pytest

from issuer.config import CROP_S, EMBEDDING_DIM, GLOBAL_FLOOR, SAMPLE_RATE
from ml.preprocess import crops, trim_silence
from ml.variants import ASNorm, Centroid, MeanSub, TopK, collect, compare, match_margin, rates, unit


def tone(seconds, amp=0.3, freq=220.0):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(seconds):
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def test_trim_removes_long_silence_but_keeps_the_sound():
    take = np.concatenate([silence(1.0), tone(1.0), silence(0.8), tone(0.6), silence(1.0)])
    trimmed = trim_silence(take)
    assert 1.6 * SAMPLE_RATE <= trimmed.size <= 2.2 * SAMPLE_RATE   # both sounds plus a little context
    assert np.abs(trimmed).max() == pytest.approx(0.3, abs=1e-3)


def test_trim_keeps_short_gaps_and_never_returns_a_fragment():
    gap = np.concatenate([tone(0.5), silence(0.1), tone(0.5)])
    assert trim_silence(gap).size == gap.size                        # a 100 ms gap is part of the sound
    blip = np.concatenate([silence(2.0), tone(0.1), silence(2.0)])
    assert trim_silence(blip).size == blip.size                      # too little would remain
    assert trim_silence(silence(2.0)).size == silence(2.0).size


def test_crops_cover_the_take_and_end_flush():
    take = tone(3.2)
    pieces = crops(take)
    assert all(p.size == int(CROP_S * SAMPLE_RATE) for p in pieces)
    assert np.array_equal(pieces[-1], take[-int(CROP_S * SAMPLE_RATE):])
    assert len(crops(tone(1.0))) == 1


def rand_unit(rng, n=1):
    return unit(rng.normal(size=(n, EMBEDDING_DIM))).astype(np.float32)


def speaker(rng, n=45, noise=1.6):
    """Takes clustered around one random voice (cosine to centre about 0.5)."""
    center = rand_unit(rng)[0]
    return unit(center + noise * rng.normal(size=(n, EMBEDDING_DIM)) / np.sqrt(EMBEDDING_DIM)).astype(np.float32)


@pytest.mark.parametrize("scorer", [Centroid(), TopK(), ASNorm(10), MeanSub(Centroid()), MeanSub(ASNorm(10))])
def test_every_scorer_ranks_own_takes_above_others(scorer):
    rng = np.random.default_rng(0)
    own, other, cohort = speaker(rng), speaker(rng), np.concatenate([speaker(rng) for _ in range(3)])
    template = scorer.fit(own[:5], cohort)
    genuine = [scorer.score(template, v) for v in own[5:]]
    impostor = [scorer.score(template, v) for v in other]
    assert np.median(genuine) > np.max(impostor)
    assert np.isfinite(template["spread"])


def test_asnorm_refuses_a_cohort_smaller_than_k():
    rng = np.random.default_rng(1)
    with pytest.raises(ValueError):
        ASNorm(60).fit(speaker(rng)[:5], speaker(rng, n=20))


def _world(rng, n_dev=4, n_eval=6):
    vectors, selections, groups = {}, {}, {}
    for i in range(n_dev + n_eval):
        sid = f"S{i}"
        names = [f"{sid}_{j}" for j in range(45)]
        vectors.update(zip(names, speaker(rng)))
        selections[sid] = (names[:5], names[5:], "cross-session")
        groups[sid] = "control" if i % 2 else "dysarthric"
    ordered = [f"S{i}" for i in range(n_dev + n_eval)]
    return vectors, selections, groups, ordered[:n_dev], ordered[n_dev:]


def test_margin_matching_hits_the_target_and_is_the_strictest():
    rng = np.random.default_rng(2)
    vectors, selections, groups, dev, _ = _world(rng)
    rows = collect(Centroid(), vectors, selections, dev, groups, lambda s: None)
    margin = match_margin(rows, None, 0.2)
    assert rates(rows, margin, None)["frr"] <= 0.2
    assert rates(rows, margin - 1e-3, None)["frr"] > 0.2


def test_margin_matching_reports_a_binding_floor_instead_of_hiding_it():
    rng = np.random.default_rng(2)
    vectors, selections, groups, dev, _ = _world(rng)
    rows = collect(Centroid(), vectors, selections, dev, groups, lambda s: None)
    # Synthetic cosines sit near 0.5, so a 0.45 floor keeps FRR above 20% at any margin.
    margin = match_margin(rows, GLOBAL_FLOOR, 0.2)
    assert margin == 100.0 and rates(rows, margin, GLOBAL_FLOOR)["frr"] > 0.2


def test_compare_never_puts_an_evaluation_recording_in_a_cohort():
    rng = np.random.default_rng(3)
    vectors, selections, groups, dev, ev = _world(rng)
    cohorts = []

    class Spy(Centroid):
        name = "spy"

        def fit(self, enrollment, cohort):
            cohorts.append(cohort)
            return super().fit(enrollment, cohort)

    compare([Centroid(), Spy()], {"plain": vectors}, selections, groups, dev, ev)
    evaluation = np.stack([vectors[n] for s in ev for n in selections[s][0] + selections[s][1]])
    assert cohorts and all((c @ evaluation.T).max() < 1 - 1e-4 for c in cohorts)


def test_development_claims_exclude_the_claimant_from_its_cohort():
    rng = np.random.default_rng(5)
    vectors, selections, groups, dev, ev = _world(rng)
    claims = []

    class Spy(Centroid):
        name = "spy"

        def fit(self, enrollment, cohort):
            claims.append((enrollment, cohort))
            return super().fit(enrollment, cohort)

    compare([Centroid(), Spy()], {"plain": vectors}, selections, groups, dev, ev)
    dev_claims = claims[:len(dev)]
    assert all((cohort @ enrollment.T).max() < 1 - 1e-4 for enrollment, cohort in dev_claims)


def test_compare_reference_and_decision_shape():
    rng = np.random.default_rng(4)
    vectors, selections, groups, dev, ev = _world(rng)
    result = compare([Centroid(), TopK()], {"plain": vectors}, selections, groups, dev, ev)
    assert result["reference"]["scorer"] == "centroid" and result["chosen"]["scorer"] == "top2"
    assert result["reference"]["development"]["frr"] <= result["target_development_frr"]
    assert set(result["checks"]) == {"lower_far_control", "lower_far_dysarthric", "dysarthric_frr_within_budget"}
