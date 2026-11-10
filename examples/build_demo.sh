#!/usr/bin/env sh
# Fetch the demo corpus and build its index with the default model.
#   PYTHON   interpreter with textchef installed (default: python)
#   GPU_RUN  command prefix for the two GPU steps, e.g. a job wrapper (default: none)
#   RAW      folder for the download (default: examples/demo/raw)
set -eu
cd "$(dirname "$0")/.."
PY=${PYTHON:-python}
CONFIG=examples/textchef.toml

$PY -I examples/fetch_demo.py ${RAW:+--raw "$RAW"}
$PY -m textchef.cli build "$CONFIG" --step load
${GPU_RUN:-} $PY textchef/pipeline/embed.py "$CONFIG" cuda
${GPU_RUN:-} $PY textchef/pipeline/phrases.py "$CONFIG" cuda
$PY -m textchef.cli build "$CONFIG" --step topics
$PY -m textchef.cli build "$CONFIG" --step pack
