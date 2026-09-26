"""Compare accuracy candidates on the Phase 8 trials (docs/RESEARCH.md §4, ADR 7).

Same corpus filter, quality check, seed, and trial selection as make eval.
Embeddings are cached per preprocessing variant under data/variant_cache/, so
a rerun only rescores. Writes docs/variants_results.{md,json} (gitignored).
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from issuer import config
from issuer.config import EVAL_MAX_PROBES, EVAL_SEED, RECORDINGS_PER_LABEL, SAMPLE_RATE, VARIANT_FRR_BUDGET
from ml.constants import ECAPA_DIR, REPO_ROOT, TORGO_SUBDIR
from ml.evaluate import select_trials, split_speakers
from ml.preprocess import crops, trim_silence
from ml.variants import ASNorm, Centroid, MeanSub, TopK, compare, unit
from scripts.run_eval import load_candidates

PREPROCESSORS = {
    "plain": lambda w: [w],
    "trim": lambda w: [trim_silence(w)],
    "crops": lambda w: [w] + (crops(w) if len(crops(w)) > 1 else []),
    "trim+crops": lambda w: (lambda t: [t] + (crops(t) if len(crops(t)) > 1 else []))(trim_silence(w)),
}
SCORERS = [Centroid(), TopK(), MeanSub(Centroid())] + [ASNorm(k) for k in config.ASNORM_TOP_K_GRID] \
    + [MeanSub(ASNorm(config.ASNORM_TOP_K_GRID[1]))]


def cache_key(variant, names):
    settings = {k: getattr(config, k) for k in dir(config) if k.startswith(("TRIM_", "CROP_"))}
    blob = json.dumps({"variant": variant, "settings": settings, "names": sorted(names),
                       "model": (ECAPA_DIR / "embedding_model.ckpt").stat().st_size}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def embeddings_for(variant, waveforms, cache_dir):
    path = cache_dir / f"{variant.replace('+', '_')}-{cache_key(variant, waveforms)}.npz"
    if path.exists():
        data = np.load(path)
        return dict(zip(data["names"].tolist(), data["vectors"]))
    from ml.encoder import embed
    started, vectors = time.monotonic(), {}
    for i, (name, waveform) in enumerate(sorted(waveforms.items()), 1):
        pieces = PREPROCESSORS[variant](waveform)
        vectors[name] = unit(np.mean([embed(p, SAMPLE_RATE) for p in pieces], axis=0)).astype(np.float32)
        if i % 100 == 0 or i == len(waveforms):
            print(f"[{variant}] embedded {i}/{len(waveforms)} ({time.monotonic() - started:.1f}s)", flush=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(vectors)
    np.savez(path, names=np.array(names), vectors=np.stack([vectors[n] for n in names]))
    return vectors


def pct(x):
    return f"{x:.2%}"


def report(result, counts):
    ref, chosen = result["reference"], result["chosen"]
    lines = ["# Accuracy candidates on TORGO (preliminary)", "",
             "Small corpus; development speakers choose, evaluation speakers are scored once. See docs/RESEARCH.md §4 and ADR 7.", "",
             f"Development target FRR (live policy on development speakers): {pct(result['target_development_frr'])}.",
             f"Reference: plain + centroid under the same calibration. Chosen by lowest development EER: **{chosen['embedding']} + {chosen['scorer']}**.",
             f"Decision: **{'adopt' if result['adopt'] else 'do not adopt'}** (checks: `{json.dumps(result['checks'])}`, FRR budget {pct(VARIANT_FRR_BUDGET)}).", "",
             "| Embedding | Scorer | Margin | Dev EER | Dev FRR | Control FAR | Control FRR | Control EER | Dysarthric FAR | Dysarthric FRR | Dysarthric EER |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in sorted(result["rows"], key=lambda r: r["development"]["eer"]):
        tag = " (reference)" if row is ref else " (chosen)" if row is chosen else ""
        c, d = row["evaluation"]["control"], row["evaluation"]["dysarthric"]
        lines.append(f"| {row['embedding']} | {row['scorer']}{tag} | {row['margin']:.3f} | {pct(row['development']['eer'])} | "
                     f"{pct(row['development']['frr'])} | {pct(c['far'])} | {pct(c['frr'])} | {pct(c['eer'])} | "
                     f"{pct(d['far'])} | {pct(d['frr'])} | {pct(d['eer'])} |")
    live = result["live"]
    lines += ["", f"Live policy on evaluation speakers (as in make eval): control FAR {pct(live['control']['far'])} / FRR {pct(live['control']['frr'])}; "
              f"dysarthric FAR {pct(live['dysarthric']['far'])} / FRR {pct(live['dysarthric']['frr'])}.",
              f"Trials per evaluation row: control {ref['evaluation']['control']['genuine_trials']} genuine / {ref['evaluation']['control']['impostor_trials']} impostor; "
              f"dysarthric {ref['evaluation']['dysarthric']['genuine_trials']} / {ref['evaluation']['dysarthric']['impostor_trials']}. "
              f"Development: {ref['development']['speakers']} speakers, {ref['development']['genuine_trials']} genuine / {ref['development']['impostor_trials']} impostor.",
              "", "Evaluation rows other than the chosen one are shown for transparency only; picking a different row because of its evaluation numbers would be tuning on evaluation speakers.",
              "Development numbers for cohort-based scorers (asnorm, meansub) are optimistic: with only 4 development speakers, their cohort is drawn from the same speakers who act as development impostors (ADR 7).",
              "Rows with margin 100.000 never reached the development FRR target because the cosine floor binds.",
              "The template pools five different corpus words; live enrollment uses five takes of one chosen sound. Gains may not transfer one to one.",
              f"Corpus counts: `{json.dumps(counts, sort_keys=True)}`.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / os.environ.get("DATA_DIR", "data") / TORGO_SUBDIR)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / os.environ.get("DATA_DIR", "data") / "variant_cache")
    args = parser.parse_args()
    try:
        by_speaker, counts, _ = load_candidates(args.data_dir)
        selections, groups = {}, {}
        for speaker, rows in sorted(by_speaker.items()):
            if len(rows) < RECORDINGS_PER_LABEL + 1:
                continue
            selections[speaker] = select_trials([c for c, _ in rows], EVAL_SEED, EVAL_MAX_PROBES)
            groups[speaker] = rows[0][0].group
        development, evaluation = split_speakers(groups, EVAL_SEED)
        selections = {s: ([c.name for c in e], [c.name for c in p], mode) for s, (e, p, mode) in selections.items()}
        eval_json = args.output_dir / "eval_results.json"
        if eval_json.exists():
            # Same protocol as make eval, or the comparison is not like for like.
            previous = {r["speaker"]: (r["enrollment"], r["probes"]) for r in json.loads(eval_json.read_text("utf-8"))["protocol"]}
            if any(previous.get(s) != selections[s][:2] for s in evaluation):
                raise ValueError("Trial selection differs from docs/eval_results.json; rerun make eval")
        wanted = {n for e, p, _ in selections.values() for n in e + p}
        waveforms = {}
        for speaker in selections:
            for clip, audio in by_speaker[speaker]:
                if clip.name in wanted:
                    source = io.BytesIO(audio["bytes"]) if audio.get("bytes") else args.data_dir / audio["path"]
                    waveforms[clip.name] = sf.read(source, dtype="float32")[0]
        print(f"{len(waveforms)} recordings; development {development}; evaluation {evaluation}", flush=True)
        embeddings = {v: embeddings_for(v, waveforms, args.cache_dir) for v in PREPROCESSORS}
        result = compare(SCORERS, embeddings, selections, groups, development, evaluation)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "variants_results.json").write_text(json.dumps(result, indent=2, default=float) + "\n", encoding="utf-8")
        (args.output_dir / "variants_results.md").write_text(report(result, counts), encoding="utf-8")
        chosen = result["chosen"]
        print(f"Chosen on development: {chosen['embedding']} + {chosen['scorer']}; adopt={result['adopt']} {result['checks']}", flush=True)
        for row in (result["reference"], chosen):
            e = row["evaluation"]
            print(f"  {row['embedding']} + {row['scorer']}: control FAR {pct(e['control']['far'])} FRR {pct(e['control']['frr'])}; "
                  f"dysarthric FAR {pct(e['dysarthric']['far'])} FRR {pct(e['dysarthric']['frr'])}", flush=True)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Variant comparison failed: {exc}\nNothing new was written.\n")


if __name__ == "__main__":
    main()
