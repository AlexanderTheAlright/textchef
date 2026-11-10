"""textchef build CONFIG | textchef serve CONFIG"""
from __future__ import annotations

import argparse
import sys

from textchef.config import ConfigError, load_config

HOST = "127.0.0.1"      # loopback only, on purpose; not configurable
STEPS = ("load", "embed", "phrases", "topics", "pack")


def build(config_path: str, device: str, only: str | None) -> None:
    from textchef.pipeline import embed, load, pack, phrases, topics
    cfg = load_config(config_path)
    steps = {"load": lambda: load.run(cfg), "embed": lambda: embed.run(cfg, device),
             "topics": lambda: topics.run(cfg), "phrases": lambda: phrases.run(cfg, device),
             "pack": lambda: pack.run(cfg)}
    for name in ([only] if only else STEPS):
        steps[name]()


def serve(config_path: str, port: int | None) -> None:
    import uvicorn

    from textchef.server.app import create_app
    cfg = load_config(config_path)
    if not (cfg.index_dir / "manifest.json").is_file():
        raise ConfigError(f"no index in {cfg.index_dir}; run: textchef build {config_path}")
    uvicorn.run(create_app(cfg), host=HOST, port=port or cfg.port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="textchef")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("config")
    b.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    b.add_argument("--step", choices=STEPS)
    s = sub.add_parser("serve")
    s.add_argument("config")
    s.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            build(args.config, args.device, args.step)
        else:
            serve(args.config, args.port)
    except ConfigError as e:
        print(f"textchef: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
