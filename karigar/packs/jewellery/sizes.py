"""Indian ring sizes -> inner diameter, from one cited brand chart (data/ring_sizes.json).

Shops can replace the JSON with their own chart; the code only reads `sizes[n].inner_d_mm`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RING_SIZES_FILE = Path(__file__).resolve().parents[3] / "data" / "ring_sizes.json"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def chart(path: Path | None = None) -> dict:
    return _load(str(path or RING_SIZES_FILE))


def ring_inner_d_mm(size: int) -> float:
    """Inner diameter (mm) of an Indian ring size. ValueError if the chart has no such size."""
    sizes = chart()["sizes"]
    key = str(int(size)) if float(size) == int(size) else str(size)
    if key not in sizes:
        raise ValueError(f"Indian ring size {size} is not in the chart ({min(map(int, sizes))}-{max(map(int, sizes))})")
    return float(sizes[key]["inner_d_mm"])


def us_ring_inner_d_mm(us_size: float) -> float:
    """US/Canada sizes follow a linear standard: 11.63 mm + 0.8128 mm per size."""
    return round(11.63 + 0.8128 * us_size, 1)


def bangle_inner_d_mm(sixteenths: int) -> float:
    """Indian bangle size 2-N means an inner diameter of 2 + N/16 inches."""
    return round((2 + sixteenths / 16) * 25.4, 1)
