"""Template adaptation (§7.4) replayed over later TORGO sessions, for the Dashboard.

For each evaluation speaker with a cross-session protocol in
docs/eval_results.json, the Phase 8 enrollment builds two copies of one
template: static, and adaptive (issuer.verification.adapt, confident passes
only, MAX_DRIFT clamp). Both score the same takes from the speaker's other
sessions, in recording order. Afterwards, every other speaker's Phase 8 probes
are scored against both final templates, to show whether adaptation made
impostors easier to accept. Writes web/public/drift/results.json (gitignored).

Recording sessions are days apart, not months: this shows the mechanism on
real corpus audio, not progression of a condition.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np
import pyarrow.parquet as pq

from issuer.config import ALPHA, CONFIDENT_MARGIN, MAX_DRIFT, SAMPLE_RATE
from issuer.verification import RecordingRejected, adapt, centroid, check_recording, personal_threshold, score, spread
from ml.constants import REPO_ROOT, TORGO_SUBDIR
from ml.evaluate import NAME_RE
from scripts.run_baseline import load_clips

TAKES_PER_SPEAKER = 120
BINS = 6


def corpus_names(root):
    """Every headMic filename, from the path column only (no audio decoded)."""
    names = []
    for shard in sorted(root.glob("data/*.parquet")):
        paths = pq.read_table(shard, columns=["audio"]).column("audio").combine_chunks().field("path")
        names += [p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths.to_pylist() if "headMic" in p]
    return names


def chronological(names):
    def key(name):
        speaker, session, _, index = NAME_RE.fullmatch(name).groups()
        return int(session), int(index)
    return sorted(names, key=key)


def evenly(items, n):
    if len(items) <= n:
        return items
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / os.environ.get("DATA_DIR", "data") / TORGO_SUBDIR)
    parser.add_argument("--eval-json", type=Path, default=REPO_ROOT / "docs" / "eval_results.json")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "web" / "public" / "drift")
    args = parser.parse_args()
    try:
        if not args.eval_json.exists():
            raise ValueError(f"{args.eval_json} missing. Run make eval first.")
        evaluation = json.loads(args.eval_json.read_text(encoding="utf-8"))
        protocol = evaluation["protocol"]
        speakers = [r for r in protocol if r["protocol"] == "cross-session"]
        if not speakers:
            raise ValueError("No cross-session speakers in eval_results.json")
        names = corpus_names(args.data_dir)
        plans = {}
        for row in speakers:
            enrolled_session = NAME_RE.fullmatch(row["enrollment"][0]).group(2)
            later = [n for n in names if n.startswith(row["speaker"] + "_")
                     and NAME_RE.fullmatch(n).group(2) != enrolled_session and n not in row["enrollment"]]
            # Over-select, then drop takes the live quality check would reject.
            plans[row["speaker"]] = evenly(chronological(later), TAKES_PER_SPEAKER * 2)
        wanted = ({n for r in protocol for n in r["enrollment"] + r["probes"]}
                  | {n for plan in plans.values() for n in plan})
        clips = load_clips(args.data_dir, wanted)
        from ml.encoder import embed
        started = time.monotonic()
        vectors = {}
        for i, (name, clip) in enumerate(clips.items(), 1):
            try:
                check_recording(clip["waveform"])
            except RecordingRejected:
                continue
            vectors[name] = embed(clip["waveform"], SAMPLE_RATE)
            if i % 100 == 0 or i == len(clips):
                print(f"Embedded {i}/{len(clips)} ({time.monotonic() - started:.1f}s)", flush=True)

        series, impostor = [], {"static": [], "adaptive": []}
        for row in speakers:
            enrolled = np.stack([vectors[n] for n in row["enrollment"]])
            threshold = personal_threshold(spread(enrolled))
            static = adaptive = centroid(enrolled)
            takes = evenly([n for n in plans[row["speaker"]] if n in vectors], TAKES_PER_SPEAKER)
            points, updates = [], 0
            for name in takes:
                vec = vectors[name]
                s_static, s_adaptive = score(vec, static), score(vec, adaptive)
                points.append({"take": name, "session": NAME_RE.fullmatch(name).group(2),
                               "static": s_static >= threshold, "adaptive": s_adaptive >= threshold,
                               "static_margin": s_static - threshold, "adaptive_margin": s_adaptive - threshold})
                # Live behaviour: only an accepted take can adapt, and adapt()
                # applies the confident-pass gate and the clamp itself.
                if s_adaptive >= threshold:
                    adaptive, drift = adapt(adaptive, vec, threshold)
                    updates += drift is not None
            others = [vectors[n] for r in protocol if r["speaker"] != row["speaker"]
                      for n in r["probes"] if n in vectors]
            for variant, template in (("static", static), ("adaptive", adaptive)):
                impostor[variant] += [score(v, template) >= threshold for v in others]
            series.append({"speaker": row["speaker"], "group": row["group"], "threshold": threshold,
                           "updates": updates, "total_drift": float(1 - adaptive @ static), "points": points})

        def binned(variant, group):
            rows = [s for s in series if group in (None, s["group"])]
            out = []
            for b in range(BINS):
                hits = [p[variant] for s in rows for p in s["points"][b * len(s["points"]) // BINS:
                                                                      (b + 1) * len(s["points"]) // BINS]]
                out.append(float(np.mean(hits)) if hits else None)
            return out

        result = {"generated": time.strftime("%Y-%m-%d %H:%M"), "alpha": ALPHA, "max_drift": MAX_DRIFT,
                  "confident_margin": CONFIDENT_MARGIN, "bins": BINS, "series": series,
                  "accept_by_bin": {g or "all": {v: binned(v, g) for v in ("static", "adaptive")}
                                    for g in (None, "control", "dysarthric")},
                  "accept_overall": {v: float(np.mean([p[v] for s in series for p in s["points"]]))
                                     for v in ("static", "adaptive")},
                  "impostor_accept": {v: float(np.mean(x)) for v, x in impostor.items()},
                  "impostor_trials": len(impostor["static"])}
        staging = args.output_dir.with_name(args.output_dir.name + ".tmp")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        (staging / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        shutil.rmtree(args.output_dir, ignore_errors=True)
        staging.rename(args.output_dir)
        print(f"Speakers {len(series)}; genuine accept static {result['accept_overall']['static']:.1%}, "
              f"adaptive {result['accept_overall']['adaptive']:.1%}; impostor accept static "
              f"{result['impostor_accept']['static']:.2%}, adaptive {result['impostor_accept']['adaptive']:.2%} "
              f"({result['impostor_trials']} trials)", flush=True)
        print(f"By bin (all): {result['accept_by_bin']['all']}", flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Drift simulation failed: {exc}\nNothing was written.\n")


if __name__ == "__main__":
    main()
