from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from map_schema.canonical_map import (
    ALLOWED_SYMBOLS,
    FLOOR,
    WALL,
    CanonicalMap,
)
from map_schema.map_validator import MapValidator


@dataclass
class RepairReport:
    changed: bool
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MapRepairer:
    """Connect walkable regions within an explicit changed-cell limit."""

    def repair(
            self,
            canonical_map: CanonicalMap,
            *,
            max_changed_cells: int,
    ) -> tuple[CanonicalMap, RepairReport]:
        if type(max_changed_cells) is not int or max_changed_cells <= 0:
            raise ValueError("max_changed_cells must be a positive integer")

        unsupported = sorted({
            symbol
            for _, _, symbol in canonical_map.iter_cells()
            if symbol not in ALLOWED_SYMBOLS
        })
        if unsupported:
            raise ValueError(
                f"Repair does not replace unsupported symbols: {unsupported}"
            )

        grid = [list(row) for row in canonical_map.grid]
        walkable = set(canonical_map.walkable_cells())
        components = MapValidator._components(
            walkable,
            canonical_map.width,
            canonical_map.height,
        )
        actions: list[str] = []
        changed_cells = 0

        while len(components) > 1:
            first = min(components, key=lambda component: min(component))
            others = walkable - first

            start, end = min(
                ((a, b) for a in first for b in others),
                key=lambda pair: (
                    abs(pair[0][0] - pair[1][0])
                    + abs(pair[0][1] - pair[1][1]),
                    pair,
                ),
            )

            path = [
                (x, start[1])
                for x in range(
                    min(start[0], end[0]),
                    max(start[0], end[0]) + 1,
                    )
            ]
            path.extend(
                (end[0], y)
                for y in range(
                    min(start[1], end[1]),
                    max(start[1], end[1]) + 1,
                    )
            )
            walls = {
                (x, y)
                for x, y in path
                if grid[y][x] == WALL
            }

            required_changes = changed_cells + len(walls)
            if required_changes > max_changed_cells:
                raise ValueError(
                    "Connecting the regions would exceed "
                    f"the repair limit of {max_changed_cells} changed cells"
                )

            for x, y in walls:
                grid[y][x] = FLOOR

            changed_cells = required_changes
            walkable.update(walls)
            actions.append(f"Connected regions from {start} to {end}")
            components = MapValidator._components(
                walkable,
                canonical_map.width,
                canonical_map.height,
            )

        if not actions:
            return canonical_map, RepairReport(changed=False)

        repaired = canonical_map.replace_grid(
            ("".join(row) for row in grid),
            {"repair_actions": actions},
        )
        return repaired, RepairReport(changed=True, actions=actions)