"""Load theme files. Every value is checked before it reaches a browser,
because the web app writes palette values into CSS."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILTIN_DIR = REPO / "themes"

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_FONT = re.compile(r"^[A-Za-z0-9 ,'\"_-]{1,200}$")

COLOR_KEYS = ("bg", "surface", "surface_alt", "border", "text", "text_muted", "brand",
              "brand_text", "accent", "accent_text", "accent_soft", "mark")
GRAPH_KEYS = ("edge", "label", "muted", "lift_low", "lift_high")
STRING_KEYS = ("title", "search_placeholder", "start", "empty")


class ThemeError(ValueError):
    pass


def load_theme(path: Path) -> dict:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    name = path.stem
    if not _NAME.match(name):
        raise ThemeError(f"{path.name}: bad theme name")
    colors, graph, strings = raw.get("colors", {}), raw.get("graph", {}), raw.get("strings", {})
    palette = graph.get("palette", [])
    for key in COLOR_KEYS:
        if not _COLOR.match(str(colors.get(key, ""))):
            raise ThemeError(f"{name}: colors.{key} must be a hex colour")
    for key in GRAPH_KEYS:
        if not _COLOR.match(str(graph.get(key, ""))):
            raise ThemeError(f"{name}: graph.{key} must be a hex colour")
    if not palette or not all(_COLOR.match(str(c)) for c in palette):
        raise ThemeError(f"{name}: graph.palette must be a list of hex colours")
    for key in ("font", "font_mono"):
        if not _FONT.match(str(raw.get(key, ""))):
            raise ThemeError(f"{name}: {key} is not a font stack")
    if raw.get("scheme") not in ("light", "dark"):
        raise ThemeError(f"{name}: scheme must be light or dark")
    return {
        "name": name,
        "label": str(raw.get("label", name))[:40],
        "scheme": raw["scheme"],
        "font": raw["font"],
        "font_mono": raw["font_mono"],
        "colors": {k: colors[k] for k in COLOR_KEYS},
        "graph": {**{k: graph[k] for k in GRAPH_KEYS}, "palette": list(palette)[:24]},
        "strings": {k: str(strings.get(k, ""))[:80] for k in STRING_KEYS},
    }


def load_themes(extra_dir: Path | None = None) -> list[dict]:
    themes: dict[str, dict] = {}
    for folder in (BUILTIN_DIR, extra_dir):
        if folder and folder.is_dir():
            for path in sorted(folder.glob("*.toml")):
                theme = load_theme(path)
                themes[theme["name"]] = theme
    return list(themes.values())
