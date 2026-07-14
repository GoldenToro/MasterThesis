from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from map_schema.canonical_map import WALKABLE_SYMBOLS, CanonicalMap


def canonical_to_area_genome(
    canonical_map: CanonicalMap,
    map_scale: int = 2,
    corridor_width_threshold: int = 3,
) -> dict[str, Any]:
    """Convert the canonical grid into exact, non-overlapping rectangles.

    Consecutive rows with identical walkable runs are merged. Canonical row zero
    is the visual top row, while Project Arena uses a bottom-row coordinate.
    """
    active: dict[tuple[int, int], dict[str, int]] = {}
    rectangles: list[dict[str, Any]] = []

    for row_index, row in enumerate(canonical_map.grid):
        runs = _walkable_runs(row)
        current_keys = set(runs)

        for key in list(active):
            if key not in current_keys:
                rectangles.append(_finalize_rectangle(active.pop(key), canonical_map.height, corridor_width_threshold))

        for left, right in runs:
            key = (left, right)
            if key in active:
                active[key]["row_end"] = row_index + 1
            else:
                active[key] = {
                    "left": left,
                    "right": right,
                    "row_start": row_index,
                    "row_end": row_index + 1,
                }

    for rectangle in active.values():
        rectangles.append(_finalize_rectangle(rectangle, canonical_map.height, corridor_width_threshold))

    return {
        "width": canonical_map.width,
        "height": canonical_map.height,
        "mapScale": int(map_scale),
        "areas": rectangles,
    }


def write_area_genome(
    canonical_map: CanonicalMap,
    path: Path,
    map_scale: int = 2,
    corridor_width_threshold: int = 3,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_to_area_genome(canonical_map, map_scale, corridor_width_threshold)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _walkable_runs(row: str) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, symbol in enumerate(row + "#"):
        walkable = symbol in WALKABLE_SYMBOLS
        if walkable and start is None:
            start = index
        elif walkable is False and start is not None:
            runs.append((start, index))
            start = None
    return runs


def _finalize_rectangle(
    rectangle: dict[str, int],
    map_height: int,
    corridor_width_threshold: int,
) -> dict[str, Any]:
    width = rectangle["right"] - rectangle["left"]
    height = rectangle["row_end"] - rectangle["row_start"]
    bottom = map_height - rectangle["row_end"]
    top = map_height - rectangle["row_start"]
    return {
        "bottomRow": bottom,
        "topRow": top,
        "leftColumn": rectangle["left"],
        "rightColumn": rectangle["right"],
        "isCorridor": min(width, height) <= corridor_width_threshold,
    }
