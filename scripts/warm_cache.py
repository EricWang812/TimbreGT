"""Download the ECAPA model and the TORGO corpus once, on good wifi.

Usage: python -m scripts.warm_cache

Idempotent: files already present are skipped by huggingface_hub. Download
only; nothing here loads the model (that happens in ml/encoder.py only).
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import snapshot_download

from ml.constants import ECAPA_DIR, ECAPA_REPO, REPO_ROOT, TORGO_REPO, TORGO_SUBDIR


def dir_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    data_dir = (REPO_ROOT / os.environ.get("DATA_DIR", "./data")).resolve()
    torgo_dir = data_dir / TORGO_SUBDIR

    print(f"ECAPA -> {ECAPA_DIR}", flush=True)
    snapshot_download(repo_id=ECAPA_REPO, local_dir=ECAPA_DIR)
    print(f"ECAPA done, {dir_size_mb(ECAPA_DIR):.0f} MB", flush=True)

    print(f"TORGO -> {torgo_dir} (about 1.6 GB)", flush=True)
    snapshot_download(repo_id=TORGO_REPO, repo_type="dataset", local_dir=torgo_dir)
    print(f"TORGO done, {dir_size_mb(torgo_dir):.0f} MB", flush=True)


if __name__ == "__main__":
    main()
