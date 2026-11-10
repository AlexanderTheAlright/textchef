<!-- description: to be written by Alex -->

# textchef

## Quick start

```
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/textchef build tests/data/textchef.toml
(cd web && npm ci && npm run build)
.venv/bin/textchef serve tests/data/textchef.toml
```

Open http://127.0.0.1:8765

Demo corpus (20,000 passages, default model, GPU):

```
.venv/bin/pip install -e ".[model]"
PYTHON=.venv/bin/python examples/build_demo.sh
.venv/bin/textchef serve examples/textchef.toml
```

Tests:

```
.venv/bin/pytest
(cd web && node scripts/check_map.mjs http://127.0.0.1:8765 && node scripts/check_ui.mjs http://127.0.0.1:8765)
```

## Config

`textchef.toml`. Paths are relative to the config file and must stay inside its folder.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `data_dir` | string | `"textchef-data"` | Folder the build writes and the server reads |
| `corpus.path` | string | required | `.csv` or `.parquet` file |
| `corpus.text` | string | required | Text column |
| `corpus.id` | string | none | Document or author id column |
| `corpus.id_label` | string | `"Document"` | Display label for the id |
| `corpus.group` | string | none | Group column |
| `corpus.group_label` | string | `"Group"` | Display label for the group |
| `corpus.url` | string | none | Column of `http(s)` links to each text's source |
| `corpus.credit` | string | none | Column naming each text's author or source |
| `corpus.credit_url` | string | none | Column of `http(s)` links for the credit |
| `corpus.min_words` | integer | `3` | Shorter texts are dropped |
| `facet[].column` | string | required | Facet column |
| `facet[].label` | string | column name | Display label |
| `facet[].type` | string | `"categorical"` | `"categorical"`, `"numeric"` or `"date"` |
| `facet[].contrast` | boolean | `true` | Offer in Contrast (categorical only) |
| `model.name` | string | `"mixedbread-ai/mxbai-embed-large-v1"` | sentence-transformers model, or `"hashing"` (offline, no download) |
| `model.batch_size` | integer | `32` | Texts per forward pass |
| `model.max_seq_length` | integer | `256` | Tokens per text |
| `model.dims` | integer | `256` | Served vector size after PCA |
| `topics.min_cluster_size` | integer | `0` | HDBSCAN minimum cluster size; `0` = from corpus size |
| `topics.stopwords` | list of strings | `[]` | Extra words kept out of topic labels |
| `server.port` | integer | `8765` | Port on 127.0.0.1 |
| `ui.theme_light` | string | `"light"` | Default theme, light colour scheme |
| `ui.theme_dark` | string | `"dark"` | Default theme, dark colour scheme |
| `ui.themes_dir` | string | none | Folder of extra theme `.toml` files |

`textchef build CONFIG [--device auto|cpu|cuda] [--step load|embed|phrases|topics|pack]`
`textchef serve CONFIG [--port N]`

## Licence

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
