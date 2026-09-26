"""Offline speaker verification evaluation, with no model load at import.

Speaker-disjoint development/evaluation cohorts; disjoint enrollment/probe
recordings within each identity. This is NOT a live sound-label challenge.
"""
from dataclasses import dataclass
import hashlib
import re

import numpy as np

from issuer.config import COHESION_MIN, RECORDINGS_PER_LABEL
from issuer.verification import centroid, cohesion, in_sample_spread, personal_threshold, spread

NAME_RE = re.compile(r"^([FM]C?\d+)_(\d+)_(headMic|arrayMic)_(\d+)\.wav$", re.I)


@dataclass(frozen=True)
class Clip:
    name: str
    speaker: str
    session: str
    group: str
    vector: np.ndarray


def metadata(path, speech_status=None):
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    match = NAME_RE.fullmatch(name)
    if not match:
        raise ValueError(f"Unrecognized TORGO filename: {name!r}")
    speaker, session, mic, _ = match.groups()
    speaker = speaker.upper()
    parsed = "control" if speaker[1] == "C" else "dysarthric"
    statuses = {"healthy": "control", "control": "control", "dysarthria": "dysarthric", "dysarthric": "dysarthric"}
    if speech_status is None or speech_status == "":
        group = parsed
    else:
        key = str(speech_status).strip().lower()
        if key not in statuses:
            raise ValueError(f"Unknown speech_status {speech_status!r} for {name}")
        group = statuses[key]
        if group != parsed:
            raise ValueError(f"Conflicting speaker/status metadata: {name}, {speech_status}")
    return name, speaker, session, mic.lower(), group


