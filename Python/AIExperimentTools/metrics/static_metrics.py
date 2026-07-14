from __future__ import annotations

from collections import deque
from math import hypot
from random import Random
from statistics import mean
from typing import Iterable

from map_schema.canonical_map import AMMO, COVER, HEALTH, SPAWN, WALL, WALKABLE_SYMBOLS, CanonicalMap


def calculate_static_metrics(
    canonical_map: CanonicalMap,
    visibility_sample_limit: int = 192,
    eccentricity_sample_limit: int = 128,
) -> dict[str, float | int]:
    walkable = set(canonical_map.walkable_cells())
    total_tiles = canonical_map.width * canonical_map.height
    components = _components(walkable)
    largest_component = max((len(component) for component in components), default=0)
    edges = _edge_count(walkable)
    cycle_rank = max(0, edges - len(walkable) + len(components))
    articulation_points = _articulation_points(walkable)

    x_symmetry = _axis_symmetry(canonical_map, horizontal=False)
    y_symmetry = _axis_symmetry(canonical_map, horizontal=True)

    graph_distances = _distance_metrics(walkable, eccentricity_sample_limit)
    visibility = _visibility_metrics(canonical_map, walkable, visibility_sample_limit)
    spawn_metrics = _spawn_metrics(canonical_map, walkable)

    direct_counts = {
        "map_width": canonical_map.width,
        "map_height": canonical_map.height,
        "total_tile_count": total_tiles,
        "walkable_tile_count": len(walkable),
        "wall_tile_count": sum(1 for _, _, value in canonical_map.iter_cells() if value == WALL),
        "spawn_count": len(canonical_map.cells_with({SPAWN})),
        "cover_object_count": len(canonical_map.cells_with({COVER})),
        "health_pickup_count": len(canonical_map.cells_with({HEALTH})),
        "ammo_pickup_count": len(canonical_map.cells_with({AMMO})),
    }

    calculated = {
        "walkable_area_ratio": len(walkable) / total_tiles,
        "largest_navigable_region_ratio": largest_component / len(walkable) if walkable else 0.0,
        "connectivity": 1.0 if len(components) == 1 else 0.0,
        "number_of_connected_components": len(components),
        "symmetry_x": x_symmetry,
        "symmetry_y": y_symmetry,
        "max_symmetry": max(x_symmetry, y_symmetry),
        "graph_edge_count": edges,
        "graph_density": (2 * edges / (len(walkable) * (len(walkable) - 1))) if len(walkable) > 1 else 0.0,
        "loop_count": cycle_rank,
        "chokepoint_count": len(articulation_points),
        "cover_density": direct_counts["cover_object_count"] / len(walkable) if walkable else 0.0,
    }
    return {**direct_counts, **calculated, **graph_distances, **visibility, **spawn_metrics}


