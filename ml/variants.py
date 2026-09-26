"""Scoring candidates and their development-calibrated comparison (docs/RESEARCH.md §4).

No model load. Every scorer fits a per-speaker template from five enrollment
embeddings and reports a held-out spread (ADR 3), so a personal threshold
`max(floor, spread - margin)` exists for each. Scorers that change the score
scale have no cosine floor. Margins are chosen on development speakers only,
so evaluation speakers never tune anything (ADR 6).
"""
import numpy as np

from issuer.config import GLOBAL_FLOOR, THRESHOLD_MARGIN, TOP_K_SAMPLES, VARIANT_FRR_BUDGET
from issuer.verification import centroid, spread
from ml.evaluate import error_rates, roc_eer


def unit(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


class Centroid:
    """The live scorer: cosine to the centroid."""
    name, floor = "centroid", GLOBAL_FLOOR

    def fit(self, enrollment, cohort):
        return {"center": centroid(enrollment), "spread": spread(enrollment)}

    def score(self, template, v):
        return float(v @ template["center"])


class TopK:
    """Mean of the best TOP_K_SAMPLES cosines to individual enrollment takes."""
    name, floor = f"top{TOP_K_SAMPLES}", GLOBAL_FLOOR

    @staticmethod
    def _score(enrollment, v):
        return float(np.sort(enrollment @ v)[-TOP_K_SAMPLES:].mean())

    def fit(self, enrollment, cohort):
        held_out = [self._score(np.delete(enrollment, i, axis=0), enrollment[i]) for i in range(len(enrollment))]
        return {"enrollment": enrollment, "spread": float(np.mean(held_out))}

    def score(self, template, v):
        return self._score(template["enrollment"], v)


class ASNorm:
    """Adaptive symmetric normalization against the top-k most similar cohort takes."""
    floor = None

    def __init__(self, k):
        self.k, self.name = k, f"asnorm{k}"

    def _stats(self, cohort, x):
        top = np.sort(cohort @ x)[-self.k:]
        return float(top.mean()), max(float(top.std()), 1e-6)

    def _norm(self, raw, side_a, side_b):
        return 0.5 * ((raw - side_a[0]) / side_a[1] + (raw - side_b[0]) / side_b[1])

    def fit(self, enrollment, cohort):
        if len(cohort) < self.k:
            raise ValueError(f"cohort of {len(cohort)} is smaller than k={self.k}")
        held_out = []
        for i in range(len(enrollment)):
            center = centroid(np.delete(enrollment, i, axis=0))
            held_out.append(self._norm(float(enrollment[i] @ center), self._stats(cohort, center),
                                       self._stats(cohort, enrollment[i])))
        center = centroid(enrollment)
        return {"center": center, "cohort": cohort, "side": self._stats(cohort, center),
                "spread": float(np.mean(held_out))}

    def score(self, template, v):
        return self._norm(float(v @ template["center"]), template["side"], self._stats(template["cohort"], v))


class MeanSub:
    """Subtract the in-domain (cohort) mean embedding, renormalize, then score with `inner`."""
    floor = None

    def __init__(self, inner):
        self.inner, self.name = inner, f"meansub+{inner.name}"

    def fit(self, enrollment, cohort):
        mean = cohort.mean(axis=0)
        template = self.inner.fit(unit(enrollment - mean), unit(cohort - mean))
        return {**template, "mean": mean}

    def score(self, template, v):
        return self.inner.score(template, unit(v - template["mean"]))


def collect(scorer, vectors, selections, speakers, groups, cohort_for):
    """Scores for every claim among `speakers`; impostors are the other listed speakers only."""
    rows = []
    for speaker in speakers:
        enrollment, probes, _ = selections[speaker]
        template = scorer.fit(np.stack([vectors[n] for n in enrollment]), cohort_for(speaker))
        impostors = [vectors[n] for other in speakers if other != speaker for n in selections[other][1]]
        rows.append({"speaker": speaker, "group": groups[speaker], "spread": template["spread"],
                     "genuine": np.array([scorer.score(template, vectors[n]) for n in probes]),
                     "impostor": np.array([scorer.score(template, v) for v in impostors])})
    return rows


def _margins(rows, margin, floor):
    genuine, impostor = [], []
    for r in rows:
        threshold = r["spread"] - margin
        if floor is not None:
            threshold = max(floor, threshold)
        genuine.append(r["genuine"] - threshold)
        impostor.append(r["impostor"] - threshold)
    return np.concatenate(genuine), np.concatenate(impostor)


def rates(rows, margin, floor, group=None):
    chosen = [r for r in rows if group in (None, r["group"])]
    genuine, impostor = _margins(chosen, margin, floor)
    far, frr = error_rates(genuine, impostor)
    return {"far": far, "frr": frr, "eer": roc_eer(genuine, impostor)["eer"], "speakers": len(chosen),
            "genuine_trials": int(genuine.size), "impostor_trials": int(impostor.size)}


def match_margin(rows, floor, target_frr):
    """Smallest (strictest) margin whose pooled FRR is at or below target_frr.

    FRR can only fall as the margin grows, so bisection is exact up to
    float resolution. If even the loosest margin misses the target (a floor
    can bind), the loosest is returned and the report shows the miss.
    """
    lo, hi = -100.0, 100.0
    if rates(rows, hi, floor)["frr"] > target_frr:
        return hi
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if rates(rows, mid, floor)["frr"] <= target_frr else (mid, hi)
    return hi


def compare(scorers, embeddings, selections, groups, development, evaluation):
    """Every (embedding, scorer) pair, calibrated on development, scored once on evaluation.

    embeddings: {name: {clip name: unit vector}}; "plain" must be the live one.
    The reference is plain + centroid under the same calibration, so every
    row is judged by the same procedure. The candidate is chosen by lowest
    development EER; evaluation numbers never choose anything.
    """
    def cohort_of(vectors, speakers):
        return np.stack([vectors[n] for s in speakers for n in selections[s][0] + selections[s][1]])

    live_dev = collect(Centroid(), embeddings["plain"], selections, development, groups,
                       lambda s: cohort_of(embeddings["plain"], [d for d in development if d != s]))
    target = rates(live_dev, THRESHOLD_MARGIN, GLOBAL_FLOOR)["frr"]
    live_eval = collect(Centroid(), embeddings["plain"], selections, evaluation, groups,
                        lambda s: cohort_of(embeddings["plain"], development))
    live = {g: rates(live_eval, THRESHOLD_MARGIN, GLOBAL_FLOOR, g) for g in ("control", "dysarthric")}

    rows = []
    for name, vectors in embeddings.items():
        dev_cohorts = {s: cohort_of(vectors, [d for d in development if d != s]) for s in development}
        eval_cohort = cohort_of(vectors, development)
        for scorer in scorers:
            dev = collect(scorer, vectors, selections, development, groups, dev_cohorts.__getitem__)
            margin = match_margin(dev, scorer.floor, target)
            ev = collect(scorer, vectors, selections, evaluation, groups, lambda s: eval_cohort)
            rows.append({"embedding": name, "scorer": scorer.name, "margin": margin,
                         "development": rates(dev, margin, scorer.floor),
                         "evaluation": {g: rates(ev, margin, scorer.floor, g) for g in ("control", "dysarthric")}})

    reference = next(r for r in rows if r["embedding"] == "plain" and r["scorer"] == "centroid")
    candidates = [r for r in rows if r is not reference]
    chosen = min(candidates, key=lambda r: (r["development"]["eer"], r["development"]["far"]))
    ref_eval, new_eval = reference["evaluation"], chosen["evaluation"]
    checks = {
        "lower_far_control": new_eval["control"]["far"] < ref_eval["control"]["far"],
        "lower_far_dysarthric": new_eval["dysarthric"]["far"] < ref_eval["dysarthric"]["far"],
        "dysarthric_frr_within_budget":
            new_eval["dysarthric"]["frr"] <= ref_eval["dysarthric"]["frr"] + VARIANT_FRR_BUDGET,
    }
    return {"target_development_frr": target, "live": live, "reference": reference, "chosen": chosen,
            "adopt": all(checks.values()), "checks": checks, "rows": rows}
