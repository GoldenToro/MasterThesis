from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Iterable


WALL = "#"
FLOOR = "."
SPAWN = "S"
HEALTH = "H"
AMMO = "A"
ALLOWED_SYMBOLS = frozenset({WALL, FLOOR, SPAWN, HEALTH, AMMO})
WALKABLE_SYMBOLS = frozenset({FLOOR, SPAWN, HEALTH, AMMO})


@dataclass(frozen=True)
class CanonicalMap:
    map_id: str
    width: int
    height: int
    grid: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Map width and height must be positive")
        if len(self.grid) != self.height:
            raise ValueError(f"Expected {self.height} grid rows, received {len(self.grid)}")
        for index, row in enumerate(self.grid):
            if len(row) != self.width:
                raise ValueError(
                    f"Grid row {index} has width {len(row)} instead of {self.width}"
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalMap":
        return cls(
            map_id=str(data.get("map_id", "map")),
            width=int(data["width"]),
            height=int(data["height"]),
            grid=tuple(str(row) for row in data["grid"]),
            metadata=dict(data.get("metadata", {})),
            schema_version=str(data.get("schema_version", "1.0")),
        )

    @classmethod
    def from_area_rectangles(
        cls,
        map_id: str,
        width: int,
        height: int,
        areas: Iterable[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> "CanonicalMap":
        grid = [[WALL for _ in range(width)] for _ in range(height)]
        for area in areas:
            left = max(0, int(area["leftColumn"]))
            right = min(width, int(area["rightColumn"]))
            bottom = max(0, int(area["bottomRow"]))
            top = min(height, int(area["topRow"]))
            for unity_y in range(bottom, top):
                canonical_y = height - 1 - unity_y
                for x in range(left, right):
                    grid[canonical_y][x] = FLOOR
        return cls(
            map_id=map_id,
            width=width,
            height=height,
            grid=tuple("".join(row) for row in grid),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "map_id": self.map_id,
            "width": self.width,
            "height": self.height,
            "grid": list(self.grid),
            "metadata": self.metadata,
        }

    def iter_cells(self):
        for y, row in enumerate(self.grid):
            for x, symbol in enumerate(row):
                yield x, y, symbol

    def cells_with(self, symbols: Iterable[str]) -> list[tuple[int, int]]:
        symbol_set = set(symbols)
        return [(x, y) for x, y, value in self.iter_cells() if value in symbol_set]

    def walkable_cells(self) -> list[tuple[int, int]]:
        return self.cells_with(WALKABLE_SYMBOLS)

    def grid_bytes(self) -> bytes:
        return "\n".join(self.grid).encode("utf-8")

    def content_hash(self) -> str:
        return sha256(self.grid_bytes()).hexdigest()

    def replace_grid(
        self,
        grid: Iterable[str],
        metadata_updates: dict[str, Any] | None = None,
    ) -> "CanonicalMap":
        metadata = dict(self.metadata)
        metadata.update(metadata_updates or {})
        return CanonicalMap(
            map_id=self.map_id,
            width=self.width,
            height=self.height,
            grid=tuple(grid),
            metadata=metadata,
            schema_version=self.schema_version,
        )
