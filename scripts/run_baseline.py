"""Transcription check vs Timbre on the Phase 8 trials, for the Baseline page.

Reuses the exact enrollment and probe recordings from docs/eval_results.json
(run `make eval` first), so both checks are scored on identical takes. Writes
web/public/baseline/results.json plus the example clips (gitignored: corpus
audio is never committed).
"""
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np
import soundfile as sf

from issuer.config import BASELINE_MAX_WER, SAMPLE_RATE
from issuer.verification import centroid, personal_threshold, spread
from ml.baseline_asr import compare, passes, scoreable, transcribe, wer
from ml.constants import REPO_ROOT, TORGO_SUBDIR, WHISPER_DIR

EXAMPLES_PER_SPEAKER = 2
SELECTION_RULE = (f"For each dysarthric speaker, the first {EXAMPLES_PER_SPEAKER} test takes (in the "
                  "evaluation's fixed, score-independent order) that the transcription check rejects and "
                  "Timbre accepts. Chosen to show the contrast; the rates above cover every trial.")


def load_clips(root, wanted):
    from datasets import Audio, load_dataset
    shards = sorted(root.glob("data/*.parquet"))
    if not shards:
        raise ValueError(f"No TORGO parquet shards in {root / 'data'}. Run python -m scripts.warm_cache")
    dataset = load_dataset("parquet", data_files=[str(p) for p in shards], split="train", streaming=True)
    dataset = dataset.cast_column("audio", Audio(decode=False))
    clips = {}
    for row in dataset:
        audio = row["audio"]
        name = (audio.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
        if name not in wanted:
            continue
        source = io.BytesIO(audio["bytes"]) if audio.get("bytes") else root / audio["path"]
        waveform, rate = sf.read(source, dtype="float32", always_2d=False)
        if rate != SAMPLE_RATE or waveform.ndim != 1:
            raise ValueError(f"{name}: expected mono {SAMPLE_RATE} Hz audio")
        clips[name] = {"waveform": waveform, "prompt": row["transcription"].strip()}
    missing = wanted - clips.keys()
    if missing:
        raise ValueError(f"{len(missing)} evaluation recordings not found in the corpus, e.g. {sorted(missing)[:3]}")
    return clips


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / os.environ.get("DATA_DIR", "data") / TORGO_SUBDIR)
    parser.add_argument("--eval-json", type=Path, default=REPO_ROOT / "docs" / "eval_results.json")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "web" / "public" / "baseline")
    args = parser.parse_args()
    try:
        if not args.eval_json.exists():
            raise ValueError(f"{args.eval_json} missing. Run make eval first.")
        if not (WHISPER_DIR / "model.bin").exists():
            raise ValueError("Whisper small missing. Run python -m scripts.warm_asr")
        evaluation = json.loads(args.eval_json.read_text(encoding="utf-8"))
        protocol = evaluation["protocol"]
        wanted = {n for row in protocol for n in row["enrollment"] + row["probes"]}
        clips = load_clips(args.data_dir, wanted)
        print(f"Loaded {len(clips)} evaluation recordings", flush=True)

        from ml.encoder import embed
        started = time.monotonic()
        vectors = {name: embed(c["waveform"], SAMPLE_RATE) for name, c in clips.items()}
        print(f"Embedded {len(vectors)} ({time.monotonic() - started:.1f}s)", flush=True)

        templates = {}
        for row in protocol:
            enrolled = np.stack([vectors[n] for n in row["enrollment"]])
            threshold = personal_threshold(spread(enrolled))
            # Same recordings and formula as make eval, so this must reproduce it.
            if not np.isclose(threshold, row["thresholds"]["held_out"], atol=1e-4):
                raise ValueError(f"{row['speaker']}: threshold {threshold:.4f} differs from eval_results.json")
            templates[row["speaker"]] = (centroid(enrolled), threshold, row["group"])

        takes = [(row["speaker"], n) for row in protocol for n in row["probes"] if scoreable(clips[n]["prompt"])]
        skipped = sum(len(row["probes"]) for row in protocol) - len(takes)
        started = time.monotonic()
        heard = {}
        for i, (_, name) in enumerate(takes, 1):
            heard[name] = transcribe(clips[name]["waveform"])
            if i % 25 == 0 or i == len(takes):
                print(f"Transcribed {i}/{len(takes)} ({time.monotonic() - started:.1f}s)", flush=True)
        asr_seconds = time.monotonic() - started

        trials = []
        for claimed, (center, threshold, claimed_group) in templates.items():
            for speaker, name in takes:
                score = float(vectors[name] @ center)
                trials.append({"kind": "genuine" if speaker == claimed else "impostor", "claimed": claimed,
                               "claimed_group": claimed_group, "take": name,
                               "baseline_pass": passes(clips[name]["prompt"], heard[name]),
                               "timbre_pass": score >= threshold, "score": score, "threshold": threshold})
        rates = compare(trials)

        per_speaker, examples = [], []
        for row in protocol:
            own = [t for t in trials if t["kind"] == "genuine" and t["claimed"] == row["speaker"]]
            per_speaker.append({"speaker": row["speaker"], "group": row["group"], "trials": len(own),
                                "baseline_accepts": float(np.mean([t["baseline_pass"] for t in own])),
                                "timbre_accepts": float(np.mean([t["timbre_pass"] for t in own]))})
            if row["group"] != "dysarthric":
                continue
            contrast = [t for t in own if not t["baseline_pass"] and t["timbre_pass"]]
            for t in contrast[:EXAMPLES_PER_SPEAKER]:
                prompt = clips[t["take"]]["prompt"]
                examples.append({"speaker": row["speaker"], "audio": t["take"], "prompt": prompt,
                                 "heard": heard[t["take"]], "wer": wer(prompt, heard[t["take"]]),
                                 "score": t["score"], "threshold": t["threshold"]})

        result = {"generated": time.strftime("%Y-%m-%d %H:%M"), "seed": evaluation["seed"],
                  "max_wer": BASELINE_MAX_WER, "rates": rates, "per_speaker": per_speaker,
                  "examples": examples, "selection_rule": SELECTION_RULE,
                  "skipped_unscoreable_takes": skipped, "asr_seconds_per_take": asr_seconds / len(takes)}
        # Replace the whole output folder only after everything succeeded.
        staging = args.output_dir.with_name(args.output_dir.name + ".tmp")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        for example in examples:
            sf.write(staging / example["audio"], clips[example["audio"]]["waveform"], SAMPLE_RATE, subtype="PCM_16")
        (staging / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        shutil.rmtree(args.output_dir, ignore_errors=True)
        staging.rename(args.output_dir)
        for group, cell in rates.items():
            print(f"{group}: transcription accepts the right person {cell['baseline_accepts_genuine']:.1%}, "
                  f"someone else {cell['baseline_accepts_impostor']:.1%}; Timbre {cell['timbre_accepts_genuine']:.1%} "
                  f"and {cell['timbre_accepts_impostor']:.1%} (N={cell['speakers']} speakers, "
                  f"{cell['genuine_trials']} genuine / {cell['impostor_trials']} impostor trials)", flush=True)
        print(f"Wrote {len(examples)} examples to {args.output_dir}", flush=True)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Baseline failed: {exc}\nNo new baseline was written.\n")


if __name__ == "__main__":
    main()
