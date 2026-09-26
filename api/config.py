"""Merchant settings. The merchant cannot import issuer/config.py (separate
services), so its own tunables live here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from ml.constants import REPO_ROOT, WHISPER_DIR

load_dotenv(REPO_ROOT / ".env")

MERCHANT_ID = "seaside-market"

# --- Shopping intent (docs/ALGORITHM.md §10) ---
INTENT_CONFIDENCE_MIN = 0.7
KEYWORD_MIN_QUERY_COVERAGE = 0.5  # keyword fallback: a product must explain MORE than half the content words
FILLER_WORDS = frozenset("a an the some please i id want would like to get buy add me my of and can you".split())
ASR_MODEL_DIR = WHISPER_DIR
ASR_BEAM_SIZE = 5
ASR_NBEST = 3
ASR_MAX_TOKENS = 128
ASR_NO_SPEECH_MAX = 0.6
SHOP_SAMPLE_RATE = 16000
SHOP_AUDIO_MAX_SECONDS = 10
SHOP_AUDIO_MAX_BYTES = 400000
SHOP_TEXT_MAX = 300
LLM_TIMEOUT_S = 8.0
LLM_MAX_TOKENS = 256
LLM_MODELS = {"anthropic": "claude-haiku-4-5", "gemini": "gemini-2.5-flash-lite"}

# --- Additive OpenAI agentic shopping ---
OPENAI_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
OPENAI_INTENT_MODEL = "gpt-4.1-mini"
OPENAI_TIMEOUT_S = 20.0

# --- Cart pricing (flat demo rates, not real tax logic) ---
TAX_RATE_BPS = 400               # basis points: 400 = 4.00%
SHIPPING_CENTS = 599
FREE_SHIPPING_MIN_CENTS = 3500   # subtotal at or above this ships free
MAX_QUANTITY = 20                # per line
MAX_CART_LINES = 50

# --- Issuer calls (server to server) ---
ISSUER_TIMEOUT_S = 10.0

# --- Storage ---
DB_BUSY_TIMEOUT_S = 5.0


def _require_choice(name: str, value: str, choices: set[str]) -> str:
    if value not in choices:
        raise RuntimeError(f"{name}={value!r} in .env; expected one of {sorted(choices)}")
    return value


def _repo_path(value: str) -> Path:
    return (REPO_ROOT / value).resolve()


# --- Environment (§4.3) ---
MERCHANT_PORT = int(os.environ.get("MERCHANT_PORT", "8000"))
MERCHANT_DB = _repo_path(os.environ.get("MERCHANT_DB", "./merchant.db"))
# Server-to-server call to the issuer. 127.0.0.1 avoids an IPv6 (::1) miss on
# Windows; browser-facing origins still use "localhost" (docs/CONTEXT.md §12).
ISSUER_URL = f"http://127.0.0.1:{int(os.environ.get('ISSUER_PORT', '8100'))}"
WEB_ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "http://localhost:5173")
LLM_PROVIDER = _require_choice(
    "LLM_PROVIDER", os.environ.get("LLM_PROVIDER", "anthropic"), {"anthropic", "gemini"}
)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
