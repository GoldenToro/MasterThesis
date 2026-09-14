from __future__ import annotations

import random

from generators.base_generator import BaseGenerator
from generators.constructive.common import (
    Rect,
    blank_grid,
    carve_rect,
    connect_components,
    floor_components,
    grid_rows,
    run_constructive,
)
from map_schema.canonical_map import FLOOR, WALL, CanonicalMap


def run(base_generator: BaseGenerator) -> list[str]:
    return run_constructive(base_generator, _generate, "cellular_automata")


def _generate(
    width: int,
    height: int,
    rng: random.Random,
    settings: dict,
    map_id: str,
) -> CanonicalMap:
    wall_probability = min(
        0.9,
        max(0.1, float(settings.get("initial_wall_probability", 0.55))),
    )
    iterations = max(0, int(settings.get("smoothing_iterations", 5)))
    threshold = int(settings.get("wall_neighbor_threshold", 5))
    minimum_region_size = max(1, int(settings.get("minimum_region_size", 20)))
    connect_regions = bool(settings.get("connect_regions", True))
    corridor_width = max(1, int(settings.get("corridor_width", 1)))

    grid = blank_grid(width, height)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            grid[y][x] = WALL if rng.random() < wall_probability else FLOOR

    for _ in range(iterations):
        next_grid = blank_grid(width, height)
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                wall_neighbors = 0
                for ny in range(y - 1, y + 2):
                    for nx in range(x - 1, x + 2):
                        if nx == x and ny == y:
                            continue
                        if grid[ny][nx] == WALL:
                            wall_neighbors += 1
                next_grid[y][x] = WALL if wall_neighbors >= threshold else FLOOR
        grid = next_grid

    components_before = floor_components(grid)
    retained = [component for component in components_before if len(component) >= minimum_region_size]
    accepted = set().union(*retained) if retained else set()
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            grid[y][x] = FLOOR if (x, y) in accepted else WALL

    if not accepted:
        fallback_width = max(3, width // 4)
        fallback_height = max(3, height // 4)
        carve_rect(
            grid,
            Rect(
                width // 2 - fallback_width // 2,
                height // 2 - fallback_height // 2,
                fallback_width,
                fallback_height,
            ),
        )
        retained = floor_components(grid)

    corridor_count = 0
    if connect_regions:
        corridor_count = connect_components(grid, rng, corridor_width)

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=grid_rows(grid),
        metadata={
            "genome_representation_type": "cellular_grid",
            "room_count": len(retained),
            "corridor_count": corridor_count,
            "initial_wall_probability": wall_probability,
            "smoothing_iterations": iterations,
        },
    )
