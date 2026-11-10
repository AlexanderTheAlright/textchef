# Third-party notices

Nothing below is bundled in this repository; each is fetched at install, build or run time.

## Python

| Package | Licence | Source |
|---|---|---|
| numpy | BSD-3-Clause | https://numpy.org |
| pandas | BSD-3-Clause | https://pandas.pydata.org |
| pyarrow | Apache-2.0 | https://arrow.apache.org |
| scipy | BSD-3-Clause | https://scipy.org |
| scikit-learn | BSD-3-Clause | https://scikit-learn.org |
| umap-learn | BSD-3-Clause | https://github.com/lmcinnes/umap |
| numba (via umap-learn) | BSD-2-Clause | https://numba.pydata.org |
| llvmlite (via numba) | BSD-2-Clause, Apache-2.0 WITH LLVM-exception | https://github.com/numba/llvmlite |
| pynndescent (via umap-learn) | BSD-2-Clause | https://github.com/lmcinnes/pynndescent |
| tqdm (via umap-learn) | MPL-2.0 AND MIT | https://github.com/tqdm/tqdm |
| fastapi | MIT | https://github.com/fastapi/fastapi |
| starlette (via fastapi) | BSD-3-Clause | https://github.com/encode/starlette |
| pydantic (via fastapi) | MIT | https://github.com/pydantic/pydantic |
| uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| sentence-transformers (optional `model`) | Apache-2.0 | https://github.com/UKPLab/sentence-transformers |
| torch (optional `model`) | BSD-3-Clause, Apache-2.0, BSD-2-Clause, BSL-1.0, MIT | https://github.com/pytorch/pytorch |
| transformers (via sentence-transformers) | Apache-2.0 | https://github.com/huggingface/transformers |
| pytest (optional `test`) | MIT | https://github.com/pytest-dev/pytest |
| httpx (optional `test`) | BSD-3-Clause | https://github.com/encode/httpx |
| certifi (via httpx) | MPL-2.0 | https://github.com/certifi/python-certifi |

## npm (build only; `web/package-lock.json` pins every version)

| Package | Licence | Source |
|---|---|---|
| next | MIT | https://github.com/vercel/next.js |
| react, react-dom | MIT | https://github.com/facebook/react |
| typescript | Apache-2.0 | https://github.com/microsoft/TypeScript |
| @types/node, @types/react, @types/react-dom | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped |
| caniuse-lite (via next) | CC-BY-4.0 | https://github.com/browserslist/caniuse-lite |
| sharp (optional, via next) | Apache-2.0 | https://github.com/lovell/sharp |
| @img/sharp-libvips-* (optional, via sharp; not used by the static build) | LGPL-3.0-or-later | https://github.com/lovell/sharp-libvips |

## Models

| Model | Licence | Source |
|---|---|---|
| mixedbread-ai/mxbai-embed-large-v1 (default; downloaded on first build) | Apache-2.0 | https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1 |

## Data

| Data | Licence | Source |
|---|---|---|
| The Workplace Stack Exchange posts, 2018-05-02 onward (demo corpus; `tests/data/sample.csv` holds 200 passages) | CC BY-SA 4.0 | https://workplace.stackexchange.com , https://archive.org/details/stackexchange , https://creativecommons.org/licenses/by-sa/4.0/ |

Source: Stack Exchange Network. Each passage carries its author's display name (`author`), a link to the author's profile (`author_url`) and a link to the original question (`url`); passages are excerpts of the posts. CC BY-SA 4.0 share-alike applies to `tests/data/sample.csv` only, not to the code.
