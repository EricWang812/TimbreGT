"""Download the candidate speaker encoders compared by make models (ADR 8).

Evaluation only: nothing here is loaded by the issuer. Run once on good wifi,
about 220 MB. Files land in models/candidates/ (gitignored).
"""
from huggingface_hub import hf_hub_download, snapshot_download

from ml.candidate_encoders import MODELS_DIR, ONNX_MODELS, SB_RESNET_REPO

if __name__ == "__main__":
    for name, (repo, filename, config_file) in ONNX_MODELS.items():
        for f in (filename, config_file):
            hf_hub_download(repo, f, local_dir=MODELS_DIR / name)
        print(f"{name}: cached", flush=True)
    snapshot_download(SB_RESNET_REPO, local_dir=MODELS_DIR / "sb_resnet",
                      allow_patterns=["*.ckpt", "hyperparams.yaml", "label_encoder.txt", "config.json"])
    print("sb_resnet: cached", flush=True)
