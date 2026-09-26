"""Every tunable constant for the issuer lives here. No inline literals elsewhere.

Values and rationale: docs/ALGORITHM.md §7. Changing a §7 value requires a
CHANGELOG entry and an ADR in docs/DECISIONS.md.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from ml.constants import ECAPA_EMBEDDING_DIM, ECAPA_SAMPLE_RATE, REPO_ROOT

load_dotenv(REPO_ROOT / ".env")

# --- Audio and embedding (§7.1) ---
SAMPLE_RATE = ECAPA_SAMPLE_RATE  # 16000 Hz. Asserted, never silently resampled.
EMBEDDING_DIM = ECAPA_EMBEDDING_DIM

# --- Enrollment (§7.2) ---
LABELS_PER_USER = 3
RECORDINGS_PER_LABEL = 5
MIN_DURATION = 1.2               # seconds
MAX_DURATION = 10.0              # seconds; longer uploads are rejected, not truncated
MAX_LABEL_LENGTH = 32            # characters in a user-chosen sound label
MIN_RMS = 0.01
COHESION_MIN = 0.55
ENROLL_RERECORD_LIMIT = 1        # re-record attempts before accepting as low_confidence

# --- Personal thresholds (§7.3) ---
GLOBAL_FLOOR = 0.45
THRESHOLD_MARGIN = 0.12

# --- Adaptation (§7.4) ---
CONFIDENT_MARGIN = 0.10
ALPHA = 0.12
MAX_DRIFT = 0.05

# --- Liveness and anti-replay (§7.5) ---
CHALLENGE_LENGTH = 2             # labels required per approval, in order
REPLAY_CORR = 0.98

# --- Fallback (§7.6) ---
MAX_VOICE_ATTEMPTS = 2

# --- Passkeys (WebAuthn, §7.6) ---
WEBAUTHN_RP_NAME = "Your bank (Timbre demo)"
WEBAUTHN_CHALLENGE_TTL_SECONDS = 300   # a WebAuthn challenge is single-use and short-lived
WEBAUTHN_TIMEOUT_MS = 120000           # generous: the person may need time with their device

# --- Approval sessions ---
SESSION_TTL_SECONDS = 300
SESSION_MAX_EXTENSIONS = 10      # WCAG 2.2.1: the user can extend a time limit at least ten times
SESSION_ID_BYTES = 16            # secrets.token_urlsafe entropy; the id authorizes the widget

# --- Offline evaluation (no live verification parameter changes) ---
EVAL_SEED = 20260925
EVAL_MAX_PROBES = 40
# Demo baseline (ml/baseline_asr.py): a transcription check passes a take when its
# word error rate against the prompt is at or below this. Generous on purpose,
# so the baseline is not a strawman. Never used for live verification.
BASELINE_MAX_WER = 0.25

# --- Accuracy candidates (docs/RESEARCH.md). Evaluated by make variants;
# not used live unless ADR 7 adopts them. ---
TRIM_FRAME_S = 0.02              # frame length for silence detection
TRIM_HOP_S = 0.01
TRIM_DB_BELOW_PEAK = 35.0        # frames this far below the loudest frame are silence
TRIM_KEEP_CONTEXT_S = 0.10       # speech context kept around each voiced frame
TRIM_MIN_KEEP_S = 0.5            # never trim below this; keep the untrimmed take instead
CROP_S = 1.5                     # multi-crop embedding: crop length
CROP_HOP_S = 0.75
ASNORM_TOP_K_GRID = (10, 30, 60) # cohort sizes tried on development speakers only
TOP_K_SAMPLES = 2                # per-sample scoring: mean of the best k enrollment matches
VARIANT_FRR_BUDGET = 0.02        # a candidate may raise dysarthric FRR by at most this

# --- Storage ---
DB_BUSY_TIMEOUT_S = 5.0


def _require_choice(name: str, value: str, choices: set[str]) -> str:
    if value not in choices:
        raise RuntimeError(f"{name}={value!r} in .env; expected one of {sorted(choices)}")
    return value


def _repo_path(value: str) -> Path:
    return (REPO_ROOT / value).resolve()


# --- Environment (§4.3) ---
ISSUER_PORT = int(os.environ.get("ISSUER_PORT", "8100"))
ISSUER_DB = _repo_path(os.environ.get("ISSUER_DB", "./issuer.db"))
WEB_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "http://localhost:5173")
WEBAUTHN_RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
PAYMENT_PROVIDER = _require_choice(
    "PAYMENT_PROVIDER", os.environ.get("PAYMENT_PROVIDER", "stripe"), {"stripe", "visa"}
)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
VISA_CERT_PATH = os.environ.get("VISA_CERT_PATH", "")
VISA_KEY_PATH = os.environ.get("VISA_KEY_PATH", "")
VISA_USER_ID = os.environ.get("VISA_USER_ID", "")
VISA_PASSWORD = os.environ.get("VISA_PASSWORD", "")
# PAYMENT_PROVIDER=visa runs checkout through CyberSource, Visa's payment
# gateway, in its sandbox (issuer/payments/visa_provider.py, ADR 13). Keys come
# from the CyberSource Business Center (REST shared secret). Each demo
# cardholder's card is a CyberSource customer token created in that dashboard
# from a Visa test card, so no card number is ever in this repo (§2.2).
CYBERSOURCE_HOST = "apitest.cybersource.com"   # sandbox only; the provider refuses anything else
CYBERSOURCE_MERCHANT_ID = os.environ.get("CYBERSOURCE_MERCHANT_ID", "")
CYBERSOURCE_KEY_ID = os.environ.get("CYBERSOURCE_KEY_ID", "")
CYBERSOURCE_SECRET_KEY = os.environ.get("CYBERSOURCE_SECRET_KEY", "")
CYBERSOURCE_CUSTOMER_TOKENS = {
    "maya": os.environ.get("CYBERSOURCE_CUSTOMER_MAYA", ""),
    "jordan": os.environ.get("CYBERSOURCE_CUSTOMER_JORDAN", ""),
}
CYBERSOURCE_TIMEOUT_S = 20.0
