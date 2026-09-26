"""Run the offline TORGO evaluation. See docs/EVALUATION.md for the protocol."""
import argparse
from collections import Counter
import io
import json
import os
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from issuer.config import (EVAL_MAX_PROBES, EVAL_SEED, GLOBAL_FLOOR, MIN_DURATION, RECORDINGS_PER_LABEL,
                           SAMPLE_RATE, THRESHOLD_MARGIN)
from issuer.verification import RecordingRejected, check_recording
from ml.constants import ECAPA_DIR, REPO_ROOT, TORGO_SUBDIR
from ml.evaluate import Clip, evaluate, metadata, select_trials


def load_candidates(root):
    # Streaming parquet keeps the 1.6 GB corpus out of RAM. datasets is already
    # a pinned dependency. Audio(decode=False) avoids TorchCodec and resampling.
    from datasets import Audio, load_dataset
    shards = sorted(root.glob("data/*.parquet"))
    if not shards:
        raise ValueError(f"No TORGO parquet shards in {root / 'data'}. Run python -m scripts.warm_cache")
    dataset = load_dataset("parquet", data_files=[str(p) for p in shards], split="train", streaming=True)
    dataset = dataset.cast_column("audio", Audio(decode=False))
    counts = Counter()
    by_speaker = {}
    names = set()
    for row in dataset:
        counts["rows"] += 1
        audio = row["audio"]
        name, speaker, session, mic, group = metadata(audio.get("path") or "", row.get("speech_status"))
        if mic != "headmic":
            counts["other_microphone"] += 1
            continue
        counts["headmic"] += 1
        if name in names:
            raise ValueError(f"Duplicate headMic recording: {name}")
        names.add(name)
        source = io.BytesIO(audio["bytes"]) if audio.get("bytes") else root / audio["path"]
        waveform, rate = sf.read(source, dtype="float32", always_2d=False)
        if rate != SAMPLE_RATE or waveform.ndim != 1 or not np.isfinite(waveform).all():
            raise ValueError(f"{name}: expected finite mono {SAMPLE_RATE} Hz audio, got {rate} Hz / {waveform.shape}")
        try:
            check_recording(waveform)
        except RecordingRejected as exc:
            reason = "too_short" if waveform.size < SAMPLE_RATE * MIN_DURATION else "quality_rejected"
            counts[reason] += 1
            continue
        counts["usable"] += 1
        # Keep encoded corpus bytes for selected clips, not expanded arrays.
        by_speaker.setdefault(speaker, []).append((Clip(name, speaker, session, group, np.empty(0)), audio))
    return by_speaker, dict(counts), [{"name": p.name, "bytes": p.stat().st_size} for p in shards]


