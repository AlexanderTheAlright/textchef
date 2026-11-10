"""Step 3: topics and the 2D map.

UMAP to 5 dimensions, HDBSCAN for density clusters, c-TF-IDF for the words
that set each cluster apart. Clustering runs on distinct texts; labels weight
by row frequency.
"""
from __future__ import annotations

import json
import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

from textchef.config import Config

RANDOM_STATE = 42
NOISE_FLOOR = 0.70      # cosine to the nearest centroid before a noise point joins it
MERGE_COS = 0.95        # centroids this parallel AND sharing words are one topic
WORD_JACCARD = 0.30
N_MACRO = 12
BOILERPLATE_DEPTH = 30  # a term among a topic's top 30 ...
BOILERPLATE_SHARE = 0.2 # ... in more than this share of topics is dropped from labels
EDGE_K = 4
EDGE_MIN = 0.35

# apostrophes are stripped before tokenizing, which leaves these behind
CONTRACTIONS = frozenset("""
didn didnt hasn hasnt doesn doesnt wasn wasnt couldn couldnt wouldn wouldnt isn
isnt aren arent shouldn shouldnt haven havent hadn hadnt weren werent cant wont
dont don im ive id youre theyre thats theres its
""".split())

_WORD = re.compile(r"[a-z]{3,}")


_POSSESSIVE = re.compile(r"['\u2019]s\b")


def _lower(s: str) -> str:
    """Lowercase; "boss's" becomes "boss" and "don't" becomes "dont"."""
    return _POSSESSIVE.sub("", s.lower()).replace("'", "").replace("\u2019", "")


def _unit(a: np.ndarray) -> np.ndarray:
    return a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-9, None)


def _centroids(emb: np.ndarray, lab: np.ndarray, n: int) -> np.ndarray:
    cent = np.vstack([emb[lab == k].mean(0) if (lab == k).any() else np.zeros(emb.shape[1])
                      for k in range(n)])
    return _unit(cent)


def reduce(emb: np.ndarray, n_components: int, min_dist: float) -> np.ndarray:
    from umap import UMAP
    n = len(emb)
    if n <= n_components + 2:
        return emb[:, :n_components].astype(np.float32)
    return UMAP(n_neighbors=min(15, n - 1), n_components=n_components, min_dist=min_dist,
                metric="cosine", random_state=RANDOM_STATE, verbose=False).fit_transform(emb)


