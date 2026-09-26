"""Candidate speaker encoders for the model comparison (docs/RESEARCH.md §3, ADR 8).

Evaluation only. The issuer loads ml/encoder.py and nothing else (§6); a
candidate moves there only if ADR 8 adopts it. Models load lazily on first
use, from models/candidates/ (python -m scripts.warm_candidates), never from
the network. Speaker identity only: nothing here transcribes (§2.1).

WeSpeaker ONNX models take 80-bin Kaldi fbank features with per-utterance
mean normalization, computed with the pinned torchaudio; onnxruntime is
already installed as a faster-whisper dependency.
"""
from functools import lru_cache

import numpy as np
import torch
import torchaudio

from ml.constants import ECAPA_SAMPLE_RATE, REPO_ROOT

MODELS_DIR = REPO_ROOT / "models" / "candidates"
ONNX_MODELS = {
    "campplus": ("Wespeaker/wespeaker-voxceleb-campplus", "voxceleb_CAM++.onnx", "config.yaml"),
    "resnet221": ("Wespeaker/wespeaker-voxceleb-resnet221-LM", "voxceleb_resnet221_LM.onnx", "voxceleb_resnet221_LM.yaml"),
    "resnet34": ("Wespeaker/wespeaker-voxceleb-resnet34-LM", "voxceleb_resnet34_LM.onnx", "config.yaml"),
}
SB_RESNET_REPO = "speechbrain/spkrec-resnet-voxceleb"
FBANK = {"num_mel_bins": 80, "frame_length": 25, "frame_shift": 10, "dither": 0.0,
         "sample_frequency": ECAPA_SAMPLE_RATE, "window_type": "hamming"}


def _unit(v):
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / np.linalg.norm(v)


def _missing(path):
    raise RuntimeError(f"Candidate model missing at {path}. Run: python -m scripts.warm_candidates")


@lru_cache(maxsize=None)
def _onnx(name):
    import onnxruntime
    path = MODELS_DIR / name / ONNX_MODELS[name][1]
    if not path.exists():
        _missing(path)
    options = onnxruntime.SessionOptions()
    options.log_severity_level = 3
    return onnxruntime.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def fbank(waveform):
    """WeSpeaker front end: int16-scaled audio, 80 log-mel bins, mean-normalized over time."""
    audio = torch.from_numpy(np.asarray(waveform, dtype=np.float32)).unsqueeze(0) * (1 << 15)
    feats = torchaudio.compliance.kaldi.fbank(audio, **FBANK)
    return (feats - feats.mean(dim=0)).unsqueeze(0).numpy()


def embed_onnx(name, waveform):
    session = _onnx(name)
    return _unit(session.run(None, {session.get_inputs()[0].name: fbank(waveform)})[0][0])


@lru_cache(maxsize=1)
def _sb_resnet():
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy
    path = MODELS_DIR / "sb_resnet"
    if not (path / "embedding_model.ckpt").exists():
        _missing(path)
    model = EncoderClassifier.from_hparams(source=str(path), savedir=str(path),
                                           local_strategy=LocalStrategy.NO_LINK, run_opts={"device": "cpu"})
    model.eval()
    return model


def embed_sb_resnet(waveform):
    peak = float(np.max(np.abs(waveform)))
    if peak == 0:
        raise ValueError("silent recording cannot be embedded")
    with torch.no_grad():
        out = _sb_resnet().encode_batch(torch.from_numpy((waveform / peak).astype(np.float32)).unsqueeze(0))
    return _unit(out.numpy())


EMBEDDERS = {name: (lambda w, n=name: embed_onnx(n, w)) for name in ONNX_MODELS} | {"sb_resnet": embed_sb_resnet}
