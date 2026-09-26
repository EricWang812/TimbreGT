# Context: prior art, known issues, demo, glossary

Part of the Timbre instruction set. Read `CLAUDE.md` first.
**Read section "Prior art" before writing any README, pitch, or Devpost text.
Read "Known issues" before debugging anything that looks mysterious.**

Style rule: do not use em dashes in anything you write in this repo.

---

## 11. Prior art: know this cold

A judge may know this literature. Do not overclaim.

**Exists (academic).** Dysarthric speaker verification is a real subfield.
Salim et al. 2022 (MFCC plus CQCC features, duration-modification augmentation,
i-vector and x-vector models; reported EER improvements of 15.07% and 22.75%);
prosodic features plus out-of-domain augmentation (2023); MFCC and LFCC frame-
level fusion (2024); temporal discriminative bottleneck embeddings (2025). A
2015 paper already framed dysarthric speakers as excluded from speech-enabled
biometric solutions.

**Exists (commercial).** Text-independent and passive voice biometrics are
standard practice, with deployments at JPMorgan Chase, Wells Fargo, and TD Bank,
and vendors such as Daon. Passive enrollment rates are reported above 95%, and
some institutions may auto-enroll customers where call-recording consent already
exists. Industry guidance already recommends refreshing voiceprints over time as
voices change.

**Does not exist, as far as we can find.** Any shipped deployment of
dysarthria-aware verification. Any published issuer accommodation path for
people who cannot pass voice authentication. Personal thresholds derived from a
speaker's own variability. Template adaptation for progressive neurological
change. Any of this wired into a payment flow.

**Correct framing for the pitch:** "Four research groups showed this works. None
of it shipped. Meanwhile banks are passively enrolling these users by default.
We built the deployment."

---

## 12. Known issues, caveats, and workarounds

| Issue | Impact | Workaround |
|---|---|---|
| Visa Intelligent Commerce is gated | No VIC APIs during the event | Stripe plus provider interface plus mapping doc (§9) |
| Two-way SSL setup is fiddly | Can consume 6 hours | Do it pre-event; use VDC Playground first |
| Venue wifi | Model and corpus downloads fail | `scripts/warm_cache.py` before arrival; everything local |
| Expo hall noise | Verification scores drop | Headset microphone; test in a loud room on Saturday, not Sunday |
| TORGO has about 15 speakers | Noisy EER estimate | Report as preliminary; print exact N on every chart |
| TORGO has two microphone types | Measures channel, not speaker | Filter to `headMic` only |
| Replay attack on a recorded hum | Judge will ask | All three defenses in §7.5 |
| Non-speech sounds carry low entropy | Security objection | Position as one factor alongside device possession, never standalone |
| ECAPA was trained on typical speech | Degraded scores on dysarthric audio | This is the measured gap. Report it honestly: it is the problem statement. |
| First ECAPA load is slow | Cold-start latency ruins the 2 s claim | Load at import in `ml/encoder.py`; add `/healthz` that confirms the model is resident; hit it before demoing |
| LLM latency is unpredictable | Would break the 2 s claim | The LLM is never in the verification path, only in shopping |
| WebAuthn requires a secure context | Passkey fallback fails | `localhost` is exempt, but the web origin (`:5173`) differs from the issuer origin (`:8100`). Set `WEBAUTHN_RP_ID=localhost` and `WEBAUTHN_ORIGIN=http://localhost:5173`, and validate against that origin server-side. Never demo from a LAN IP or `127.0.0.1` mixed with `localhost`. |
| SQLite write locks under concurrency | Sporadic 500s mid-demo | One writer per database; `check_same_thread=False`; keep transactions short |
| Sample-rate mismatch | Scores look like an identity failure | Assert 16000 Hz on both paths; never silently resample |
| Adaptation could be poisoned | Security objection | Confident-pass gate plus `MAX_DRIFT` clamp (§7.4) |
| Demo database drifts across rehearsals | Inconsistent scores on stage | `make reset` between full rehearsals |
| uvicorn `--reload` can hang on Windows | Log shows "Reloading..." with no "Started server process" after it; the old code keeps serving | The issuer now runs without `--reload` (it hung repeatedly after loading the speaker model): restart it by hand after any issuer or `ml/` edit. The merchant still reloads; if it hangs the same way, stop it and rerun `make api`. |
| Schema change with existing `.db` files | `CREATE TABLE IF NOT EXISTS` does not alter old tables; endpoints fail on missing columns | `make reset` after any change to a `SCHEMA` string (no migration framework, by design) |

