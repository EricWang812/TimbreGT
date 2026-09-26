# Research: improving speaker verification accuracy and lowering false accepts

Part of the Timbre instruction set. Read `AGENTS.md` first. Prior art we must
not overclaim is in `docs/CONTEXT.md` §11; this file is the working survey
behind ADR 7. Style rule: no em dashes.

**Scope.** Techniques that could make the acoustic check more accurate for our
users, and in particular reduce false accepts (someone else approved as the
cardholder) without pushing false rejects back up for dysarthric speakers.
Every candidate is measured with the existing Phase 8 protocol (ADR 6) before
it can touch the live path. Nothing here involves transcription (§2.1) or
simulated speech (§2.3).

## 1. The problem, in published numbers

- Speech pathology degrades off-the-shelf speaker verification badly. A
  large-scale study reports ECAPA-class systems going from low single-digit
  EER on typical speech to roughly 16% to 43% on pathological speech,
  including dysarthria ([effect of speech pathology on ASV, large-scale
  study](https://arxiv.org/pdf/2204.06450);
  [quantifying the effect of pathology on automatic and human
  SV](https://arxiv.org/html/2406.06208)).
- Dysarthric speaker verification is an active research area: x-vectors with
  duration-modification augmentation (Salim et al., Interspeech 2022,
  [paper](https://www.isca-archive.org/interspeech_2022/salim22_interspeech.pdf)),
  CQCC features ([2023](https://link.springer.com/article/10.1007/s00034-023-02505-0)),
  prosodic features with out-of-domain augmentation
  ([2023](https://www.sciencedirect.com/science/article/abs/pii/S0003682X23002104)),
  augmentation plus feature fusion
  ([2024](https://www.sciencedirect.com/science/article/abs/pii/S0167639324000426)),
  and temporal discriminative bottleneck embeddings
  ([2025](https://www.sciencedirect.com/science/article/abs/pii/S1051200425006840)).
  These need model training on dysarthric data, which 15 TORGO speakers cannot
  support without overfitting, so they stay out of scope.

## 2. Candidates that need no training

| Technique | What it does | Evidence | Fit for Timbre |
|---|---|---|---|
| Cohort score normalization (AS-norm) | Compares a trial score with the scores of the most similar other voices, on both the template and the take side, and standardizes it | Standard in challenge systems; the trainable variant reports 4.1% relative EER and 10.6% relative minDCF gains over plain AS-norm with ECAPA ([TAS-norm](https://arxiv.org/abs/2504.04512); [adaptive data normalization](https://www.isca-archive.org/interspeech_2023/cumani23_interspeech.pdf)) | Targets false accepts directly: a take that resembles many voices earns less |
| Silence trimming | Drops frames far below the loudest frame before embedding | Speech activity detection matters most for short, noisy segments ([far-field short utterances](https://arxiv.org/html/2002.06033v1)) | Dysarthric takes contain long pauses and breaths that dilute the embedding |
| Multi-crop embedding | Embeds overlapping crops and averages them | Ten-crop averaging is standard VoxCeleb practice ([VoxCeleb2](https://arxiv.org/pdf/1806.05622), [graph attention back-end](https://arxiv.org/abs/2010.11543)); segment aggregation reports about 45% relative gain on 1 s tests ([segment aggregation](https://arxiv.org/pdf/2005.03329)) | Takes are short (1.2 s minimum) |
| Per-sample enrollment scoring | Scores a take against each enrollment sample (top-k mean) instead of only the centroid | Multi-enrollment back-ends show score-level and embedding-level aggregation trade off ([joint encoder and back-end](https://arxiv.org/pdf/2209.00485)) | A variable speaker's five takes may not average into one good point |
| In-domain mean subtraction | Subtracts the mean embedding of in-domain audio and renormalizes | Unsupervised domain adaptation in embedding space ([adaptive mean normalization](https://www.researchgate.net/publication/345142046_Adaptive_Mean_Normalization_for_Unsupervised_Adaptation_of_Speaker_Embeddings); [CORAL++](https://arxiv.org/pdf/2202.01092)) | ECAPA was trained on celebrity interview speech, not atypical speech |

## 3. Candidates parked

- **Quality-measure calibration** (logistic regression on score, duration,
  embedding norm): standard for mixed durations
  ([QMF](https://www.researchgate.net/publication/260695687_Quality_Measure_Functions_for_Calibration_of_Speaker_Recognition_Systems_in_Various_Duration_Conditions);
  [uncertainty-aware back-end](https://arxiv.org/html/2609.01221)). Needs more
  labeled trials than our 4 development speakers provide.
- **Stronger or fused embedding models**: VoxCeleb1-O EER of CAM++ 0.65%,
  ERes2NetV2 0.61% ([3D-Speaker](https://arxiv.org/html/2403.19971v3),
  [CAM++](https://arxiv.org/pdf/2303.00332)), WavLM-ECAPA 0.39%
  ([overview](https://www.emergentmind.com/topics/wavlm-ecapa-tdnn-architecture)),
  versus about 0.8% for the SpeechBrain ECAPA we use. A new dependency and a
  large download; plan Phase 4, only if the cheap options leave a gap.
- **Spoofing countermeasures** (synthetic or converted voices): AASIST family
  and spoofing-aware verification ([SASV 2022](https://arxiv.org/pdf/2201.10283),
  [AASIST3](https://arxiv.org/html/2408.17352)). A separate false-accept threat
  from the replay check we already run; plan Phase 5.

## 4. How we decide (no tuning on evaluation speakers)

`make variants` runs every candidate on the Phase 8 trials (identical
recordings, seed, and probes). Parameters and the winning configuration are
chosen on the 4 development speakers only; the 11 evaluation speakers are then
scored once. For each configuration, the margin is set on development speakers
so their false-reject rate matches the live policy's, which makes
false-accept rates comparable across score scales. A configuration ships only
if, on evaluation speakers, it lowers false accepts for both groups and does
not raise dysarthric false rejects by more than `VARIANT_FRR_BUDGET`. Results
and the decision are recorded in ADR 7.

## 5. Results (2026-09-26, ADR 7)

None of the cheap candidates was adopted. On this corpus:

- No configuration improved dysarthric separability: the plain embedding with
  centroid scoring kept the best dysarthric EER (8.75%).
- Every configuration that lowered false accepts for both groups did so by
  raising dysarthric false rejects 10 to 15 points, the trade the project
  exists to avoid.
- Silence trimming hurt dysarthric speakers consistently.
- Development speakers could not choose reliably: with 4 of them, the cohort
  for AS-norm and mean subtraction overlaps the development impostors, which
  flatters those methods (disclosed in ADR 7).

**Candidate encoders (ADR 8, `make models`).** The development pick
(ResNet221) halved false accepts but raised dysarthric false rejects 9 points,
so nothing was adopted. Post hoc, fusing ECAPA with a second encoder lowered
EER for both groups in three of four pairings (for example ECAPA + ResNet34:
control 6.60% to 5.15%, dysarthric 8.75% to 5.67%). That is a lead to confirm
on independent data, not a result we can claim.

What would move the needle, in order: a larger development cohort from another
corpus (so selection is trustworthy), then a stronger or second embedding model
(plan Phase 4). Full table: `docs/variants_results.md` after `make variants`.
