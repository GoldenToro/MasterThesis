from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from math import ceil, floor
from typing import Any

from generators.llm_map_creator.schemas import DirectCanonicalMapResponse
from map_schema.canonical_map import (
    ALLOWED_SYMBOLS,
    FLOOR,
    SPAWN,
    WALL,
    WALKABLE_SYMBOLS,
    CanonicalMap,
)


@dataclass
class ProcessingReport:
    changed: bool
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DirectMapProcessor:
    """Normalize and repair one complete LLM grid in deterministic linear passes."""

    def __init__(self, width: int, height: int, validation: dict[str, Any]):
        if width < 5 or height < 5:
            raise ValueError("Direct LLM maps require width and height of at least 5")
        self.width = int(width)
        self.height = int(height)
        self.validation = dict(validation)

    def normalize(
        self,
        response: DirectCanonicalMapResponse,
        *,
        map_id: str,
        metadata: dict[str, Any],
    ) -> tuple[CanonicalMap, ProcessingReport]:
        actions: list[str] = []
        rows = list(response.grid)

        if response.width != self.width:
            actions.append(
                f"Replaced response width {response.width} with configured width {self.width}"
            )
        if response.height != self.height:
            actions.append(
                f"Replaced response height {response.height} with configured height {self.height}"
            )

        if len(rows) > self.height:
            rows = rows[: self.height]
            actions.append("Removed extra grid rows")
        elif len(rows) < self.height:
            rows.extend(WALL * self.width for _ in range(self.height - len(rows)))
            actions.append("Added missing grid rows as walls")

        normalized_rows: list[str] = []
        replaced_symbols = 0
        width_fixes = 0
        for row in rows:
            text = str(row)
            if len(text) > self.width:
                text = text[: self.width]
                width_fixes += 1
            elif len(text) < self.width:
                text = text + WALL * (self.width - len(text))
                width_fixes += 1

            sanitized = []
            for symbol in text:
                if symbol in ALLOWED_SYMBOLS:
                    sanitized.append(symbol)
                else:
                    sanitized.append(WALL)
                    replaced_symbols += 1
            normalized_rows.append("".join(sanitized))

        if width_fixes:
            actions.append(f"Corrected the width of {width_fixes} grid rows")
        if replaced_symbols:
            actions.append(
                f"Replaced {replaced_symbols} unsupported grid symbols with walls"
            )

        merged_metadata = dict(metadata)
        merged_metadata.update(
            {
                "llm_suggested_map_id": response.map_id,
                "llm_design_summary": response.metadata.design_summary,
                "llm_features": list(response.metadata.features),
                "llm_response_width": response.width,
                "llm_response_height": response.height,
            }
        )
        canonical_map = CanonicalMap(
            map_id=map_id,
            width=self.width,
            height=self.height,
            grid=tuple(normalized_rows),
            metadata=merged_metadata,
            schema_version="1.0",
        )
        return canonical_map, ProcessingReport(changed=bool(actions), actions=actions)

    def repair(
        self,
        canonical_map: CanonicalMap,
        *,
        minimum_spawn_count: int,
    ) -> tuple[CanonicalMap, ProcessingReport]:
        grid = [list(row) for row in canonical_map.grid]
        actions: list[str] = []

        sealed = self._seal_border(grid)
        if sealed:
            actions.append(f"Sealed {sealed} border cells")

        if self._walkable_cells(grid):
            pass
        else:
            center_x = self.width // 2
            center_y = self.height // 2
            for y in range(max(1, center_y - 1), min(self.height - 1, center_y + 2)):
                for x in range(max(1, center_x - 1), min(self.width - 1, center_x + 2)):
                    grid[y][x] = FLOOR
            actions.append("Carved a central walkable seed region")

        connected = self._connect_regions(grid)
        if connected:
            actions.append(f"Connected {connected} separated walkable regions")

        total_tiles = self.width * self.height
        minimum_ratio = float(self.validation.get("minimum_walkable_ratio", 0.0))
        maximum_ratio = float(self.validation.get("maximum_walkable_ratio", 1.0))
        minimum_tiles = ceil(minimum_ratio * total_tiles)
        maximum_tiles = floor(maximum_ratio * total_tiles)

        walkable_count = len(self._walkable_cells(grid))
        if walkable_count < minimum_tiles:
            added = self._grow_connected_region(grid, minimum_tiles)
            if added:
                actions.append(
                    f"Added {added} connected floor cells to reach the minimum walkable ratio"
                )

        walkable_count = len(self._walkable_cells(grid))
        if walkable_count > maximum_tiles:
            removed = self._shrink_connected_region(grid, maximum_tiles)
            if removed:
                actions.append(
                    f"Removed {removed} walkable cells to reach the maximum walkable ratio"
                )

        added_spawns = self._add_missing_spawns(grid, minimum_spawn_count)
        if added_spawns:
            actions.append(f"Added {added_spawns} spawn markers")

        sealed_after = self._seal_border(grid)
        if sealed_after:
            actions.append(f"Resealed {sealed_after} border cells")

        repaired = canonical_map.replace_grid(
            ("".join(row) for row in grid),
            {"generation_repair_actions": actions},
        )
        return repaired, ProcessingReport(changed=bool(actions), actions=actions)

    def _seal_border(self, grid: list[list[str]]) -> int:
        changed = 0
        for x in range(self.width):
            for y in (0, self.height - 1):
                if grid[y][x] != WALL:
                    grid[y][x] = WALL
                    changed += 1
        for y in range(1, self.height - 1):
            for x in (0, self.width - 1):
                if grid[y][x] != WALL:
                    grid[y][x] = WALL
                    changed += 1
        return changed

    @staticmethod
    def _walkable_cells(grid: list[list[str]]) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y, row in enumerate(grid)
            for x, value in enumerate(row)
            if value in WALKABLE_SYMBOLS
        ]

    def _connect_regions(self, grid: list[list[str]]) -> int:
        components = self._components(grid)
        if len(components) <= 1:
            return 0

        largest = max(components, key=len)
        anchor = min(largest, key=lambda point: (point[1], point[0]))
        connected = 0
        for component in sorted(
            (value for value in components if value is not largest),
            key=lambda value: min((point[1], point[0]) for point in value),
        ):
            start = min(
                component,
                key=lambda point: (
                    abs(point[0] - anchor[0]) + abs(point[1] - anchor[1]),
                    point[1],
                    point[0],
                ),
            )
            self._carve_manhattan(grid, start, anchor)
            connected += 1
        return connected

    def _components(self, grid: list[list[str]]) -> list[set[tuple[int, int]]]:
        remaining = set(self._walkable_cells(grid))
        components: list[set[tuple[int, int]]] = []
        while remaining:
            start = min(remaining, key=lambda point: (point[1], point[0]))
            remaining.remove(start)
            component = {start}
            queue = deque([start])
            while queue:
                x, y = queue.popleft()
                for point in self._neighbors(x, y):
                    if point in remaining:
                        remaining.remove(point)
                        component.add(point)
                        queue.append(point)
            components.append(component)
        return components

    def _carve_manhattan(
        self,
        grid: list[list[str]],
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        x, y = start
        end_x, end_y = end
        while x != end_x:
            if grid[y][x] == WALL:
                grid[y][x] = FLOOR
            x += 1 if end_x > x else -1
        while y != end_y:
            if grid[y][x] == WALL:
                grid[y][x] = FLOOR
            y += 1 if end_y > y else -1
        if grid[y][x] == WALL:
            grid[y][x] = FLOOR

    def _add_missing_spawns(
        self,
        grid: list[list[str]],
        minimum_spawn_count: int,
    ) -> int:
        selected = [
            (x, y)
            for y, row in enumerate(grid)
            for x, value in enumerate(row)
            if value == SPAWN
        ]
        candidates = self._walkable_cells(grid)
        added = 0
        while len(selected) < minimum_spawn_count and candidates:
            if selected:
                candidate = max(
                    candidates,
                    key=lambda point: (
                        min(
                            abs(point[0] - other[0]) + abs(point[1] - other[1])
                            for other in selected
                        ),
                        -point[1],
                        -point[0],
                    ),
                )
            else:
                candidate = candidates[len(candidates) // 2]
            grid[candidate[1]][candidate[0]] = SPAWN
            selected.append(candidate)
            candidates = [point for point in candidates if point != candidate]
            added += 1
        return added

    def _grow_connected_region(
        self,
        grid: list[list[str]],
        target_count: int,
    ) -> int:
        walkable = set(self._walkable_cells(grid))
        queue: deque[tuple[int, int]] = deque(sorted(walkable, key=lambda p: (p[1], p[0])))
        queued = set(queue)
        added = 0

        while queue and len(walkable) < target_count:
            x, y = queue.popleft()
            for nx, ny in self._neighbors(x, y):
                point = (nx, ny)
                if point in queued:
                    continue
                queued.add(point)
                if grid[ny][nx] == WALL:
                    grid[ny][nx] = FLOOR
                    walkable.add(point)
                    added += 1
                    queue.append(point)
                    if len(walkable) >= target_count:
                        break
                elif grid[ny][nx] in WALKABLE_SYMBOLS:
                    queue.append(point)
        return added

    def _shrink_connected_region(
        self,
        grid: list[list[str]],
        target_count: int,
    ) -> int:
        walkable = set(self._walkable_cells(grid))
        if len(walkable) <= target_count:
            return 0

        spawns = sorted(
            ((x, y) for x, y in walkable if grid[y][x] == SPAWN),
            key=lambda point: (point[1], point[0]),
        )
        root = spawns[0] if spawns else min(walkable, key=lambda p: (p[1], p[0]))
        parents = self._bfs_parents(root, walkable)

        keep = {root}
        for spawn in spawns:
            current = spawn
            keep.add(current)
            while current != root and current in parents:
                current = parents[current]
                keep.add(current)

        queue: deque[tuple[int, int]] = deque(sorted(keep, key=lambda p: (p[1], p[0])))
        queued = set(queue)
        while queue and len(keep) < target_count:
            x, y = queue.popleft()
            for point in self._neighbors(x, y):
                if point in queued or point not in walkable:
                    continue
                queued.add(point)
                keep.add(point)
                queue.append(point)
                if len(keep) >= target_count:
                    break

        removable = walkable - keep
        for x, y in removable:
            grid[y][x] = WALL
        return len(removable)

    def _bfs_parents(
        self,
        root: tuple[int, int],
        walkable: set[tuple[int, int]],
    ) -> dict[tuple[int, int], tuple[int, int]]:
        queue = deque([root])
        visited = {root}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        while queue:
            x, y = queue.popleft()
            for point in self._neighbors(x, y):
                if point in walkable and point not in visited:
                    visited.add(point)
                    parents[point] = (x, y)
                    queue.append(point)
        return parents

    def _neighbors(self, x: int, y: int):
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 1 <= nx < self.width - 1 and 1 <= ny < self.height - 1:
                yield nx, ny