---

---

## 16. Demo requirements (build toward this, not away from it)

Total 90 seconds. Rehearse at least five times, including the failure path.
Run `make reset` between full rehearsals.

1. **The wall (15 s).** Transcription-based baseline on dysarthric TORGO audio.
   It fails twice. Say: "In production, the next step is a phone call."
2. **The fix (20 s).** Same speaker, same audio, Timbre verifies in under two
   seconds. Show the score and the personal threshold on screen.
3. **The purchase (25 s).** A judge shops by voice, hears the spoken
   confirmation, approves, the token is charged, the receipt appears.
4. **The privacy proof (15 s).** Open devtools: the merchant received
   `{verified, transaction_id}` and nothing else.
5. **The drift (15 s).** Adaptation chart across simulated months, with and
   without adaptation.

Record a video of the full working flow in advance as insurance against wifi
failure at the table.

### Answers to have ready

- *Replay attack?* See §7.5, all three defenses.
- *Entropy of a hum versus a passphrase?* Lower. One factor among several, with
  passkey step-up above the amount tier. Do not oversell it.
- *Your FAR and FRR at that threshold?* Cite the actual operating point from
  `docs/eval_results.md`, not "it works."
- *Is not text-independent verification already articulation-agnostic?* Yes in
  principle, but the models are trained on typical speech and degrade on
  dysarthric speech, which is why the §11 papers exist, and the IVR layer in
  front of the biometric still demands intelligible digits.
- *How is this different from the research?* See §11. Deployment, personal
  thresholds, adaptation for progressive change, issuer-side privacy split.
- *Is this an app or a protocol?* Protocol. See §1.1. It ships as issuer and
  network infrastructure the way 3-D Secure does. The storefront on screen is a
  test harness proving a merchant integrates in a few lines and learns nothing
  about the user.
- *Why not integrate with a real store?* See §1.1. No merchant exposes a hook
  inside checkout, and intercepting one means touching live card fields.
  Building both sides is what lets us show the privacy boundary at all.
- *What if someone cannot enroll at all?* See §7.2. They are not locked out. The
  passkey path carries them, and we report the enrollment failure rather than
  hiding it.

---

## 17. Glossary

| Term | Meaning |
|---|---|
| **Dysarthria** | A motor speech disorder. Muscle control for speech is impaired; language and intelligence are not. |
| **ASR** | Automatic speech recognition. Turns audio into words. Used for shopping intent only. |
| **ASV** | Automatic speaker verification. Confirms identity from voice. What we build. |
| **ECAPA-TDNN** | The speaker-embedding model architecture we use, via SpeechBrain. |
| **Embedding** | A 192-dimensional vector representing a voice. Compared with cosine similarity. |
| **Centroid** | The averaged, re-normalized embedding of a user's enrollment samples for one sound label. |
| **Cohesion** | Mean pairwise cosine similarity across a user's enrollment samples. Measures enrollment quality. |
| **Spread** | Mean cosine of a user's samples to their own centroid. Drives the personal threshold. |
| **Drift** | How far the stored template has moved from its previous value after adaptation. |
| **EER** | Equal error rate. The threshold where false accepts equal false rejects. Lower is better. |
| **FAR / FRR** | False accept rate, false reject rate. |
| **PAN** | Primary account number, i.e. the card number. We never store one. |
| **Token / TokenRef** | An opaque reference standing in for a card. Safe to store. |
| **instruction_id** | UUID generated by the merchant at cart confirmation, binding verification to authorization. |
| **Step-up** | An additional verification demanded for higher-risk or higher-value transactions. |
| **IVR** | Interactive voice response. The phone menu that rejects our users today. |
| **TORGO** | The dysarthric speech corpus we evaluate on (Rudzicz et al., 2012). |
| **VIC** | Visa Intelligent Commerce, Visa's agentic-payments API suite. Gated. |
| **CIDI** | Georgia Tech's Center for Inclusive Design and Innovation. Potential user contact. |
