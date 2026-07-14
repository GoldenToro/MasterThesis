from __future__ import annotations

from itertools import combinations
from statistics import mean

from map_schema.canonical_map import CanonicalMap, WALKABLE_SYMBOLS


def calculate_map_set_diversity(maps: list[CanonicalMap]) -> dict[str, float | int]:
    if len(maps) < 2:
        return {
            "map_count": len(maps),
            "unique_map_count": len({canonical_map.content_hash() for canonical_map in maps}),
            "unique_map_ratio": 1.0 if maps else 0.0,
            "mean_pairwise_tile_distance": 0.0,
        }

    distances = [_tile_distance(first, second) for first, second in combinations(maps, 2)]
    unique_count = len({canonical_map.content_hash() for canonical_map in maps})
    return {
        "map_count": len(maps),
        "unique_map_count": unique_count,
        "unique_map_ratio": unique_count / len(maps),
        "mean_pairwise_tile_distance": mean(distances),
    }


def _tile_distance(first: CanonicalMap, second: CanonicalMap) -> float:
    if first.width != second.width or first.height != second.height:
        return 1.0
    differences = 0
    total = first.width * first.height
    for y in range(first.height):
        for x in range(first.width):
            first_walkable = first.grid[y][x] in WALKABLE_SYMBOLS
            second_walkable = second.grid[y][x] in WALKABLE_SYMBOLS
            differences += int(first_walkable != second_walkable)
    return differences / total
