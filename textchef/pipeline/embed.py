"""Step 2: embed the distinct texts.

No prompt prefix on either side: the server builds a query vector from phrase
embeddings (step 4), so texts and phrases must sit in one symmetric space.

Model "hashing" is a small offline embedder (hashed word and character
n-grams through a fixed random projection). It needs no download and no GPU;
the tests use it.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from textchef.config import Config
from textchef.pipeline.load import unique_texts
from textchef.pipeline.pacing import GpuBudget

SHARD = 2048            # texts per shard file; a stopped run loses at most one
HASH_DIMS = 256


def pick_device(device: str, model: str = "") -> str:
    if model == "hashing":
        return "cpu"            # no neural model, nothing for a GPU to do
    if device != "auto":
        return device
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class HashingEmbedder:
    def __init__(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer
        self.words = HashingVectorizer(n_features=4096, ngram_range=(1, 2), norm="l2",
                                       alternate_sign=False, stop_words="english")
        self.chars = HashingVectorizer(n_features=4096, analyzer="char_wb", ngram_range=(3, 4),
                                       norm="l2", alternate_sign=False)
        self.proj = np.random.default_rng(42).standard_normal((8192, HASH_DIMS)).astype(np.float32)

    def encode(self, texts: list[str]) -> np.ndarray:
        from scipy.sparse import hstack
        x = hstack([self.words.transform(texts), 0.5 * self.chars.transform(texts)]).tocsr()
        v = np.asarray(x @ self.proj, dtype=np.float32)
        return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)


class ModelEmbedder:
    def __init__(self, cfg: Config, device: str) -> None:
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(cfg.model, device=device)
        self.model.max_seq_length = cfg.max_seq_length
        self.batch_size = cfg.batch_size

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)


def make_embedder(cfg: Config, device: str):
    return HashingEmbedder() if cfg.model == "hashing" else ModelEmbedder(cfg, device)


def _batches(texts: list[str], max_items: int, max_chars: int) -> list[np.ndarray]:
    """Index batches of similar-length texts, bounded by item count and by
    total characters, so one forward pass never grows with document length."""
    order = np.argsort([len(t) for t in texts])
    out, cur, chars = [], [], 0
    for i in order:
        n = min(len(texts[i]), 2000)
        if cur and (len(cur) >= max_items or chars + n > max_chars):
            out.append(np.array(cur))
            cur, chars = [], 0
        cur.append(int(i))
        chars += n
    if cur:
        out.append(np.array(cur))
    return out


def encode_paced(embedder, texts: list[str], cfg: Config, device: str, label: str) -> np.ndarray:
    """Encode in batches under GpuBudget: on CUDA each batch waits for
    GPU_RESERVE_MB of free memory (wait_for_headroom) and is followed by a
    pause set by GPU_DUTY."""
    budget = GpuBudget(enabled=(device == "cuda"))
    max_items = cfg.batch_size * 8
    out = None
    t0, done = time.time(), 0
    for idx in _batches(texts, max_items, max_chars=max_items * 600):
        with budget:
            vec = embedder.encode([texts[i] for i in idx])
        if out is None:
            out = np.zeros((len(texts), vec.shape[1]), np.float32)
        out[idx] = vec
        done += len(idx)
        if done % (max_items * 10) < len(idx):
            print(f"  {label}: {done:,}/{len(texts):,} {done / max(time.time() - t0, 1e-6):.0f}/s",
                  flush=True)
    if device == "cuda":
        print(f"  {label}: {budget.report()}")
    return out


def _save_atomic(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_suffix(".tmp.npy")
    np.save(tmp, arr)
    os.replace(tmp, path)


def run(cfg: Config, device: str = "auto") -> np.ndarray:
    device = pick_device(device, cfg.model)
    rows = pd.read_parquet(cfg.work_dir / "rows.parquet")
    texts = unique_texts(rows)
    # the folder name carries the model and the texts, so stale shards are never reused
    key = hashlib.sha1("\x1f".join([cfg.model, str(cfg.max_seq_length), *texts]).encode()).hexdigest()[:10]
    shard_dir = cfg.work_dir / f"emb_shards_{key}"
    shard_dir.mkdir(parents=True, exist_ok=True)
    print(f"embed: {len(texts):,} texts with {cfg.model} on {device}")

    embedder = None
    parts = []
    for n, start in enumerate(range(0, len(texts), SHARD)):
        path = shard_dir / f"shard_{n:05d}.npy"
        chunk = texts[start:start + SHARD]
        if path.exists() and len(np.load(path, mmap_mode="r")) == len(chunk):
            parts.append(np.load(path))
            continue
        embedder = embedder or make_embedder(cfg, device)
        vec = encode_paced(embedder, chunk, cfg, device, f"shard {n}").astype(np.float16)
        _save_atomic(path, vec)
        parts.append(vec)
    emb = np.concatenate(parts)
    _save_atomic(cfg.work_dir / "emb_unique.f16.npy", emb)
    print(f"embed: saved {emb.shape}")
    return emb


if __name__ == "__main__":
    # python textchef/pipeline/embed.py CONFIG [DEVICE]: this step alone, for GPU job launchers
    import sys

    from textchef.config import load_config
    run(load_config(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "auto")
