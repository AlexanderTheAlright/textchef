"""Build one index from the 200-row sample with the offline "hashing"
embedder, on CPU, and share it across tests."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from textchef.cli import build
from textchef.config import Config, load_config

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("project")
    shutil.copy(DATA / "sample.csv", root / "sample.csv")
    shutil.copy(DATA / "textchef.toml", root / "textchef.toml")
    return root


@pytest.fixture(scope="session")
def cfg(project: Path) -> Config:
    build(str(project / "textchef.toml"), device="cpu", only=None)
    return load_config(project / "textchef.toml")