def cluster(red: np.ndarray, emb: np.ndarray, min_cluster_size: int) -> np.ndarray:
    n = len(red)
    size = min_cluster_size or int(np.clip(n // 600, 5, 150))
    lab = HDBSCAN(min_cluster_size=size, min_samples=min(10, size),
                  cluster_selection_method="eom", copy=True).fit_predict(red)
    if lab.max() < 1:
        # too little density structure (tiny corpora): fall back to k-means
        k = int(np.clip(round(np.sqrt(n / 8)), 2, 12))
        return KMeans(n_clusters=min(k, n), n_init=4, random_state=RANDOM_STATE).fit_predict(emb)

    return lab


def rescue_noise(lab: np.ndarray, emb: np.ndarray) -> np.ndarray:
    """An unclustered text joins its nearest topic when it is close enough."""
    cent = _centroids(emb, lab, int(lab.max() + 1))
    noise = np.where(lab == -1)[0]
    if len(noise):
        sim = emb[noise] @ cent.T
        take = sim.max(1) >= NOISE_FLOOR
        lab[noise[take]] = sim.argmax(1)[take]
    return lab


def merge_near_duplicates(lab: np.ndarray, emb: np.ndarray, rows: pd.DataFrame,
                          stop: frozenset[str]) -> np.ndarray:
    n_topics = lab.max() + 1
    cent = _centroids(emb, lab, n_topics)
    row_topic = lab[rows["uniq"].to_numpy()]

    def top_words(k: int) -> set[str]:
        txt = " ".join(rows.loc[row_topic == k, "text"].head(400))
        counts = Counter(w for w in _WORD.findall(_lower(txt)) if w not in stop)
        return {w for w, _ in counts.most_common(15)}

    sim = cent @ cent.T
    np.fill_diagonal(sim, -1)
    parent = list(range(n_topics))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    words: dict[int, set[str]] = {}
    for a, b in np.argwhere(sim >= MERGE_COS):
        a, b = int(a), int(b)
        if a >= b:
            continue
        wa = words.setdefault(a, top_words(a))
        wb = words.setdefault(b, top_words(b))
        if len(wa & wb) / max(len(wa | wb), 1) >= WORD_JACCARD:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    roots = sorted({find(k) for k in range(n_topics)})
    remap = {r: i for i, r in enumerate(roots)}
    return np.array([remap[find(int(k))] if k >= 0 else -1 for k in lab])


def ctfidf_keywords(docs: list[str], stop: frozenset[str], top: int = 12) -> list[list[str]]:
    """Top words per document (one document per topic). idf uses each term's
    total count against the average topic length, as BERTopic defines it."""
    cv = CountVectorizer(stop_words=list(stop), ngram_range=(1, 2), max_features=60000,
                         token_pattern=r"(?u)\b[a-z][a-z]+\b", preprocessor=_lower)
    try:
        x = cv.fit_transform(docs)
    except ValueError:
        return [[] for _ in docs]
    vocab = np.array(cv.get_feature_names_out())
    doubled = np.array([len(set(v.split())) < len(v.split()) for v in vocab])    # "company company"
    x, vocab = x[:, ~doubled], vocab[~doubled]
    xa = np.asarray(x.todense(), dtype=np.float64)
    tf = xa / np.clip(xa.sum(1, keepdims=True), 1, None)
    score = tf * np.log(1.0 + (xa.sum() / xa.shape[0]) / np.clip(xa.sum(0), 1, None))
    # a term that ranks high in many topics is corpus boilerplate, not a label
    ranked = np.argsort(-score, axis=1)[:, :BOILERPLATE_DEPTH]
    if len(docs) >= 10:
        share = np.bincount(ranked.ravel(), minlength=len(vocab)) / len(docs)
        score[:, share > BOILERPLATE_SHARE] = 0.0
    out = []
    for k in range(len(docs)):
        best = np.argsort(-score[k])[:top]
        out.append([str(vocab[i]) for i in best if score[k, i] > 0])
    return out


def _stem(w: str) -> str:
    for suf in ("ments", "ment", "tions", "tion", "ings", "ing", "ers", "er",
                "ies", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def _same_family(a: str, b: str) -> bool:
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))


def label_words(words: list[str], n: int = 3) -> list[str]:
    """The first n keywords that are distinct ideas ("cost living, cost,
    inflation" keeps "cost living, inflation")."""
    chosen: list[str] = []
    stems: list[set[str]] = []
    for w in words:
        toks = list(dict.fromkeys(w.split()))
        st = {_stem(t) for t in toks}
        if any(_same_family(s, p) for prev in stems for s in st for p in prev):
            continue
        chosen.append(" ".join(toks))
        stems.append(st)
        if len(chosen) == n:
            break
    return chosen


def run(cfg: Config) -> dict:
    rows = pd.read_parquet(cfg.work_dir / "rows.parquet")
    emb = np.load(cfg.work_dir / "emb_unique.f16.npy").astype(np.float32)
    stop = frozenset(ENGLISH_STOP_WORDS) | CONTRACTIONS | frozenset(cfg.stopwords)

    # merge on the dense cores, before rescued texts pull every centroid
    # toward the corpus mean
    lab = cluster(reduce(emb, 5, 0.0), emb, cfg.min_cluster_size)
    lab = rescue_noise(merge_near_duplicates(lab, emb, rows, stop), emb)
    n_topics = int(lab.max() + 1)
    cent = _centroids(emb, lab, n_topics)
    xy = reduce(emb, 2, 0.12)

    rows["topic"] = lab[rows["uniq"].to_numpy()].astype(np.int32)
    docs = (rows.groupby("topic")["text"].apply(" ".join)
            .reindex(range(n_topics), fill_value="").tolist())
    keywords = ctfidf_keywords(docs, stop)

    # second-level groups over topic centroids; they colour the map
    macro = (KMeans(n_clusters=min(N_MACRO, n_topics), n_init=10,
                    random_state=RANDOM_STATE).fit_predict(cent)
             if n_topics > 1 else np.zeros(n_topics, int))

    sim = cent @ cent.T
    np.fill_diagonal(sim, -1)
    edges, seen = [], set()
    for a in range(n_topics):
        for b in np.argsort(-sim[a])[:EDGE_K]:
            pair = (min(a, int(b)), max(a, int(b)))
            if pair[0] == pair[1] or pair in seen or sim[pair] <= EDGE_MIN:
                continue
            seen.add(pair)
            edges.append({"a": pair[0], "b": pair[1], "w": round(float(sim[pair]), 4)})

    topics = []
    for k in range(n_topics):
        members = xy[lab == k]
        sub = rows[rows["topic"] == k]
        words = label_words(keywords[k])
        topics.append({
            "id": k,
            "label": ", ".join(words) if words else f"topic {k}",
            "keywords": keywords[k],
            "count": int(len(sub)),
            "macro": int(macro[k]),
            "x": float(members[:, 0].mean()) if len(members) else 0.0,
            "y": float(members[:, 1].mean()) if len(members) else 0.0,
            "groups": (sub["group"].value_counts().head(12).astype(int).to_dict()
                       if "group" in sub.columns else {}),
        })

    macro_labels = {}
    for g in sorted(set(macro.tolist())):
        members = sorted((t for t in topics if t["macro"] == g), key=lambda t: -t["count"])
        words = list(dict.fromkeys(w for t in members for w in t["keywords"][:4]))
        macro_labels[str(g)] = ", ".join(label_words(words))

    meta = {"n_topics": n_topics, "unassigned": int((rows["topic"] == -1).sum()),
            "topics": topics, "edges": edges, "macro_labels": macro_labels}
    (cfg.work_dir / "topic_meta.json").write_text(json.dumps(meta))
    rows.to_parquet(cfg.work_dir / "topics.parquet", index=False)
    np.save(cfg.work_dir / "xy.f16.npy", xy.astype(np.float16))
    print(f"topics: {n_topics} topics, {len(edges)} edges, "
          f"{meta['unassigned']:,} rows unassigned")
    return meta
