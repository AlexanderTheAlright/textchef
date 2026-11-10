"""Read and validate textchef.toml."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "mixedbread-ai/mxbai-embed-large-v1"
FACET_TYPES = ("categorical", "numeric", "date")
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Facet:
    column: str
    label: str
    type: str = "categorical"
    contrast: bool = True


@dataclass(frozen=True)
class Config:
    root: Path                      # folder holding the config file
    corpus_path: Path
    data_dir: Path
    text: str
    id: str | None = None
    group: str | None = None
    url: str | None = None          # column of web links back to each text's source
    credit: str | None = None       # column naming each text's author or source
    credit_url: str | None = None   # column of web links for the credit
    group_label: str = "Group"
    id_label: str = "Document"
    min_words: int = 3
    facets: tuple[Facet, ...] = ()
    model: str = DEFAULT_MODEL
    batch_size: int = 32
    max_seq_length: int = 256
    dims: int = 256
    min_cluster_size: int = 0       # 0 = pick from corpus size
    stopwords: tuple[str, ...] = ()
    port: int = 8765
    theme_light: str = "light"
    theme_dark: str = "dark"
    themes_dir: Path | None = None
    extra: dict = field(default_factory=dict)

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    def facet(self, column: str) -> Facet | None:
        return next((f for f in self.facets if f.column == column), None)


def _inside(root: Path, value: str, key: str) -> Path:
    """Resolve a path from the config; it must stay under the config's folder."""
    p = (root / value).resolve()
    if p != root and root not in p.parents:
        raise ConfigError(f"{key}: {value!r} is outside {root}")
    return p


def _typed(table: dict, key: str, kind: type, default):
    v = table.get(key, default)
    if v is None and default is None:
        return None
    if not isinstance(v, kind) or isinstance(v, bool) and kind is int:
        raise ConfigError(f"{key}: expected {kind.__name__}")
    return v


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    if not path.is_file():
        raise ConfigError(f"no config file at {path}")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.parent

    corpus = raw.get("corpus") or {}
    if "path" not in corpus or "text" not in corpus:
        raise ConfigError("[corpus] needs path and text")
    corpus_path = _inside(root, _typed(corpus, "path", str, None), "corpus.path")
    if corpus_path.suffix.lower() not in (".csv", ".parquet"):
        raise ConfigError("corpus.path must be a .csv or .parquet file")

    facets = []
    for f in raw.get("facet", []):
        col = _typed(f, "column", str, None)
        if not col:
            raise ConfigError("[[facet]] needs column")
        kind = _typed(f, "type", str, "categorical")
        if kind not in FACET_TYPES:
            raise ConfigError(f"facet {col}: type must be one of {FACET_TYPES}")
        facets.append(Facet(col, _typed(f, "label", str, col), kind,
                            _typed(f, "contrast", bool, True)))
    cols = [f.column for f in facets]
    if len(set(cols)) != len(cols):
        raise ConfigError("duplicate facet column")

    model = raw.get("model") or {}
    topics = raw.get("topics") or {}
    server = raw.get("server") or {}
    ui = raw.get("ui") or {}
    for key in ("theme_light", "theme_dark"):
        if key in ui and not _NAME.match(str(ui[key])):
            raise ConfigError(f"ui.{key}: not a theme name")
    port = _typed(server, "port", int, 8765)
    if not 1024 <= port <= 65535:
        raise ConfigError("server.port must be 1024-65535")
    themes_dir = _inside(root, ui["themes_dir"], "ui.themes_dir") if "themes_dir" in ui else None

    return Config(
        root=root,
        corpus_path=corpus_path,
        data_dir=_inside(root, _typed(raw, "data_dir", str, "textchef-data"), "data_dir"),
        text=_typed(corpus, "text", str, None),
        id=_typed(corpus, "id", str, None),
        group=_typed(corpus, "group", str, None),
        url=_typed(corpus, "url", str, None),
        credit=_typed(corpus, "credit", str, None),
        credit_url=_typed(corpus, "credit_url", str, None),
        group_label=_typed(corpus, "group_label", str, "Group"),
        id_label=_typed(corpus, "id_label", str, "Document"),
        min_words=_typed(corpus, "min_words", int, 3),
        facets=tuple(facets),
        model=_typed(model, "name", str, DEFAULT_MODEL),
        batch_size=_typed(model, "batch_size", int, 32),
        max_seq_length=_typed(model, "max_seq_length", int, 256),
        dims=_typed(model, "dims", int, 256),
        min_cluster_size=_typed(topics, "min_cluster_size", int, 0),
        stopwords=tuple(str(s).lower() for s in topics.get("stopwords", [])),
        port=port,
        theme_light=str(ui.get("theme_light", "light")),
        theme_dark=str(ui.get("theme_dark", "dark")),
        themes_dir=themes_dir,
    )
