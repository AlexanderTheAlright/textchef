"""Step 4: the phrase index, which lets the server turn a typed query into a
vector without loading a model.

The corpus's own vocabulary (1-3 word phrases above a frequency floor) is
embedded with the same model. At query time the server finds the phrases a
query contains and takes their IDF-weighted mean.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

from textchef.config import Config
from textchef.pipeline.embed import encode_paced, make_embedder, pick_device

MAX_PHRASES = 40000


def _worth_keeping(p: str) -> bool:
    toks = p.split()
    if all(t in ENGLISH_STOP_WORDS for t in toks):
        return False
    return not (len(toks) == 1 and len(p) < 3)


def build_vocabulary(texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    min_df = 2 if len(texts) < 2000 else 5
    cv = CountVectorizer(ngram_range=(1, 3), min_df=min_df, lowercase=True,
                         token_pattern=r"(?u)\b[a-z][a-z]+\b", max_features=300000)
    x = cv.fit_transform(texts)
    vocab = np.array(cv.get_feature_names_out())
    df = np.asarray((x > 0).sum(0)).ravel()
    keep = np.array([_worth_keeping(p) for p in vocab])
    vocab, df = vocab[keep], df[keep]

    # most frequent first, but every single word stays: they are what people type
    sel = np.array([" " not in v for v in vocab])
    for i in np.argsort(-df):
        if sel.sum() >= MAX_PHRASES:
            break
        sel[i] = True
    return vocab[sel], df[sel]


def run(cfg: Config, device: str = "auto") -> pd.DataFrame:
    device = pick_device(device, cfg.model)
    rows = pd.read_parquet(cfg.work_dir / "rows.parquet")
    vocab, df = build_vocabulary(rows["text"].tolist())
    print(f"phrases: {len(vocab):,} phrases on {device}")

    emb = encode_paced(make_embedder(cfg, device), vocab.tolist(), cfg, device, "phrases")
    phrases = pd.DataFrame({"phrase": vocab, "df": df,
                            "idf": np.log(1.0 + len(rows) / np.clip(df, 1, None))})
    phrases.to_parquet(cfg.work_dir / "phrases.parquet", index=False)
    np.save(cfg.work_dir / "emb_phrase.f16.npy", emb.astype(np.float16))
    return phrases


if __name__ == "__main__":
    # python textchef/pipeline/phrases.py CONFIG [DEVICE]: this step alone, for GPU job launchers
    import sys

    from textchef.config import load_config
    run(load_config(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "auto")
