"""Keep a batch GPU job from starving a display that shares the card.

Wrap each encode call in `with GpuBudget():`. After every batch it sleeps in
proportion to the time the batch took (GPU_DUTY, default 0.5 = free half the
time), and before every batch it waits until GPU_RESERVE_MB of memory is free
and the card is under GPU_TEMP_CEILING_C. On CPU it does nothing.
"""
from __future__ import annotations

import os
import subprocess
import time


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _query_gpu() -> tuple[float, float] | None:
    """(free MB, temperature C) of the first GPU, or None when unknown."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True).stdout
        free, temp = out.strip().splitlines()[0].split(",")
        return float(free), float(temp)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


class GpuBudget:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.duty = min(max(_env_float("GPU_DUTY", 0.5), 0.05), 1.0)
        self.reserve_mb = _env_float("GPU_RESERVE_MB", 4096)
        self.temp_ceiling = _env_float("GPU_TEMP_CEILING_C", 75)
        self.work_s = 0.0
        self.sleep_s = 0.0
        self._t0 = 0.0

    def wait_for_headroom(self, max_wait_s: float = 300.0) -> None:
        waited = 0.0
        while waited < max_wait_s:
            state = _query_gpu()
            if state is None:
                return
            free_mb, temp = state
            if free_mb >= self.reserve_mb and temp < self.temp_ceiling:
                return
            time.sleep(2.0)
            waited += 2.0
            self.sleep_s += 2.0
        raise RuntimeError("GPU has no free memory or is too hot; stopping instead of pushing on")

    def __enter__(self) -> "GpuBudget":
        if self.enabled:
            self.wait_for_headroom()
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *exc) -> None:
        took = time.monotonic() - self._t0
        self.work_s += took
        if self.enabled and self.duty < 1.0:
            pause = took * (1.0 - self.duty) / self.duty
            time.sleep(pause)
            self.sleep_s += pause

    def report(self) -> str:
        return f"gpu work {self.work_s:.0f}s, paused {self.sleep_s:.0f}s (duty {self.duty})"
