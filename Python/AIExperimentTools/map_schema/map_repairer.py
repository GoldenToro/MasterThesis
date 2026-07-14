from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from map_schema.canonical_map import ALLOWED_SYMBOLS, FLOOR, SPAWN, WALL, WALKABLE_SYMBOLS, CanonicalMap


@dataclass
class RepairReport:
    changed: bool
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MapRepairer:
    """Deterministic, intentionally conservative repairs for generated grids."""

    def repair(
        self,
        canonical_map: CanonicalMap,
        minimum_spawn_count: int = 2,
    ) -> tuple[CanonicalMap, RepairReport]:
        grid = [list(row) for row in canonical_map.grid]
        actions: list[str] = []

        replacements = 0
        for y, row in enumerate(grid):
            for x, symbol in enumerate(row):
                if symbol not in ALLOWED_SYMBOLS:
                    grid[y][x] = WALL
                    replacements += 1
        if replacements:
            actions.append(f"Replaced {replacements} unsupported symbols with walls")

        components = self._components(grid)
        while len(components) > 1:
            first = components[0]
            second = min(
                components[1:],
                key=lambda component: self._component_distance(first, component),
            )
            start, end = self._closest_pair(first, second)
            self._carve_manhattan(grid, start, end)
            actions.append(f"Connected regions from {start} to {end}")
            components = self._components(grid)

        spawns = self._cells(grid, {SPAWN})
        walkable = self._cells(grid, WALKABLE_SYMBOLS)
        while len(spawns) < minimum_spawn_count and walkable:
            candidate = self._farthest_cell(walkable, spawns)
            grid[candidate[1]][candidate[0]] = SPAWN
            spawns.append(candidate)
            actions.append(f"Added spawn marker at {candidate}")

        repaired = canonical_map.replace_grid(
            ("".join(row) for row in grid),
            {"repair_actions": actions},
        )
        return repaired, RepairReport(changed=bool(actions), actions=actions)

    @staticmethod
    def _cells(grid: list[list[str]], symbols) -> list[tuple[int, int]]:
        accepted = set(symbols)
        return [
            (x, y)
            for y, row in enumerate(grid)
            for x, value in enumerate(row)
            if value in accepted
        ]

    @classmethod
    def _components(cls, grid: list[list[str]]) -> list[set[tuple[int, int]]]:
        height = len(grid)
        width = len(grid[0])
        remaining = set(cls._cells(grid, WALKABLE_SYMBOLS))
        components: list[set[tuple[int, int]]] = []
        while remaining:
            start = next(iter(remaining))
            queue = deque([start])
            component = {start}
            remaining.remove(start)
            while queue:
                x, y = queue.popleft()
                for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    nx, ny = neighbor
                    if 0 <= nx < width and 0 <= ny < height and neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        queue.append(neighbor)
            components.append(component)
        return components

    @staticmethod
    def _component_distance(
        first: set[tuple[int, int]], second: set[tuple[int, int]]
    ) -> int:
        return min(abs(ax - bx) + abs(ay - by) for ax, ay in first for bx, by in second)

    @staticmethod
    def _closest_pair(
        first: set[tuple[int, int]], second: set[tuple[int, int]]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        return min(
            ((a, b) for a in first for b in second),
            key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]),
        )

    @staticmethod
    def _carve_manhattan(
        grid: list[list[str]], start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        x, y = start
        end_x, end_y = end
        step_x = 1 if end_x >= x else -1
        while x != end_x:
            if grid[y][x] == WALL:
                grid[y][x] = FLOOR
            x += step_x
        step_y = 1 if end_y >= y else -1
        while y != end_y:
            if grid[y][x] == WALL:
                grid[y][x] = FLOOR
            y += step_y
        if grid[y][x] == WALL:
            grid[y][x] = FLOOR

    @staticmethod
    def _farthest_cell(
        candidates: list[tuple[int, int]], selected: list[tuple[int, int]]
    ) -> tuple[int, int]:
        if selected:
            return max(
                candidates,
                key=lambda candidate: min(
                    abs(candidate[0] - point[0]) + abs(candidate[1] - point[1])
                    for point in selected
                ),
            )
        return candidates[len(candidates) // 2]
