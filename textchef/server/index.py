"""The packed index in memory, and every lookup the API serves.

Everything expensive happened in the pipeline. A search here is a dictionary
lookup for the query's phrases plus one matrix multiply.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

from textchef.config import Config

_TOK = re.compile(r"[a-z]+")
_NORM = re.compile(r"[^a-z0-9]+")
_QUOTED = re.compile(r'^\s*["“”](.+)["“”]\s*$', re.S)

# a query phrase may not start on one of these, or "childcare is impossible"
# would anchor on "is impossible"
LEAD_STOP = frozenset("""
a an the is are was were be been being am do does did doing have has had having
of in on at to for with from by about into over under and or but if then than
that this these those it its as not no nor so such very too only just my your
our their his her him she he they them we you i me
""".split())

# function words never count as marking a group in a contrast
CONTRAST_STOP = LEAD_STOP | frozenset("""
will would could should can may might must there here what when where who how
why all any both each own same now also out up down off once more most other some
""".split())

LEX_SCORE = 0.6          # score of a full wording match, beside cosine scores
WORDING_WEIGHT = 0.5     # what a full wording match adds to cosine when ranking
CONTRAST_MIN_ROWS = 20
CONTRAST_PRIOR = 500.0
LIFT_MIN_ROWS = 10
MAP_POINTS = 5000


class ScopeError(ValueError):
    """A scope names a facet or value type the index does not have."""


def _norm_key(s: str) -> str:
    return _NORM.sub(" ", s.lower()).strip()


def _trigrams(s: str) -> set[str]:
    s = f"  {s} "
    return {s[i:i + 3] for i in range(len(s) - 2)}


class Index:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        d: Path = cfg.index_dir
        self.manifest = json.loads((d / "manifest.json").read_text())
        self.rows = pd.read_parquet(d / "rows.parquet")
        self.vec = np.load(d / "text.i8.npy").astype(np.float32)
        self.phrase_vec = np.load(d / "phrase.i8.npy").astype(np.float32)
        self.xy = np.load(d / "xy.f16.npy").astype(np.float32)
        self.facet_info = json.loads((d / "facets.json").read_text())
        meta = json.loads((d / "topics.json").read_text())
        self.topics = {t["id"]: t for t in meta["topics"]}
        self.edges = meta["edges"]
        self.macro_labels = meta["macro_labels"]
        phrases = pd.read_parquet(d / "phrases.parquet")

        # int8 dot products come back to cosine through this factor
        self.unit = (self.manifest["scale"] / 127.0) ** 2
        self.n_rows = len(self.rows)
        self.n_uniq = len(self.vec)
        self.uniq = self.rows["uniq"].to_numpy()
        self.topic = self.rows["topic"].to_numpy()
        self.text = self.rows["text"].tolist()
        self.words = np.array([len(t.split()) for t in self.text])

        order = np.argsort(self.uniq, kind="stable")
        self._rows_sorted = order
        self._uniq_start = np.searchsorted(self.uniq[order], np.arange(self.n_uniq + 1))
        self.uniq_topic = self.topic[order[self._uniq_start[:-1]]]

        self.phrase_txt = phrases["phrase"].tolist()
        self.phrase_idf = phrases["idf"].to_numpy(np.float32)
        self.phrase_ix = {p: j for j, p in enumerate(self.phrase_txt)}
        self._tri: dict[str, list[int]] = {}
        self._tri_len = np.zeros(len(self.phrase_txt), np.int32)
        for p, j in self.phrase_ix.items():
            if " " in p:
                continue
            tg = _trigrams(p)
            self._tri_len[j] = len(tg)
            for t in tg:
                self._tri.setdefault(t, []).append(j)

        # one binary text-by-word matrix serves wording matches and contrasts
        first_rows = order[self._uniq_start[:-1]]
        cv = CountVectorizer(binary=True, token_pattern=r"(?u)\b[a-z][a-z]+\b", dtype=np.float32)
        self._bow: sparse.csc_matrix = cv.fit_transform(
            [self.text[i] for i in first_rows]).tocsc()
        self._vocab = cv.vocabulary_
        self._vocab_words = cv.get_feature_names_out()
        self._word_df = np.asarray(self._bow.sum(0)).ravel()

        self._codes: dict[str, pd.Categorical] = {}
        self._ranges: dict[str, np.ndarray] = {}
        if "group" in self.rows.columns:
            self._codes["group"] = pd.Categorical(self.rows["group"])
        for f in cfg.facets:
            col = self.rows[f"f_{f.column}"]
            if f.type == "categorical":
                self._codes[f.column] = pd.Categorical(col)
            elif f.type == "date":
                days = pd.to_datetime(col).to_numpy("datetime64[D]")
                self._ranges[f.column] = np.where(np.isnat(days), np.nan, days.astype(float))
            else:
                self._ranges[f.column] = col.to_numpy(float)

        # rows sharing each row's id, so the UI offers "same document" only when there are some
        self._id_count = (self.rows.groupby("id")["id"].transform("size").to_numpy()
                          if "id" in self.rows.columns else None)

        cent = np.zeros((len(self.topics), self.vec.shape[1]), np.float32)
        for k in self.topics:
            m = self.vec[self.uniq_topic == k]
            if len(m):
                cent[k] = m.mean(0)
        self.cent = cent / np.clip(np.linalg.norm(cent, axis=1, keepdims=True), 1e-9, None)

        rng = np.random.default_rng(42)
        pick = rng.choice(self.n_uniq, min(MAP_POINTS, self.n_uniq), replace=False)
        self._points = [[round(float(self.xy[i, 0]), 3), round(float(self.xy[i, 1]), 3),
                         int(self.uniq_topic[i])] for i in pick]

    # ---------------------------------------------------------------- scope
    def mask(self, scope: dict | None) -> np.ndarray:
        """Boolean row mask for {groups, topics, filters}."""
        m = np.ones(self.n_rows, bool)
        scope = scope or {}
        if scope.get("groups"):
            if "group" not in self._codes:
                raise ScopeError("no group column configured")
            m &= self._isin("group", scope["groups"])
        if scope.get("topics"):
            m &= np.isin(self.topic, np.array(scope["topics"], int))
        for col, want in (scope.get("filters") or {}).items():
            if col in self._codes and col != "group":
                if not isinstance(want, list):
                    raise ScopeError(f"{col}: expected a list of values")
                m &= self._isin(col, want)
            elif col in self._ranges:
                if not isinstance(want, dict):
                    raise ScopeError(f"{col}: expected min/max")
                m &= self._in_range(col, want.get("min"), want.get("max"))
            else:
                raise ScopeError(f"unknown facet: {col}")
        return m

    def _isin(self, col: str, values: list) -> np.ndarray:
        cat = self._codes[col]
        codes = [i for i, c in enumerate(cat.categories) if str(c) in set(map(str, values))]
        return np.isin(cat.codes, codes)

    def _in_range(self, col: str, lo, hi) -> np.ndarray:
        vals = self._ranges[col]
        m = ~np.isnan(vals)
        is_date = self.cfg.facet(col).type == "date"
        for bound, keep in ((lo, np.greater_equal), (hi, np.less_equal)):
            if bound is None or bound == "":
                continue
            try:
                b = (float(np.datetime64(str(bound), "D").astype(float)) if is_date
                     else float(bound))
            except ValueError as e:
                raise ScopeError(f"{col}: bad bound {bound!r}") from e
            m &= keep(vals, b)
        return m

    def _uniq_in(self, row_mask: np.ndarray) -> np.ndarray:
        u = np.zeros(self.n_uniq, bool)
        u[self.uniq[row_mask]] = True
        return u

    def _rows_of(self, u: int) -> np.ndarray:
        return self._rows_sorted[self._uniq_start[u]:self._uniq_start[u + 1]]

    # ----------------------------------------------------------------- hits
    def hit(self, row: int, **extra) -> dict:
        r = int(row)
        tid = int(self.topic[r])
        out = {
            "row": r,
            "text": self.text[r],
            "words": int(self.words[r]),
            "topic": tid,
            "topic_label": self.topics[tid]["label"] if tid in self.topics else None,
            "facets": {f.column: self._value(f.column, r) for f in self.cfg.facets},
        }
        if self._id_count is not None:
            out["id"] = str(self.rows["id"].iat[r])
            out["n_id"] = int(self._id_count[r])
        if "group" in self.rows.columns:
            out["group"] = self.rows["group"].iat[r]
        for key in ("url", "credit", "credit_url"):
            if key in self.rows.columns:
                out[key] = self.rows[key].iat[r]
        out.update(extra)
        return out

    def _value(self, col: str, r: int):
        v = self.rows[f"f_{col}"].iat[r]
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        if isinstance(v, (float, np.floating)):
            return int(v) if float(v).is_integer() else float(v)
        return str(v)

    def _hit_for_uniq(self, u: int, row_mask: np.ndarray, **extra) -> dict | None:
        pos = self._rows_of(u)
        pos = pos[row_mask[pos]]
        if not len(pos):
            return None
        return self.hit(pos[0], n_same=int(len(pos)), **extra)

    # --------------------------------------------------------------- encode
    def encode(self, text: str) -> tuple[np.ndarray | None, list[dict]]:
        """Query string -> unit vector, from the phrases it contains."""
        toks = _TOK.findall((text or "").lower())
        has_content = any(t not in LEAD_STOP for t in toks)
        matched: list[tuple[str, int, bool]] = []
        i = 0
        while i < len(toks):
            if toks[i] in LEAD_STOP and has_content:
                i += 1
                continue
            for n in (3, 2, 1):                       # longest phrase wins
                j = self.phrase_ix.get(" ".join(toks[i:i + n])) if i + n <= len(toks) else None
                if j is not None:
                    matched.append((self.phrase_txt[j], j, False))
                    i += n
                    break
            else:
                j = self._fuzzy(toks[i])
                if j is not None:
                    matched.append((self.phrase_txt[j], j, True))
                i += 1
        if not matched:
            return None, []
        idx = np.array([m[1] for m in matched])
        v = (self.phrase_vec[idx] * self.phrase_idf[idx][:, None]).sum(0)
        norm = np.linalg.norm(v)
        if norm < 1e-9:
            return None, []
        # scaled so that vec @ q * unit is a cosine
        q = v / norm * (127.0 / self.manifest["scale"])
        return q.astype(np.float32), [{"term": m[0], "fuzzy": m[2]} for m in matched]

    def _fuzzy(self, tok: str, floor: float = 0.45) -> int | None:
        tg = _trigrams(tok)
        cand: dict[int, int] = {}
        for t in tg:
            for j in self._tri.get(t, ()):
                cand[j] = cand.get(j, 0) + 1
        best, score = None, 0.0
        for j, c in cand.items():
            jac = c / max(len(tg) + int(self._tri_len[j]) - c, 1)
            if jac > score:
                best, score = j, jac
        return best if score >= floor else None

    def _wording(self, toks: list[str]) -> np.ndarray:
        """Per distinct text: IDF-weighted share of the query's words it holds."""
        toks = [t for t in dict.fromkeys(toks) if t not in CONTRAST_STOP][:12]
        out = np.zeros(self.n_uniq, np.float32)
        total = 0.0
        for t in toks:
            j = self._vocab.get(t)
            df = self._word_df[j] if j is not None else 1.0
            w = float(np.log(1 + self.n_uniq / df))
            total += w
            if j is not None:
                out[self._bow.indices[self._bow.indptr[j]:self._bow.indptr[j + 1]]] += w
        return out / total if total else out

    # --------------------------------------------------------------- search
    def search(self, query: str, k: int = 50, scope: dict | None = None,
               min_score: float = 0.3) -> dict:
        row_mask = self.mask(scope)
        univ = self._uniq_in(row_mask)
        quoted = _QUOTED.match(query or "")
        score = np.full(self.n_uniq, -np.inf, np.float32)
        wording = np.zeros(self.n_uniq, np.float32)
        meaning = np.zeros(self.n_uniq, np.float32)

        if quoted:
            needle = f" {_norm_key(quoted.group(1))} "
            terms, method = [{"term": quoted.group(1).strip(), "fuzzy": False}], "exact"
            for u in np.flatnonzero(univ):
                if needle in f" {_norm_key(self.text[self._rows_of(u)[0]])} ":
                    score[u] = 1.0
        else:
            qvec, terms = self.encode(query)
            if qvec is not None:
                score = (self.vec @ qvec) * self.unit
                meaning = np.clip(score, 0, None)
            wording = self._wording(_TOK.findall((query or "").lower()))
            lex = wording >= 0.5
            score[lex] = np.maximum(score[lex], LEX_SCORE * wording[lex])
            method = ("hybrid" if qvec is not None and lex.any()
                      else "semantic" if qvec is not None
                      else "lexical" if lex.any() else "unmatched")
            if not terms:
                terms = [{"term": t, "fuzzy": False}
                         for t in _TOK.findall((query or "").lower()) if t in self._vocab]

        score[~univ] = -np.inf
        included = score >= min_score
        cand = np.flatnonzero(included)
        # rank on meaning and wording together: shared words alone are weak
        # evidence in a long text, and so is a near vector with none of the words
        rank = np.where(quoted is not None, score, meaning + WORDING_WEIGHT * wording)
        order = cand[np.argsort(-rank[cand])][:k]
        results = []
        for u in order:
            h = self._hit_for_uniq(int(u), row_mask, score=round(float(score[u]), 4),
                                   wording=round(float(wording[u]), 3))
            if h:
                results.append(h)

        hit_rows = included[self.uniq] & row_mask
        counts = np.bincount(self.topic[hit_rows & (self.topic >= 0)], minlength=len(self.topics))
        topic_hits = [{"id": int(t), "n": int(counts[t]), "label": self.topics[int(t)]["label"]}
                      for t in np.argsort(-counts)[:12] if counts[t]]
        return {"method": method, "terms": terms, "results": results,
                "total_matched": int(hit_rows.sum()), "n_in_scope": int(row_mask.sum()),
                "topic_hits": topic_hits}

    def similar(self, row: int, k: int = 10) -> dict | None:
        if not 0 <= row < self.n_rows:
            return None
        u = int(self.uniq[row])
        score = (self.vec @ self.vec[u]) * self.unit
        score[u] = -np.inf
        everything = np.ones(self.n_rows, bool)
        order = np.argsort(-score)[:k]
        return {"source": self.hit(row),
                "results": [self._hit_for_uniq(int(i), everything, score=round(float(score[i]), 4))
                            for i in order]}

    def random(self, n: int = 5, scope: dict | None = None, min_words: int = 6,
               seed: int | None = None) -> dict:
        m = self.mask(scope)
        pool = self._first_rows(m & (self.words >= min_words))
        rng = np.random.default_rng(seed)
        pick = rng.choice(pool, min(n, len(pool)), replace=False) if len(pool) else []
        return {"results": [self._hit_for_uniq(int(self.uniq[r]), m) for r in pick],
                "n_in_scope": int(len(pool))}

    def browse(self, scope: dict | None = None, offset: int = 0, limit: int = 50) -> dict:
        m = self.mask(scope)
        pool = self._first_rows(m)
        return {"results": [self._hit_for_uniq(int(self.uniq[r]), m)
                            for r in pool[offset:offset + limit]],
                "total": int(len(pool)), "offset": offset}

    def _first_rows(self, row_mask: np.ndarray) -> np.ndarray:
        """One row per group of duplicate texts, in corpus order."""
        rows = np.flatnonzero(row_mask)
        _, first = np.unique(self.uniq[rows], return_index=True)
        return rows[np.sort(first)]

    def document(self, row: int, limit: int = 200) -> dict | None:
        """Every row sharing the id of this row."""
        if "id" not in self.rows.columns or not 0 <= row < self.n_rows:
            return None
        doc_id = self.rows["id"].iat[row]
        pos = np.flatnonzero((self.rows["id"] == doc_id).to_numpy())
        return {"id": str(doc_id), "n": int(len(pos)),
                "results": [self.hit(r) for r in pos[:limit]]}

    # ----------------------------------------------------------------- map
    def graph(self) -> dict:
        topics = [{k: t[k] for k in ("id", "label", "count", "macro", "x", "y")}
                  for t in self.topics.values()]
        return {"topics": topics, "edges": self.edges, "macro_labels": self.macro_labels,
                "points": self._points, "n_rows": self.n_rows}

    def facets(self, scope: dict | None = None) -> dict:
        """Facet levels and topic sizes, counted inside a scope."""
        m = self.mask(scope)
        out = {}
        for col, info in self.facet_info.items():
            entry = {k: v for k, v in info.items() if k != "values"}
            if info["type"] == "categorical":
                cat = self._codes[col]
                counts = np.bincount(cat.codes[m & (cat.codes >= 0)], minlength=len(cat.categories))
                listed = {v["v"] for v in info["values"]}
                vals = [{"v": str(c), "n": int(n)} for c, n in zip(cat.categories, counts)
                        if str(c) in listed]
                entry["values"] = sorted(vals, key=lambda v: -v["n"])
            out[col] = entry
        counts = np.bincount(self.topic[m & (self.topic >= 0)], minlength=len(self.topics))
        return {"n": int(m.sum()), "facets": out,
                "topics": {int(t): int(n) for t, n in enumerate(counts)}}

    def topic_detail(self, tid: int, scope: dict | None = None, limit: int = 30) -> dict | None:
        t = self.topics.get(tid)
        if t is None:
            return None
        base = self.mask(scope)
        m = base & (self.topic == tid)
        members = np.flatnonzero(self._uniq_in(m))
        close = members[np.argsort(-(self.vec[members] @ self.cent[tid]))][:limit]
        sim = self.cent @ self.cent[tid]
        sim[tid] = -np.inf
        near = [{"id": int(j), "label": self.topics[int(j)]["label"],
                 "sim": round(float(sim[j]), 3)} for j in np.argsort(-sim)[:6] if sim[j] > 0]

        # which facet values are over-represented in this topic
        breakdown = {}
        share = m.sum() / max(base.sum(), 1)
        for col, cat in self._codes.items():
            inside = np.bincount(cat.codes[m & (cat.codes >= 0)], minlength=len(cat.categories))
            overall = np.bincount(cat.codes[base & (cat.codes >= 0)], minlength=len(cat.categories))
            top = [{"v": str(cat.categories[i]), "n": int(inside[i]),
                    "lift": round(float(inside[i] / overall[i] / share), 2) if share else None}
                   for i in np.argsort(-inside)[:8] if inside[i]]
            breakdown[col] = {"label": self.facet_info[col]["label"], "values": top}
        return {"id": tid, "label": t["label"], "keywords": t["keywords"], "count": t["count"],
                "n_in_scope": int(m.sum()), "macro": t["macro"],
                "macro_label": self.macro_labels.get(str(t["macro"]), ""),
                "neighbours": near, "breakdown": breakdown,
                "results": [self._hit_for_uniq(int(u), m) for u in close]}

    # ------------------------------------------------------------- contrast
    def contrast(self, a: dict, b: dict | None = None, within: dict | None = None,
                 top: int = 15, min_rate: float = 0.004) -> dict:
        """Words that mark scope A against scope B (or against the rest of
        `within`), by weighted log-odds with an informative Dirichlet prior
        (Monroe, Colaresi and Quinn 2008) over presence in a text, and A's
        share of each topic over A's share overall."""
        base = self.mask(within)
        ma = base & self.mask(a)
        mb = (base & self.mask(b)) if b else (base & ~ma)
        na, nb = int(ma.sum()), int(mb.sum())
        out = {"n_a": na, "n_b": nb, "words_a": [], "words_b": [], "lift": [], "too_few": False}
        if na < CONTRAST_MIN_ROWS or nb < CONTRAST_MIN_ROWS:
            out["too_few"] = True
            return out

        ya = self._bow.T @ np.bincount(self.uniq[ma], minlength=self.n_uniq).astype(np.float32)
        yb = self._bow.T @ np.bincount(self.uniq[mb], minlength=self.n_uniq).astype(np.float32)
        keep = np.array([w not in CONTRAST_STOP for w in self._vocab_words]) & (ya + yb >= 5)
        sa, sb = max(float(ya.sum()), 1.0), max(float(yb.sum()), 1.0)
        prior = CONTRAST_PRIOR * (self._word_df / self._word_df.sum())
        d = (np.log((ya + prior) / (sa + CONTRAST_PRIOR - ya - prior))
             - np.log((yb + prior) / (sb + CONTRAST_PRIOR - yb - prior)))
        z = d / np.sqrt(1.0 / (ya + prior) + 1.0 / (yb + prior))
        z[~keep] = 0.0
        ra, rb = ya / na, yb / nb
        order = np.argsort(z)

        def pack(idx) -> list[dict]:
            return [{"w": str(self._vocab_words[i]), "z": round(float(z[i]), 2),
                     "rate_a": round(float(ra[i]), 5), "rate_b": round(float(rb[i]), 5)}
                    for i in idx]

        out["words_a"] = pack([i for i in order[::-1] if z[i] > 0 and ra[i] >= min_rate][:top])
        out["words_b"] = pack([i for i in order if z[i] < 0 and rb[i] >= min_rate][:top])

        both = ma | mb
        base_share = na / max(int(both.sum()), 1)
        for tid in self.topics:
            in_topic = self.topic == tid
            n_both = int((in_topic & both).sum())
            if n_both >= LIFT_MIN_ROWS:
                share = int((in_topic & ma).sum()) / n_both
                out["lift"].append({"id": tid, "lift": round(share / base_share, 3), "n": n_both})
        return out