def _neighbors(cell: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    x, y = cell
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


def _components(walkable: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(walkable)
    result: list[set[tuple[int, int]]] = []
    while remaining:
        start = next(iter(remaining))
        queue = deque([start])
        component = {start}
        remaining.remove(start)
        while queue:
            current = queue.popleft()
            for neighbor in _neighbors(current):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        result.append(component)
    return result


def _edge_count(walkable: set[tuple[int, int]]) -> int:
    return sum(
        1
        for x, y in walkable
        for neighbor in ((x + 1, y), (x, y + 1))
        if neighbor in walkable
    )


def _axis_symmetry(canonical_map: CanonicalMap, horizontal: bool) -> float:
    matches = 0
    comparisons = 0
    for y in range(canonical_map.height):
        for x in range(canonical_map.width):
            other_x = x if horizontal else canonical_map.width - 1 - x
            other_y = canonical_map.height - 1 - y if horizontal else y
            first = canonical_map.grid[y][x] in WALKABLE_SYMBOLS
            second = canonical_map.grid[other_y][other_x] in WALKABLE_SYMBOLS
            matches += int(first == second)
            comparisons += 1
    return matches / comparisons if comparisons else 0.0


def _bfs_distances(
    start: tuple[int, int], walkable: set[tuple[int, int]]
) -> dict[tuple[int, int], int]:
    distances = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in _neighbors(current):
            if neighbor in walkable and neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def _distance_metrics(
    walkable: set[tuple[int, int]], sample_limit: int
) -> dict[str, float | int]:
    if not walkable:
        return {"average_eccentricity": 0.0, "graph_diameter": 0, "graph_radius": 0, "average_degree_centrality": 0.0}
    cells = sorted(walkable)
    if len(cells) > sample_limit:
        step = len(cells) / sample_limit
        cells = [cells[int(index * step)] for index in range(sample_limit)]
    eccentricities = []
    for cell in cells:
        distances = _bfs_distances(cell, walkable)
        eccentricities.append(max(distances.values(), default=0))
    degrees = [sum(1 for neighbor in _neighbors(cell) if neighbor in walkable) for cell in walkable]
    return {
        "average_eccentricity": mean(eccentricities),
        "graph_diameter": max(eccentricities),
        "graph_radius": min(eccentricities),
        "average_degree_centrality": mean(degrees) / 4.0,
    }


def _articulation_points(walkable: set[tuple[int, int]]) -> set[tuple[int, int]]:
    discovery: dict[tuple[int, int], int] = {}
    low: dict[tuple[int, int], int] = {}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}
    points: set[tuple[int, int]] = set()
    time = 0

    def visit(node: tuple[int, int]) -> None:
        nonlocal time
        discovery[node] = low[node] = time
        time += 1
        children = 0
        for neighbor in _neighbors(node):
            if neighbor not in walkable:
                continue
            if neighbor not in discovery:
                parent[neighbor] = node
                children += 1
                visit(neighbor)
                low[node] = min(low[node], low[neighbor])
                if parent.get(node) is None and children > 1:
                    points.add(node)
                if parent.get(node) is not None and low[neighbor] >= discovery[node]:
                    points.add(node)
            elif neighbor != parent.get(node):
                low[node] = min(low[node], discovery[neighbor])

    for node in walkable:
        if node not in discovery:
            parent[node] = None
            visit(node)
    return points


def _visibility_metrics(
    canonical_map: CanonicalMap,
    walkable: set[tuple[int, int]],
    sample_limit: int,
) -> dict[str, float]:
    if not walkable:
        return {"average_visibility": 0.0, "maximum_visibility": 0.0}
    cells = sorted(walkable)
    rng = Random(0)
    if len(cells) > sample_limit:
        cells = rng.sample(cells, sample_limit)
    visible_ratios = []
    for source in cells:
        visible = sum(1 for target in cells if _line_of_sight(canonical_map, source, target))
        visible_ratios.append(visible / len(cells))
    return {
        "average_visibility": mean(visible_ratios),
        "maximum_visibility": max(visible_ratios),
    }


def _line_of_sight(
    canonical_map: CanonicalMap,
    start: tuple[int, int],
    end: tuple[int, int],
) -> bool:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        if (x0, y0) not in (start, end) and canonical_map.grid[y0][x0] == WALL:
            return False
        if x0 == x1 and y0 == y1:
            return True
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def _spawn_metrics(
    canonical_map: CanonicalMap,
    walkable: set[tuple[int, int]],
) -> dict[str, float | int]:
    spawns = canonical_map.cells_with({SPAWN})
    if len(spawns) < 2:
        return {
            "spawn_shortest_path": 0,
            "spawn_distance_normalized": 0.0,
            "spawn_exposure": 0.0,
            "spawn_escape_routes_average": 0.0,
        }
    distances = _bfs_distances(spawns[0], walkable)
    path_length = distances.get(spawns[1], 0)
    diagonal = hypot(canonical_map.width, canonical_map.height)
    sample = sorted(walkable)
    if len(sample) > 192:
        sample = sample[:: max(1, len(sample) // 192)][:192]
    exposures = [
        sum(1 for target in sample if _line_of_sight(canonical_map, spawn, target)) / len(sample)
        for spawn in spawns
    ] if sample else [0.0]
    exits = [sum(1 for neighbor in _neighbors(spawn) if neighbor in walkable) for spawn in spawns]
    return {
        "spawn_shortest_path": path_length,
        "spawn_distance_normalized": path_length / diagonal if diagonal else 0.0,
        "spawn_exposure": mean(exposures),
        "spawn_escape_routes_average": mean(exits),
    }
