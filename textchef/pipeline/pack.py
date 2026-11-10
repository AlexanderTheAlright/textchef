"""Step 5: pack the index the server reads.

PCA to cfg.dims, then int8. Texts and phrases go through the same fitted PCA
and the same quantization scale, or queries and documents would land in
different spaces.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from textchef.config import Config

FIT_SAMPLE = 50000
MAX_LEVELS = 1000        # facet values listed per categorical facet


def facet_summary(rows: pd.DataFrame, cfg: Config) -> dict:
    out = {}
    if "group" in rows.columns:
        out["group"] = _categorical(rows["group"], cfg.group_label, contrast=True)
    for f in cfg.facets:
        col = rows[f"f_{f.column}"]
        if f.type == "categorical":
            out[f.column] = _categorical(col, f.label, f.contrast)
        else:
            present = col.dropna()
            out[f.column] = {
                "label": f.label, "type": f.type, "contrast": f.contrast,
                "coverage": round(float(col.notna().mean()), 4),
                "min": _plain(present.min()) if len(present) else None,
                "max": _plain(present.max()) if len(present) else None,
            }
    return out


def _categorical(col: pd.Series, label: str, contrast: bool) -> dict:
    vc = col.dropna().astype(str).value_counts()
    return {"label": label, "type": "categorical", "contrast": contrast,
            "coverage": round(float(col.notna().mean()), 4), "n_levels": int(len(vc)),
            "values": [{"v": str(k), "n": int(n)} for k, n in vc.head(MAX_LEVELS).items()]}


def _plain(v):
    return v if isinstance(v, str) else float(v)


def run(cfg: Config) -> dict:
    work, out = cfg.work_dir, cfg.index_dir
    out.mkdir(parents=True, exist_ok=True)
    emb = np.load(work / "emb_unique.f16.npy").astype(np.float32)
    pemb = np.load(work / "emb_phrase.f16.npy").astype(np.float32)
    rows = pd.read_parquet(work / "topics.parquet")
    phrases = pd.read_parquet(work / "phrases.parquet")
    meta = json.loads((work / "topic_meta.json").read_text())
    xy = np.load(work / "xy.f16.npy")

    rng = np.random.default_rng(42)
    dims = min(cfg.dims, emb.shape[1], len(emb) - 1)
    fit = rng.choice(len(emb), size=min(FIT_SAMPLE, len(emb)), replace=False)
    pca = PCA(n_components=dims, svd_solver="randomized", random_state=42).fit(emb[fit])

    def project(a: np.ndarray) -> np.ndarray:
        p = pca.transform(a)
        return p / np.clip(np.linalg.norm(p, axis=1, keepdims=True), 1e-9, None)

    rp, pp = project(emb), project(pemb)
    scale = float(max(np.abs(rp).max(), np.abs(pp).max()))

    def quantize(a: np.ndarray) -> np.ndarray:
        return np.clip(np.round(a * (127.0 / scale)), -127, 127).astype(np.int8)

    rq, pq = quantize(rp), quantize(pp)

    # quantization must not reorder neighbours
    probe = rng.choice(len(rp), min(200, len(rp)), replace=False)
    ref = rp[:20000]
    exact = rp[probe] @ ref.T
    approx = rq[probe].astype(np.float32) @ rq[:20000].astype(np.float32).T
    top = min(10, len(ref))
    agree = float(np.mean([
        len(set(np.argsort(-exact[i])[:top]) & set(np.argsort(-approx[i])[:top])) / top
        for i in range(len(probe))]))

    np.save(out / "text.i8.npy", rq)
    np.save(out / "phrase.i8.npy", pq)
    np.save(out / "xy.f16.npy", xy.astype(np.float16))
    rows.to_parquet(out / "rows.parquet", index=False, compression="zstd")
    phrases.to_parquet(out / "phrases.parquet", index=False, compression="zstd")
    (out / "topics.json").write_text(json.dumps(meta))
    (out / "facets.json").write_text(json.dumps(facet_summary(rows, cfg)))

    manifest = {
        "model": cfg.model,
        "dims_raw": int(emb.shape[1]),
        "dims": int(dims),
        "scale": scale,
        "variance_retained": float(pca.explained_variance_ratio_.sum()),
        "neighbour_agreement_top10": agree,
        "n_rows": int(len(rows)),
        "n_unique": int(emb.shape[0]),
        "n_phrases": int(len(phrases)),
        "n_topics": int(meta["n_topics"]),
        "duplicates_merged": json.loads((work / "dedupe.json").read_text()),
        "has_id": "id" in rows.columns,
        "has_group": "group" in rows.columns,
        "text_hash": hashlib.sha1("\x1f".join(rows["text"]).encode()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"pack: {len(rows):,} rows -> {out}  (PCA {emb.shape[1]}->{dims}, "
          f"top-10 agreement {agree:.0%})")
    return manifest
