from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from textchef.config import ConfigError, load_config


def test_index_files_and_shapes(cfg):
    d = cfg.index_dir
    manifest = json.loads((d / "manifest.json").read_text())
    rows = pd.read_parquet(d / "rows.parquet")
    vec = np.load(d / "text.i8.npy")
    phrase = np.load(d / "phrase.i8.npy")
    xy = np.load(d / "xy.f16.npy")
    phrases = pd.read_parquet(d / "phrases.parquet")
    topics = json.loads((d / "topics.json").read_text())
    facets = json.loads((d / "facets.json").read_text())

    assert 150 <= len(rows) <= 200
    assert manifest["n_rows"] == len(rows)
    assert vec.dtype == np.int8 and vec.shape == (rows["uniq"].nunique(), manifest["dims"])
    assert rows["url"].str.startswith("https://").all()
    assert phrase.dtype == np.int8 and phrase.shape == (len(phrases), manifest["dims"])
    assert xy.shape == (len(vec), 2)
    assert manifest["dims"] <= 64
    assert {"text", "uniq", "topic", "id", "group", "url", "credit", "credit_url", "f_post_type", "f_date",
            "f_year", "f_score"} <= set(rows.columns)
    assert topics["n_topics"] == len(topics["topics"]) >= 2
    assert all(t["label"] for t in topics["topics"])
    assert rows["topic"].max() == topics["n_topics"] - 1
    assert set(facets) == {"group", "post_type", "date", "year", "score"}
    assert facets["year"]["type"] == "numeric" and facets["post_type"]["values"]
    assert set(manifest["duplicates_merged"]) == {"exact", "near"}


def test_config_rejects_paths_outside_its_folder(project):
    for line in ('path = "../outside.csv"', 'path = "/etc/passwd"'):
        bad = project / "bad.toml"
        bad.write_text(f'[corpus]\n{line}\ntext = "text"\n')
        with pytest.raises(ConfigError):
            load_config(bad)
    bad.write_text('data_dir = "../../elsewhere"\n[corpus]\npath = "sample.csv"\ntext = "text"\n')
    with pytest.raises(ConfigError):
        load_config(bad)
    bad.unlink()


def test_duplicates_are_grouped():
    from textchef.pipeline.dedupe import group_duplicates
    base = " ".join(f"word{i}" for i in range(80)) + " "
    texts = [base, base.upper() + "!", base + "it happened twice", "a different text about pay and notice periods"]
    groups, n_exact, n_near = group_duplicates(texts)
    assert groups[0] == groups[1] == groups[2] != groups[3]
    assert (n_exact, n_near) == (1, 1)
