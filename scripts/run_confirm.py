"""Pre-registered confirmation of ECAPA + ResNet34 fusion on EasyCall.

Implements docs/PREREGISTRATION.md and its Amendment 1 exactly: frozen R
(ECAPA) and F (ECAPA + ResNet34), speaker split by seeded SHA-256, protocol P1
(every command with at least 6 usable takes is a template: 5 enrollment takes,
the rest probes), margins calibrated on the calibration cohort, one decision
on evaluation speakers. P2 (text-independent) is reported only.

Needs data/easycall/ (changelinglab/easycall-dysarthria, CC BY-NC 2.0) and
scripts.warm_candidates. Embeddings are cached in data/confirm_cache/.
Writes docs/confirm_results.{md,json} (gitignored).
"""
import argparse
from collections import defaultdict
import io
import json
from pathlib import Path
import time

import numpy as np
import pyarrow.parquet as pq
from scipy.signal import resample_poly
import soundfile as sf

from issuer.config import EVAL_MAX_PROBES, EVAL_SEED, GLOBAL_FLOOR, RECORDINGS_PER_LABEL, SAMPLE_RATE, \
    THRESHOLD_MARGIN, VARIANT_FRR_BUDGET
from issuer.verification import RecordingRejected, centroid, check_recording, spread
from ml.constants import REPO_ROOT
from ml.evaluate import Clip, roc_eer, select_trials, split_speakers, stable_key
from ml.variants import match_margin, rates, unit

CORPUS_RATE = 8000
MIN_TAKES = RECORDINGS_PER_LABEL + 1
GROUPS = ("control", "dysarthric")


