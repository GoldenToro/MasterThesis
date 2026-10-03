from __future__ import annotations

from collections import deque
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


class MapValidator:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def validate(self, canonical_map: CanonicalMap) -> ValidationReport:
        errors: list[str] = []
        warnings: list[str] = []
        for name in ("width", "height"):
            expected = self.settings.get(f"expected_{name}")
            actual = getattr(canonical_map, name)
            if expected is not None and actual != expected:
                errors.append(
                    f"Map {name} is {actual}, expected {expected}"
                )

        invalid_symbols = sorted(
            {symbol for _, _, symbol in canonical_map.iter_cells() if symbol not in ALLOWED_SYMBOLS}
        )
        if invalid_symbols:
            errors.append(f"Unsupported grid symbols: {invalid_symbols}")

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
        return ValidationReport(valid=len(errors) == 0, errors=errors, warnings=warnings, measured=measured)

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
