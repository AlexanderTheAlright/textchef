"""Step 1: read the corpus file into the row table every later step uses.

Output columns: text, uniq (index of the group of duplicate texts), id, url,
credit and group when configured, and one f_<column> per declared facet.
"""
from __future__ import annotations

import json

import pandas as pd

from textchef.config import Config, ConfigError
from textchef.pipeline.dedupe import group_duplicates


def read_corpus(cfg: Config) -> pd.DataFrame:
    if cfg.corpus_path.suffix.lower() == ".parquet":
        return pd.read_parquet(cfg.corpus_path)
    return pd.read_csv(cfg.corpus_path, dtype=str, keep_default_na=False)


def load_rows(cfg: Config) -> pd.DataFrame:
    src = read_corpus(cfg)
    wanted = [cfg.text, cfg.id, cfg.group, cfg.url, cfg.credit, cfg.credit_url] + [f.column for f in cfg.facets]
    missing = [c for c in wanted if c and c not in src.columns]
    if missing:
        raise ConfigError(f"columns not in corpus: {missing}")

    rows = pd.DataFrame()
    text = src[cfg.text].astype("string").fillna("").str.replace(r"\s+", " ", regex=True).str.strip()
    rows["text"] = text.astype(str)
    if cfg.id:
        rows["id"] = src[cfg.id].astype(str).to_numpy()
    # only web links are kept; anything else would be a script or file link in the UI
    for key, column in (("url", cfg.url), ("credit_url", cfg.credit_url)):
        if column:
            url = src[column].astype("string").str.strip()
            ok = url.str.match(r"^https?://[^\s<>\"']+$", na=False)
            rows[key] = url.where(ok).astype(object).to_numpy()
    if cfg.credit:
        rows["credit"] = _clean_category(src[cfg.credit]).to_numpy()
    if cfg.group:
        rows["group"] = _clean_category(src[cfg.group]).to_numpy()
    for f in cfg.facets:
        col = src[f.column]
        if f.type == "numeric":
            rows[f"f_{f.column}"] = pd.to_numeric(col, errors="coerce").astype("float64").to_numpy()
        elif f.type == "date":
            # stored as ISO days so range filters compare as strings or dates alike
            d = pd.to_datetime(col, errors="coerce", format="mixed")
            rows[f"f_{f.column}"] = d.dt.strftime("%Y-%m-%d").to_numpy()
        else:
            rows[f"f_{f.column}"] = _clean_category(col).to_numpy()

    keep = rows["text"].str.split().str.len() >= max(cfg.min_words, 1)
    rows = rows[keep].reset_index(drop=True)
    if rows.empty:
        raise ConfigError("no text left after the min_words floor")
    rows["uniq"], n_exact, n_near = group_duplicates(rows["text"].tolist())
    rows.attrs["dedupe"] = {"exact": n_exact, "near": n_near}
    return rows


def _clean_category(col: pd.Series) -> pd.Series:
    s = col.astype("string").str.strip()
    return s.mask(s.isin(["", "nan", "None", "NaN"])).astype(object).where(lambda x: x.notna(), None)


def unique_texts(rows: pd.DataFrame) -> list[str]:
    """Distinct texts in uniq order."""
    return rows.drop_duplicates("uniq").sort_values("uniq")["text"].tolist()


def run(cfg: Config) -> pd.DataFrame:
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(cfg)
    rows.to_parquet(cfg.work_dir / "rows.parquet", index=False)
    dedupe = rows.attrs["dedupe"]
    (cfg.work_dir / "dedupe.json").write_text(json.dumps(dedupe))
    print(f"load: {len(rows):,} rows, {rows['uniq'].nunique():,} distinct texts "
          f"({dedupe['exact']:,} exact and {dedupe['near']:,} near duplicates merged)")
    return rows
