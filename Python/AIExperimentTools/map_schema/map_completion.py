from __future__ import annotations

from collections import deque
import random

from map_schema.canonical_map import AMMO, FLOOR, HEALTH, SPAWN, CanonicalMap


def strip_objects(canonical_map: CanonicalMap) -> CanonicalMap:
    """Keep the layout, replacing existing object markers with floor."""
    translation = str.maketrans("SHA", "...")
    return canonical_map.replace_grid(
        row.translate(translation) for row in canonical_map.grid
    )


def complete_map(
        canonical_map: CanonicalMap,
        *,
        seed: int,
        health_count: int,
        ammo_count: int,
) -> CanonicalMap:
    """Place objects on a validated, connected wall/floor layout."""
    if health_count < 0 or ammo_count < 0:
        raise ValueError("Pickup counts must be non-negative")

    floor = canonical_map.cells_with({FLOOR})
    required = 2 + health_count + ammo_count
    if len(floor) < required:
        raise ValueError(
            f"Placement needs {required} floor cells; found {len(floor)}"
        )

    rng = random.Random(seed)
    first = rng.choice(floor)
    floor_set = set(floor)
    distances = {first: 0}
    queue = deque([first])

    while queue:
        x, y = queue.popleft()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in floor_set and neighbor not in distances:
                distances[neighbor] = distances[(x, y)] + 1
                queue.append(neighbor)

    if len(distances) != len(floor):
        raise ValueError("Generic placement requires one connected floor region")

    furthest_distance = max(distances.values())
    second = rng.choice([
        point for point in floor
        if distances[point] == furthest_distance
    ])

    remaining = [point for point in floor if point not in (first, second)]
    pickups = rng.sample(remaining, health_count + ammo_count)
    grid = [list(row) for row in canonical_map.grid]

    for x, y in (first, second):
        grid[y][x] = SPAWN
    for x, y in pickups[:health_count]:
        grid[y][x] = HEALTH
    for x, y in pickups[health_count:]:
        grid[y][x] = AMMO

    return canonical_map.replace_grid("".join(row) for row in grid)