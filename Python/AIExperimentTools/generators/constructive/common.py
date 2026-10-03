from __future__ import annotations

import json
import random
from collections import deque
from dataclasses import dataclass, replace
from hashlib import sha1
from time import perf_counter
from typing import Callable, Iterable

from candidate import Candidate
from experiment_session import ExperimentSession
from map_schema.canonical_map import FLOOR, WALL, CanonicalMap


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (
            self.x + self.width // 2,
            self.y + self.height // 2,
        )

    def overlaps(self, other: "Rect", padding: int = 0) -> bool:
        return not (
            self.right + padding <= other.x
            or other.right + padding <= self.x
            or self.bottom + padding <= other.y
            or other.bottom + padding <= self.y
        )


MapFactory = Callable[[int, int, random.Random, dict, str], CanonicalMap]
def run_constructive(
    base_generator: ExperimentSession,
    factory: MapFactory,
    source_name: str,
) -> list[str]:
    """Generate one epoch of independent constructive maps and evaluate them."""
    settings = base_generator.generator_settings
    population_size = int(settings["population_size"])
    width = int(settings["map_width"])
    height = int(settings["map_height"])

    if population_size <= 0:
        raise ValueError("population_size must be positive")
    if width < 8 or height < 8:
        raise ValueError(
            "Constructive generators require map dimensions of at least 8x8"
        )

    maps: list[CanonicalMap] = []

    for numeric_id in range(population_size):
        map_id = f"{source_name}_e0000_i{numeric_id:04d}"
        rng = random.Random(
            _derived_seed(base_generator.seed, source_name, numeric_id)
        )

        started = perf_counter()
        canonical_map = factory(width, height, rng, settings, map_id)
        elapsed = perf_counter() - started

        metadata = dict(canonical_map.metadata)
        metadata.update(
            {
                "generator": base_generator.generator_name,
                "constructive_method": source_name,
                "generation_time_seconds": elapsed,
                "epoch": 0,
                "id": numeric_id,
            }
        )
        maps.append(replace(canonical_map, metadata=metadata))

    candidates = [
        Candidate(canonical_map=item)
        for item in maps
    ]
    evaluated = base_generator.evaluate_candidates(candidates, epoch=0)
    final_map_ids = [
        candidate.map_id
        for candidate in evaluated
    ]

    epoch_dir = base_generator.output_dir / "epoch_0000"
    (epoch_dir / "checkpoint_summary.json").write_text(
        json.dumps(
            {
                "epoch": 0,
                "population_size": len(final_map_ids),
                "selected_map_ids": final_map_ids,
                "source": f"constructive_{source_name}",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    yield final_map_ids


def blank_grid(width: int, height: int) -> list[list[str]]:
    return [[WALL for _ in range(width)] for _ in range(height)]


def carve_rect(
    grid: list[list[str]],
    rect: Rect,
    symbol: str = FLOOR,
) -> None:
    height = len(grid)
    width = len(grid[0])
    left = max(1, rect.x)
    right = min(width - 1, rect.right)
    top = max(1, rect.y)
    bottom = min(height - 1, rect.bottom)
    for y in range(top, bottom):
        for x in range(left, right):
            grid[y][x] = symbol


def carve_corridor(
    grid: list[list[str]],
    start: tuple[int, int],
    end: tuple[int, int],
    corridor_width: int = 1,
    horizontal_first: bool = True,
) -> list[Rect]:
    """Carve an L-shaped corridor and return its rectangular segments."""
    corridor_width = max(1, int(corridor_width))
    sx, sy = start
    ex, ey = end
    half = corridor_width // 2
    segments: list[Rect] = []

    if horizontal_first:
        left = min(sx, ex)
        segments.append(Rect(left, sy - half, abs(ex - sx) + 1, corridor_width))
        top = min(sy, ey)
        segments.append(Rect(ex - half, top, corridor_width, abs(ey - sy) + 1))
    else:
        top = min(sy, ey)
        segments.append(Rect(sx - half, top, corridor_width, abs(ey - sy) + 1))
        left = min(sx, ex)
        segments.append(Rect(left, ey - half, abs(ex - sx) + 1, corridor_width))

    for segment in segments:
        carve_rect(grid, segment)
    return segments


def grid_rows(grid: list[list[str]]) -> tuple[str, ...]:
    return tuple("".join(row) for row in grid)


def floor_components(grid: list[list[str]]) -> list[set[tuple[int, int]]]:
    height = len(grid)
    width = len(grid[0])
    remaining = {
        (x, y)
        for y in range(1, height - 1)
        for x in range(1, width - 1)
        if grid[y][x] != WALL
    }
    components: list[set[tuple[int, int]]] = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = deque([start])
        component = {start}
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def connect_components(
    grid: list[list[str]],
    rng: random.Random,
    corridor_width: int = 1,
) -> int:
    """Connect every walkable component to the largest component."""
    corridor_count = 0
    components = floor_components(grid)
    while len(components) > 1:
        main = components[0]
        other = min(
            components[1:],
            key=lambda component: _component_distance(main, component),
        )
        start, end = min(
            ((a, b) for a in main for b in other),
            key=lambda pair: abs(pair[0][0] - pair[1][0])
            + abs(pair[0][1] - pair[1][1]),
        )
        carve_corridor(
            grid,
            start,
            end,
            corridor_width=corridor_width,
            horizontal_first=bool(rng.getrandbits(1)),
        )
        corridor_count += 1
        components = floor_components(grid)
    return corridor_count

def _component_distance(
    first: set[tuple[int, int]],
    second: set[tuple[int, int]],
) -> int:
    return min(
        abs(ax - bx) + abs(ay - by)
        for ax, ay in first
        for bx, by in second
    )


def _derived_seed(base_seed: int, generator: str, numeric_id: int) -> int:
    payload = f"{base_seed}:{generator}:{numeric_id}".encode("utf-8")
    return int(sha1(payload).hexdigest()[:16], 16)
