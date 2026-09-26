# Reproducing Phase 8

Run from the repository root after installing requirements and caching data:

```sh
.venv/bin/python -m scripts.warm_cache
make eval
```

Windows uses `.venv/Scripts/python.exe`. The evaluator reads local parquet shards
under `data/torgo_hf/data/`, using `DATA_DIR` from `.env` if set. It does not
transcribe audio, contact payment providers, alter enrollments, or tune live
thresholds. `--help` does not load the model.

```sh
.venv/bin/python -m scripts.run_eval --max-probes 40 --seed 20260925
.venv/bin/python -m scripts.run_eval --max-probes 100000 --output-dir data/eval-full
```

The second command uses all available held-out probes and can take much longer.
Default sampling is deterministic by filename before scoring, not by outcome.
The official report must state the probe cap; do not compare runs with different
caps as though their trial sets were identical.

Outputs: `docs/eval_results.md`, `docs/eval_results.json`, `docs/eval_roc.png`.
The JSON records exact enrollment/probe filenames and cohort membership. These
are generated local outputs and are ignored by Git. A failed run exits nonzero;
any previous report remains an older result and must not be presented as new.

Protocol is ADR 6. Development identities are reserved, not used to fit a model
or tune thresholds. Genuine probes share evaluation identity with enrollment,
but never recording. Cross-session evaluation is preferred. The report labels
same-session fallback, quality exclusions, and low-cohesion templates. The
experiment pools different utterances into one template per identity; it does
not reproduce the live sound-label policy, randomized challenge, or passkey
fallback. Low-cohesion speakers remain visible in the diagnostic result rather
than disappearing as successful enrollments.

EER is computed on `cosine score - personal threshold`, sweeping a common
margin offset. FAR/FRR are measured at offset zero. Equality passes. Tied scores
move together; EER is linearly interpolated between empirical operating points.
Report both pooled trial rates and speaker-macro averages, with exact N.
No clinical, population-level, anti-spoofing, or payment-security claim follows
from this small correlated corpus experiment.

Reference schema: https://huggingface.co/datasets/abnerh/TORGO-database