def stable_key(value, seed):
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def split_speakers(groups, seed):
    """Reserve one third (at least one) of each group for future development.

    No threshold is tuned on either cohort by this evaluator.
    """
    development, evaluation = [], []
    for group in ("control", "dysarthric"):
        speakers = sorted((s for s, g in groups.items() if g == group), key=lambda s: stable_key(s, seed))
        if len(speakers) < 3:
            raise ValueError(f"Need at least 3 eligible {group} speakers for a disjoint split")
        cut = max(1, len(speakers) // 3)
        development.extend(speakers[:cut])
        evaluation.extend(speakers[cut:])
    return sorted(development), sorted(evaluation)


def select_trials(clips, seed, max_probes):
    """Prefer enrollment from one session and probes from other sessions.

    A same-session fallback is explicit in the returned protocol. Selection
    depends only on identity/session/name, never embedding scores.
    """
    clips = sorted(clips, key=lambda c: stable_key(c.name, seed))
    if len({c.name for c in clips}) != len(clips):
        raise ValueError("Duplicate clip names would contaminate enrollment/probes")
    if len(clips) < RECORDINGS_PER_LABEL + 1:
        raise ValueError("Not enough usable recordings for enrollment and a probe")
    sessions = sorted({c.session for c in clips}, key=lambda s: stable_key(s, seed))
    for session in sessions:
        enrollment = [c for c in clips if c.session == session]
        probes = [c for c in clips if c.session != session]
        if len(enrollment) >= RECORDINGS_PER_LABEL and probes:
            return enrollment[:RECORDINGS_PER_LABEL], probes[:max_probes], "cross-session"
    return clips[:RECORDINGS_PER_LABEL], clips[RECORDINGS_PER_LABEL:][:max_probes], "same-session fallback"


def error_rates(genuine, impostor, threshold=0.0):
    genuine, impostor = np.asarray(genuine), np.asarray(impostor)
    if not genuine.size or not impostor.size:
        raise ValueError("Both genuine and impostor trials are required")
    if not np.isfinite(genuine).all() or not np.isfinite(impostor).all():
        raise ValueError("Trial scores must be finite")
    return float(np.mean(impostor >= threshold)), float(np.mean(genuine < threshold))


def roc_eer(genuine, impostor):
    """Exact empirical ROC including tied scores; linearly interpolated EER.

    Equality is accepted, matching the live verifier. Interpolated EER is a
    descriptive statistic, not a selected or deployable threshold.
    """
    error_rates(genuine, impostor)
    genuine, impostor = np.sort(genuine), np.sort(impostor)
    values = np.unique(np.concatenate((genuine, impostor)))
    thresholds = np.r_[values, np.nextafter(values[-1], np.inf)]
    far = 1 - np.searchsorted(impostor, thresholds, side="left") / len(impostor)
    frr = np.searchsorted(genuine, thresholds, side="left") / len(genuine)
    delta = far - frr
    right = int(np.flatnonzero(delta <= 0)[0])
    if delta[right] == 0:
        eer = far[right]
    else:
        left = right - 1
        weight = delta[left] / (delta[left] - delta[right])
        eer = far[left] + weight * (far[right] - far[left])
    return {"eer": float(eer), "far": far.tolist(), "frr": frr.tolist()}


def evaluate(clips, seed, max_probes):
    by_speaker = {}
    for clip in clips:
        vector = np.asarray(clip.vector)
        if vector.ndim != 1 or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=1e-4):
            raise ValueError(f"Invalid unit embedding: {clip.name}")
        by_speaker.setdefault(clip.speaker, []).append(clip)
    groups = {}
    excluded = {}
    selections = {}
    for speaker, rows in sorted(by_speaker.items()):
        if len({c.group for c in rows}) != 1:
            raise ValueError(f"Inconsistent group for {speaker}")
        try:
            selections[speaker] = select_trials(rows, seed, max_probes)
        except ValueError as exc:
            if len(rows) >= RECORDINGS_PER_LABEL + 1:
                raise
            excluded[speaker] = str(exc)
            continue
        groups[speaker] = rows[0].group
    development, evaluation = split_speakers(groups, seed)
    results = {variant: {group: {"genuine": [], "impostor": [], "per_speaker": []}
                         for group in ("control", "dysarthric")}
               for variant in ("in_sample", "held_out")}
    protocol = []
    for speaker in evaluation:
        enrollment, probes, mode = selections[speaker]
        embeddings = np.stack([c.vector for c in enrollment])
        center = centroid(embeddings)
        if not np.isfinite(center).all():
            raise ValueError(f"Undefined centroid for {speaker}")
        genuine = [float(c.vector @ center) for c in probes]
        # Group is the claimed identity's group; all other evaluation speakers
        # supply impostors, including the other group. No development probes.
        impostor = [float(c.vector @ center) for other in evaluation if other != speaker
                    for c in selections[other][1]]
        row = {"speaker": speaker, "group": groups[speaker], "protocol": mode,
               "enrollment": [c.name for c in enrollment], "probes": [c.name for c in probes],
               "cohesion": cohesion(embeddings), "low_cohesion": cohesion(embeddings) < COHESION_MIN,
               "thresholds": {}}
        for variant, formula in (("in_sample", in_sample_spread), ("held_out", spread)):
            threshold = personal_threshold(formula(embeddings))
            if not np.isfinite(threshold):
                raise ValueError(f"Undefined threshold for {speaker}")
            row["thresholds"][variant] = threshold
            cell = results[variant][groups[speaker]]
            gm, im = np.array(genuine) - threshold, np.array(impostor) - threshold
            cell["genuine"].extend(gm.tolist())
            cell["impostor"].extend(im.tolist())
            far, frr = error_rates(gm, im)
            cell["per_speaker"].append({"speaker": speaker, "far": far, "frr": frr})
        protocol.append(row)
    for groups_result in results.values():
        for cell in groups_result.values():
            genuine, impostor = cell.pop("genuine"), cell.pop("impostor")
            cell.update(roc_eer(genuine, impostor))
            cell["far_at_operating_point"], cell["frr_at_operating_point"] = error_rates(genuine, impostor)
            cell["genuine_trials"], cell["impostor_trials"] = len(genuine), len(impostor)
            cell["speaker_macro_far"] = float(np.mean([r["far"] for r in cell["per_speaker"]]))
            cell["speaker_macro_frr"] = float(np.mean([r["frr"] for r in cell["per_speaker"]]))
    return {"development_speakers": development, "evaluation_speakers": evaluation,
            "excluded_speakers": excluded, "protocol": protocol, "results": results}