def report_text(result):
    lines = ["# TORGO evaluation (preliminary)", "", "This is a small-corpus, text-independent speaker verification experiment, not a payment-security benchmark or clinical result.", "",
             f"Seed: {result['seed']}. Microphone: headMic only. Enrollment: {RECORDINGS_PER_LABEL} takes. Maximum probes per identity: {result['max_probes']}.",
             f"Fixed operating policy: max({GLOBAL_FLOOR}, spread - {THRESHOLD_MARGIN}). No tuning on this corpus.",
             f"Development identities (reserved, not scored): {', '.join(result['development_speakers'])}.",
             f"Evaluation identities: {', '.join(result['evaluation_speakers'])}.", "",
             "| Threshold spread | Claimed group | N speakers | Genuine / impostor trials | EER (margin sweep) | FAR | FRR | Macro FAR / FRR |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for variant, groups in result["results"].items():
        for group, cell in groups.items():
            lines.append(f"| {variant} | {group} | {len(cell['per_speaker'])} | {cell['genuine_trials']} / {cell['impostor_trials']} | {cell['eer']:.2%} | {cell['far_at_operating_point']:.2%} | {cell['frr_at_operating_point']:.2%} | {cell['speaker_macro_far']:.2%} / {cell['speaker_macro_frr']:.2%} |")
    lines += ["", "FAR/FRR use the fixed personal thresholds. EER sweeps score minus personal threshold, with linear interpolation between empirical ROC points; it does not choose a deployment threshold. Trial rates are pooled; macro rates give each claimed speaker equal weight. Impostors are all other evaluation speakers, across both groups.", "", "## Coverage and caveats", "", f"Corpus counts: `{json.dumps(result['counts'], sort_keys=True)}`.", f"Excluded speakers: `{json.dumps(result['excluded_speakers'], sort_keys=True)}`.", "", "| Speaker | Group | Session protocol | Probes | Enrollment cohesion | Below live cohesion minimum |", "|---|---|---|---:|---:|---|"]
    for row in result["protocol"]:
        lines.append(f"| {row['speaker']} | {row['group']} | {row['protocol']} | {len(row['probes'])} | {row['cohesion']:.3f} | {row['low_cohesion']} |")
    lines += ["", "- Enrollment and probes never share recordings; development and evaluation never share identities.",
              "- Cross-session trials are preferred; same-session fallbacks are disclosed above. Neither is longitudinal clinical evidence.",
              "- Different corpus utterances form one template per speaker. This does not test three user-chosen sound labels, the two-sound challenge, replay rejection, or passkeys.",
              "- Low-cohesion identities stay in this diagnostic experiment to expose failures. The live product would route low-confidence sound labels to a passkey; these rates do not model that policy.",
              "- Short/quiet/long clips are excluded by the existing enrollment quality policy, which can bias coverage. No disabled speech is simulated.",
              "- Correlated trials and few speakers preclude broad population claims. EER is descriptive; ADR 3 remains provisional pending representative live enrollment data.",
              "", "![ROC by cohort and threshold spread](eval_roc.png)", "",
              "Protocol, exclusions, and exact enrollment/probe filenames are in `eval_results.json`. Reproduce with `make eval`. See `EVALUATION.md` for options.", "",
              "Source: [abnerh/TORGO-database](https://huggingface.co/datasets/abnerh/TORGO-database). Rudzicz, Namasivayam, and Wolff (2012), The TORGO database of acoustic and articulatory speech from speakers with dysarthria, Language Resources and Evaluation 46(4), 523-541.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / os.environ.get("DATA_DIR", "data") / TORGO_SUBDIR)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--seed", type=int, default=EVAL_SEED)
    parser.add_argument("--max-probes", type=int, default=EVAL_MAX_PROBES)
    args = parser.parse_args()
    if args.max_probes < 1:
        parser.error("--max-probes must be positive")
    try:
        by_speaker, counts, shards = load_candidates(args.data_dir)
        print(f"Corpus: {counts}; headMic speakers: {sorted(by_speaker)}", flush=True)
        selected = []
        excluded = {}
        for speaker, rows in sorted(by_speaker.items()):
            try:
                enrollment, probes, _ = select_trials([c for c, _ in rows], args.seed, args.max_probes)
            except ValueError as exc:
                if len(rows) >= RECORDINGS_PER_LABEL + 1:
                    raise
                excluded[speaker] = str(exc)
                continue
            wanted = {c.name for c in enrollment + probes}
            selected.extend((clip, audio) for clip, audio in rows if clip.name in wanted)
        if not selected:
            raise ValueError("No eligible speakers after quality filtering")
        # Validate cohort feasibility before paying the model-loading cost.
        from ml.evaluate import split_speakers
        split_speakers({c.speaker: c.group for c, _ in selected}, args.seed)
        if not (ECAPA_DIR / "embedding_model.ckpt").exists():
            raise ValueError("ECAPA cache missing. Run python -m scripts.warm_cache")
        from ml.encoder import embed
        started = time.monotonic()
        clips = []
        for i, (clip, audio) in enumerate(selected, 1):
            source = io.BytesIO(audio["bytes"]) if audio.get("bytes") else args.data_dir / audio["path"]
            waveform, rate = sf.read(source, dtype="float32")
            clips.append(Clip(clip.name, clip.speaker, clip.session, clip.group, embed(waveform, rate)))
            if i % 25 == 0 or i == len(selected):
                print(f"Embedded {i}/{len(selected)} ({time.monotonic() - started:.1f}s)", flush=True)
        result = evaluate(clips, args.seed, args.max_probes)
        result["excluded_speakers"].update(excluded)
        result.update(seed=args.seed, max_probes=args.max_probes, counts=counts, shards=shards)
        # Create all outputs only after a successful evaluation.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 5))
        for variant, groups in result["results"].items():
            for group, cell in groups.items():
                ax.plot(cell["far"], 1 - np.array(cell["frr"]),
                        label=f"{group}, {variant}, N={len(cell['per_speaker'])}")
        ax.set(xlabel="False accept rate", ylabel="True accept rate", title="TORGO headMic: preliminary margin ROC", xlim=(0, 1), ylim=(0, 1))
        ax.legend(fontsize=8)
        ax.grid(alpha=.25)
        fig.tight_layout()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output_dir / "eval_roc.png", dpi=160)
        plt.close(fig)
        (args.output_dir / "eval_results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (args.output_dir / "eval_results.md").write_text(report_text(result), encoding="utf-8")
        print(f"Wrote evaluation to {args.output_dir}", flush=True)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\nNo new report was produced; any existing report is from an earlier run.\n")


if __name__ == "__main__":
    main()
