"""Download shopping-only Whisper small before the demo. Never used by issuer."""
from huggingface_hub import snapshot_download
from api.config import ASR_MODEL_DIR

if __name__ == "__main__":
    snapshot_download("Systran/faster-whisper-small", local_dir=ASR_MODEL_DIR)
    print(f"Shopping ASR cached in {ASR_MODEL_DIR}")
