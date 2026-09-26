"""Model and corpus locations. Pure constants, no state, safe to import anywhere.

Kept separate from ml/encoder.py because importing encoder.py loads the ECAPA
model, and scripts that only need a path must not pay that cost.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ECAPA_REPO = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_DIR = REPO_ROOT / "models" / "ecapa"
ECAPA_SAMPLE_RATE = 16000        # the model was trained on 16 kHz audio
ECAPA_EMBEDDING_DIM = 192

# Whisper small: merchant shopping intent and the demo baseline only, never identity.
WHISPER_DIR = REPO_ROOT / "models" / "whisper-small"

TORGO_REPO = "abnerh/TORGO-database"
TORGO_SUBDIR = "torgo_hf"
