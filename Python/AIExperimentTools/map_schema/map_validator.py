from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from map_schema.canonical_map import ALLOWED_SYMBOLS, SPAWN, WALKABLE_SYMBOLS, CanonicalMap


@dataclass
class ValidationReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MapValidationError(ValueError):
    """A map failed validation with one or more independently reported errors."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class MapValidator:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def validate(self, canonical_map: CanonicalMap) -> ValidationReport:
        errors = self.validate_structure(canonical_map)
        if errors:
            return ValidationReport(valid=False, errors=errors)
        warnings: list[str] = []

        walkable = set(canonical_map.walkable_cells())
        total_tiles = canonical_map.width * canonical_map.height
        walkable_ratio = len(walkable) / total_tiles
        components = self._components(walkable, canonical_map.width, canonical_map.height)
        spawn_count = len(canonical_map.cells_with({SPAWN}))

        minimum_spawn_count = int(self.settings.get("minimum_spawn_count", 2))
        if spawn_count < minimum_spawn_count:
            errors.append(
                f"Map has {spawn_count} spawn markers, requires at least {minimum_spawn_count}"
            )

        minimum_ratio = float(self.settings.get("minimum_walkable_ratio", 0.0))
        maximum_ratio = float(self.settings.get("maximum_walkable_ratio", 1.0))
        if walkable_ratio < minimum_ratio:
            errors.append(
                f"Walkable ratio {walkable_ratio:.4f} is below {minimum_ratio:.4f}"
            )
        if walkable_ratio > maximum_ratio:
            errors.append(
                f"Walkable ratio {walkable_ratio:.4f} is above {maximum_ratio:.4f}"
            )

        if bool(self.settings.get("require_single_connected_region", True)) and len(components) != 1:
            errors.append(f"Walkable layout contains {len(components)} connected regions")

        border_openings = sum(
            1
            for x, y in walkable
            if x in (0, canonical_map.width - 1) or y in (0, canonical_map.height - 1)
        )
        if border_openings:
            warnings.append(f"Map has {border_openings} walkable border cells")

        measured = {
            "total_tiles": total_tiles,
            "walkable_tiles": len(walkable),
            "walkable_ratio": walkable_ratio,
            "connected_components": len(components),
            "largest_component_tiles": max((len(component) for component in components), default=0),
            "spawn_count": spawn_count,
            "border_openings": border_openings,
        }
        minimum_regions = self.settings.get("minimum_room_regions", 0)
        if type(minimum_regions) is not int or minimum_regions < 0:
            raise ValueError("minimum_room_regions must be a non-negative integer")
        if minimum_regions:
            window = self.settings.get("room_region_window", 4)
            minimum_area = self.settings.get("minimum_room_region_area", 16)
            regions = self.room_regions(canonical_map, window, minimum_area)
            measured.update(
                room_region_count=len(regions),
                room_region_core_areas=sorted((len(region) for region in regions), reverse=True),
                room_region_window=window,
                minimum_room_region_area=minimum_area,
            )
            if len(regions) < minimum_regions:
                errors.append(
                    f"Map has {len(regions)} broad room regions, requires at least {minimum_regions} "
                    f"({window}x{window} floor windows; minimum {minimum_area} connected window positions)"
                )
        return ValidationReport(valid=len(errors) == 0, errors=errors, warnings=warnings, measured=measured)

    def validate_structure(
        self,
        canonical_map: CanonicalMap,
        *,
        allowed_symbols: frozenset[str] = ALLOWED_SYMBOLS,
    ) -> list[str]:
        return self.validate_grid(
            canonical_map.width, canonical_map.height, canonical_map.grid,
            allowed_symbols=allowed_symbols,
        )

    def validate_grid(
        self,
        width: int,
        height: int,
        grid: Sequence[str],
        *,
        allowed_symbols: frozenset[str] = ALLOWED_SYMBOLS,
    ) -> list[str]:
        """Collect structural errors before constructing a CanonicalMap."""

        errors: list[str] = []
        for name, actual in (("width", width), ("height", height)):
            if actual <= 0:
                errors.append(f"Map {name} must be positive, received {actual}")
            expected = self.settings.get(f"expected_{name}")
            if expected is not None and actual != expected:
                errors.append(f"Map {name} is {actual}, expected {expected}")
        if len(grid) != height:
            errors.append(f"Expected {height} grid rows, received {len(grid)}")
        for index, row in enumerate(grid):
            if len(row) != width:
                errors.append(f"Grid row {index} has width {len(row)} instead of {width}")
        invalid_symbols = sorted({
            symbol for row in grid for symbol in row
            if symbol not in allowed_symbols
        })
        if invalid_symbols:
            errors.append(f"Unsupported grid symbols: {invalid_symbols}")
        return errors

    @staticmethod
    def room_regions(
        canonical_map: CanonicalMap, window_size: int = 4, minimum_area: int = 16
    ) -> list[set[tuple[int, int]]]:

        if type(window_size) is not int or window_size < 2:
            raise ValueError("room_region_window must be an integer of at least two")
        if type(minimum_area) is not int or minimum_area < 1:
            raise ValueError("minimum_room_region_area must be a positive integer")
        floor = set(canonical_map.walkable_cells())
        cores = {
            (x, y) for x, y in floor
            if all((x + dx, y + dy) in floor
                   for dy in range(window_size) for dx in range(window_size))
        }
        return [
            component
            for component in MapValidator._components(cores, canonical_map.width, canonical_map.height)
            if len(component) >= minimum_area
        ]

    @staticmethod
    def _components(
        walkable: set[tuple[int, int]], width: int, height: int
    ) -> list[set[tuple[int, int]]]:
        remaining = set(walkable)
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
