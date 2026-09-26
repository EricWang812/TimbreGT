# Pre-registration: ECAPA + ResNet34 fusion on EasyCall

Part of the Timbre instruction set. Written and committed on 2026-09-26 before
any EasyCall audio was downloaded or scored, so that nothing below can be
adjusted after seeing results. Follows ADR 8. Style rule: no em dashes.

## Why

On TORGO, fusing ECAPA with a second encoder looked better after the fact
(ADR 8), but those numbers came from the evaluation speakers the protocol
forbids choosing on. The only honest test is data the configuration was not
chosen on.

## Frozen configurations (no others will be considered for adoption)

- **R (reference, live):** ECAPA (`ml/encoder.py`), centroid, held-out spread
  (ADR 3), threshold `max(GLOBAL_FLOOR, spread - margin)`, floor 0.45.
- **F (candidate):** equal-weight fusion of ECAPA and WeSpeaker ResNet34-LM
  (cosine of concatenated unit vectors, equal to the mean of the two cosines),
  same scorer, same floor. Encoders exactly as in `ml/candidate_encoders.py`
  at this commit.

## Data

- EasyCall corpus (Turrisi et al., Interspeech 2021), via the
  `changelinglab/easycall-dysarthria` Hugging Face copy, CC BY-NC 2.0,
  non-commercial evaluation only, kept under gitignored `data/`, never
  redistributed. Italian command speech; 21 healthy and 26 dysarthric
  speakers according to the dataset card.
- All splits pooled; speaker identity from the `speaker` field, group from
  `dysarthria_severity` (healthy versus any severity). Session from the
  filename if encoded, otherwise treated as unknown and disclosed.
- Quality filter: the live `check_recording` (duration and level), unchanged.
  No corpus recording is altered, and no speech is simulated.

## Speaker split

One third of each group (at least one speaker), by SHA-256 order of
`"20260925:" + speaker`, is the calibration cohort; the rest are evaluation
speakers. Same rule as ADR 6.

## Protocol P1 (primary; mirrors the live product)

Per speaker: among commands (normalized `text`) with at least 6 usable takes,
take the one with the most takes, ties broken by SHA-256 order of the command
text with the seed. Enrollment: 5 takes of that command, from one session when
sessions are known and one session has 5; probes: the remaining takes of that
command, at most 40, chosen by seeded filename order. A speaker with no such
command is excluded and counted. Impostor trials for a claimed speaker: every
other speaker's probes in the same cohort. Selection never looks at scores.

Protocol P2 (secondary, reported only): the TORGO text-independent selection
(`ml.evaluate.select_trials`, 5 enrollment takes, up to 40 probes).

## Calibration and decision

- For each of R and F, the margin is the strictest value at which the
  calibration cohort's pooled FRR is at or below the FRR that R achieves with
  the live margin (0.12) on the same cohort (`ml.variants.match_margin`).
- On P1 evaluation speakers, **F is adopted only if all three hold:**
  1. EER is lower than R's for both groups;
  2. FAR at the calibrated margin is lower than R's for both groups;
  3. dysarthric FRR is at most R's plus 2 points (`VARIANT_FRR_BUDGET`).
- Results are reported whatever the outcome, with speaker and trial counts.
  If F fails, ECAPA stays alone and the fusion lead is closed for this corpus.
  No other configuration, margin, split, or protocol variant will be tried for
  an adoption decision on EasyCall.

## Known limitations, stated in advance

Different language from TORGO (Italian commands); a single corpus; trials are
correlated within speakers; severity labels are coarse. A pass is evidence
that the fusion generalizes beyond TORGO, not a population-level claim.

## Amendment 1 (2026-09-26, before any scoring)

Made after downloading EasyCall and reading only metadata (filenames,
speakers, severity labels, command counts, durations, levels). No embedding or
score had been computed. The frozen configurations, split rule, calibration,
and adoption rule above are unchanged.

1. **Sample rate.** The audio is 8 kHz. Every take is upsampled to 16 kHz with
   `scipy.signal.resample_poly(x, 2, 1)` before the quality check and before
   both encoders, identically for R and F. Both therefore see narrowband
   (telephone-band) audio.
2. **Unlabeled speaker.** Speaker `f04` has severity `N/A`, so has no group,
   and is excluded. 54 speakers remain (24 severity 0, 30 severity 1 to 3).
3. **Protocol P1 uses every eligible command.** Each command has at most about
   6 takes per speaker, one per recording session, so the original rule gives
   a single genuine trial per speaker. Instead, every command with at least 6
   usable takes becomes its own template for that speaker (enrollment: 5
   takes by seeded filename order; probes: the remaining takes, which are
   always from other sessions). This matches the live product, where a
   person enrolls several sounds. Impostor trials for a template: every probe
   (any command) of every other speaker in the same cohort; a speaker's own
   other templates are never impostors. Measured eligibility under the live
   quality check: 23 control and 21 dysarthric speakers, 572 and 696
   templates, about 696 genuine probes per group before the split.