def waveform_of(raw):
    """Decode one corpus take and upsample 8 kHz to 16 kHz (Amendment 1.1)."""
    audio, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
    if rate != CORPUS_RATE or audio.ndim != 1:
        raise ValueError(f"expected mono {CORPUS_RATE} Hz, got {rate} Hz")
    return resample_poly(audio, SAMPLE_RATE // CORPUS_RATE, 1).astype(np.float32)


def load(root):
    """Usable takes after the live quality check. Keeps encoded bytes, not decoded audio."""
    takes, counts = {}, defaultdict(int)
    for shard in sorted((root / "data").glob("*.parquet")):
        for row in pq.read_table(shard).to_pylist():
            counts["rows"] += 1
            severity = str(row["dysarthria_severity"]).strip()
            if severity not in {"0", "1", "2", "3"}:
                counts["no_severity_label"] += 1        # Amendment 1.2
                continue
            raw = row["audio"]["bytes"]
            try:
                check_recording(waveform_of(raw))
            except RecordingRejected:
                counts["quality_rejected"] += 1
                continue
            name = row["filename"]
            if name in takes:
                raise ValueError(f"Duplicate filename {name}")
            takes[name] = {"speaker": row["speaker"], "session": name.split("_")[1],
                           "command": " ".join(row["text"].lower().split()),
                           "group": "control" if severity == "0" else "dysarthric", "raw": raw}
            counts["usable"] += 1
    return takes, dict(counts)


def templates_p1(takes):
    """Amendment 1.3: every command with at least MIN_TAKES usable takes is one template."""
    by = defaultdict(list)
    for name, t in takes.items():
        by[(t["speaker"], t["command"])].append(name)
    out = []
    for (speaker, command), names in sorted(by.items()):
        if len(names) >= MIN_TAKES:
            ordered = sorted(names, key=lambda n: stable_key(n, EVAL_SEED))
            out.append({"speaker": speaker, "command": command, "group": takes[names[0]]["group"],
                        "enrollment": ordered[:RECORDINGS_PER_LABEL],
                        "probes": ordered[RECORDINGS_PER_LABEL:][:EVAL_MAX_PROBES]})
    return out


def embed_all(names, takes, encoder, cache_dir):
    path = cache_dir / f"{encoder}.npz"
    cached = {}
    if path.exists():
        data = np.load(path)
        cached = dict(zip(data["names"].tolist(), data["vectors"]))
    missing = sorted(set(names) - cached.keys())
    if missing:
        if encoder == "ecapa":
            from ml.encoder import embed
            fn = lambda w: embed(w, SAMPLE_RATE)  # noqa: E731
        else:
            from ml.candidate_encoders import EMBEDDERS
            fn = EMBEDDERS[encoder]
        started = time.monotonic()
        for i, name in enumerate(missing, 1):
            cached[name] = unit(fn(waveform_of(takes[name]["raw"]))).astype(np.float32)
            if i % 500 == 0 or i == len(missing):
                print(f"[{encoder}] embedded {i}/{len(missing)} ({time.monotonic() - started:.0f}s)", flush=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        keys = sorted(cached)
        np.savez(path, names=np.array(keys), vectors=np.stack([cached[k] for k in keys]))
    return cached


def score_rows(templates, speakers, vectors):
    """One row per template: held-out spread, own probes, and every other speaker's probes."""
    chosen = [t for t in templates if t["speaker"] in speakers]
    probe_names = sorted({n for t in chosen for n in t["probes"]})
    owner = np.array([n.split("_")[0] for n in probe_names])
    matrix = np.stack([vectors[n] for n in probe_names])
    rows = []
    for t in chosen:
        enrolled = np.stack([vectors[n] for n in t["enrollment"]])
        center = centroid(enrolled)
        own = np.array([vectors[n] @ center for n in t["probes"]])
        rows.append({"speaker": t["speaker"], "group": t["group"], "spread": spread(enrolled),
                     "genuine": own, "impostor": (matrix @ center)[owner != t["speaker"]]})
    return rows


def evaluate_config(rows_cal, rows_eval, target):
    margin = match_margin(rows_cal, GLOBAL_FLOOR, target)
    return {"margin": margin, "calibration": rates(rows_cal, margin, GLOBAL_FLOOR),
            "evaluation": {g: rates(rows_eval, margin, GLOBAL_FLOOR, g) for g in GROUPS}}


def p2_selections(takes, speakers):
    """TORGO-style text-independent selection (ml.evaluate.select_trials), score independent."""
    by = defaultdict(list)
    for name, t in takes.items():
        if t["speaker"] in speakers:
            by[t["speaker"]].append(Clip(name, t["speaker"], t["session"], t["group"], np.empty(0)))
    return {s: select_trials(c, EVAL_SEED, EVAL_MAX_PROBES) for s, c in by.items() if len(c) >= MIN_TAKES}


def p2(takes, selections, vectors_by_config):
    """Secondary: EER at the live policy (reported, decides nothing)."""
    out = {}
    for config, vectors in vectors_by_config.items():
        out[config] = {}
        for group in GROUPS:
            genuine, impostor = [], []
            for s, (enrollment, probes, _) in selections.items():
                if takes[enrollment[0].name]["group"] != group:
                    continue
                enrolled = np.stack([vectors[c.name] for c in enrollment])
                center, threshold = centroid(enrolled), max(GLOBAL_FLOOR, spread(enrolled) - THRESHOLD_MARGIN)
                genuine += [vectors[c.name] @ center - threshold for c in probes]
                impostor += [vectors[c.name] @ center - threshold
                             for o, (_, p, _) in selections.items() if o != s for c in p]
            out[config][group] = {"eer": roc_eer(np.array(genuine), np.array(impostor))["eer"],
                                  "genuine_trials": len(genuine), "impostor_trials": len(impostor)}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data" / "easycall")
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "data" / "confirm_cache")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs")
    args = parser.parse_args()
    try:
        takes, counts = load(args.data_dir)
        templates = templates_p1(takes)
        groups = {t["speaker"]: t["group"] for t in templates}
        calibration, evaluation = split_speakers(groups, EVAL_SEED)
        print(f"{counts}; {len(templates)} templates; calibration {calibration}; evaluation {evaluation}", flush=True)
        selections2 = p2_selections(takes, set(evaluation))
        needed = ({n for t in templates for n in t["enrollment"] + t["probes"]}
                  | {c.name for e, p, _ in selections2.values() for c in e + p})
        ecapa = embed_all(needed, takes, "ecapa", args.cache_dir)
        resnet34 = embed_all(needed, takes, "resnet34", args.cache_dir)
        configs = {"R": ecapa, "F": {n: unit(np.concatenate([ecapa[n], resnet34[n]])) for n in needed}}

        rows = {c: (score_rows(templates, set(calibration), v), score_rows(templates, set(evaluation), v))
                for c, v in configs.items()}
        target = rates(rows["R"][0], THRESHOLD_MARGIN, GLOBAL_FLOOR)["frr"]
        result = {c: evaluate_config(cal, ev, target) for c, (cal, ev) in rows.items()}
        R, F = result["R"]["evaluation"], result["F"]["evaluation"]
        checks = {
            "lower_eer_control": F["control"]["eer"] < R["control"]["eer"],
            "lower_eer_dysarthric": F["dysarthric"]["eer"] < R["dysarthric"]["eer"],
            "lower_far_control": F["control"]["far"] < R["control"]["far"],
            "lower_far_dysarthric": F["dysarthric"]["far"] < R["dysarthric"]["far"],
            "dysarthric_frr_within_budget": F["dysarthric"]["frr"] <= R["dysarthric"]["frr"] + VARIANT_FRR_BUDGET,
        }
        secondary = p2(takes, selections2, configs)
        summary = {"counts": counts, "templates": len(templates), "calibration_speakers": calibration,
                   "evaluation_speakers": evaluation, "target_calibration_frr": target, "results": result,
                   "checks": checks, "adopt": all(checks.values()), "p2_secondary": secondary}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "confirm_results.json").write_text(json.dumps(summary, indent=2, default=float) + "\n",
                                                              encoding="utf-8")
        pct = lambda x: f"{x:.2%}"  # noqa: E731
        lines = ["# Pre-registered fusion confirmation on EasyCall", "",
                 "Protocol: docs/PREREGISTRATION.md with Amendment 1. EasyCall (Turrisi et al., Interspeech 2021), "
                 "CC BY-NC 2.0, non-commercial evaluation.", "",
                 f"Decision: **{'adopt F' if summary['adopt'] else 'do not adopt F'}**. Checks: `{json.dumps(checks)}`.", "",
                 f"Calibration speakers ({len(calibration)}): {', '.join(calibration)}. "
                 f"Evaluation speakers ({len(evaluation)}): {', '.join(evaluation)}.",
                 f"Target calibration FRR (R at the live margin): {pct(target)}. Templates: {len(templates)}. "
                 f"Corpus counts: `{json.dumps(counts, sort_keys=True)}`.", "",
                 "| Config | Margin | Group | Templates | Genuine / impostor trials | EER | FAR | FRR |",
                 "|---|---:|---|---:|---:|---:|---:|---:|"]
        for c, label in (("R", "R: ECAPA (live)"), ("F", "F: ECAPA + ResNet34")):
            for g in GROUPS:
                e = result[c]["evaluation"][g]
                lines.append(f"| {label} | {result[c]['margin']:.3f} | {g} | {e['speakers']} | "
                             f"{e['genuine_trials']} / {e['impostor_trials']} | {pct(e['eer'])} | {pct(e['far'])} | {pct(e['frr'])} |")
        lines += ["", f"Secondary P2 (text-independent, reported only): `{json.dumps(secondary, default=float)}`.", "",
                  "Audio is 8 kHz, upsampled to 16 kHz for both configurations. Italian command speech; one corpus; "
                  "correlated trials. Not a population-level claim.", ""]
        (args.output_dir / "confirm_results.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"adopt={summary['adopt']} {checks}", flush=True)
        for c in ("R", "F"):
            for g in GROUPS:
                e = result[c]["evaluation"][g]
                print(f"  {c} {g}: EER {pct(e['eer'])} FAR {pct(e['far'])} FRR {pct(e['frr'])} "
                      f"({e['genuine_trials']}/{e['impostor_trials']}) margin {result[c]['margin']:.3f}", flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Confirmation failed: {exc}\nNothing new was written.\n")


if __name__ == "__main__":
    main()
