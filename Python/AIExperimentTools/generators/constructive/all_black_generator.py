from __future__ import annotations

import random

from experiment_session import ExperimentSession
from generators.constructive.common import (
    Rect,
    blank_grid,
    carve_corridor,
    carve_rect,
    grid_rows,
    run_constructive,
)
from map_schema.canonical_map import CanonicalMap


def run(base_generator: ExperimentSession) -> list[str]:
    return run_constructive(base_generator, _generate, "all_black")


def _generate(
    width: int,
    height: int,
    rng: random.Random,
    settings: dict,
    map_id: str,
) -> CanonicalMap:
    target_room_count = max(2, int(settings.get("room_count", 10)))
    minimum_room_size = max(3, int(settings.get("minimum_room_size", 4)))
    maximum_room_size = max(minimum_room_size, int(settings.get("maximum_room_size", 10)))
    room_padding = max(0, int(settings.get("room_padding", 1)))
    corridor_width = max(1, int(settings.get("corridor_width", 2)))
    max_attempts = max(target_room_count, int(settings.get("max_placement_attempts", 500)))
    extra_connection_probability = min(
        1.0,
        max(0.0, float(settings.get("extra_connection_probability", 0.15))),
    )

    maximum_allowed_width = width - 4
    maximum_allowed_height = height - 4
    if minimum_room_size > maximum_allowed_width or minimum_room_size > maximum_allowed_height:
        raise ValueError(
            "All-Black minimum_room_size is too large for the configured map dimensions"
        )
    maximum_room_width = min(maximum_room_size, maximum_allowed_width)
    maximum_room_height = min(maximum_room_size, maximum_allowed_height)

    rooms: list[Rect] = []
    attempts = 0
    while len(rooms) < target_room_count and attempts < max_attempts:
        attempts += 1
        room_width = rng.randint(minimum_room_size, maximum_room_width)
        room_height = rng.randint(minimum_room_size, maximum_room_height)
        room = Rect(
            rng.randint(1, width - 1 - room_width),
            rng.randint(1, height - 1 - room_height),
            room_width,
            room_height,
        )
        if any(room.overlaps(existing, room_padding) for existing in rooms):
            continue
        rooms.append(room)

    if len(rooms) < 2:
        fallback_width = max(3, min(maximum_room_size, width // 5))
        fallback_height = max(3, min(maximum_room_size, height // 3))
        rooms = [
            Rect(2, height // 2 - fallback_height // 2, fallback_width, fallback_height),
            Rect(
                width - 2 - fallback_width,
                height // 2 - fallback_height // 2,
                fallback_width,
                fallback_height,
            ),
        ]

    grid = blank_grid(width, height)
    area_encoding: list[dict[str, int | str]] = []
    for room in rooms:
        carve_rect(grid, room)
        area_encoding.append(
            {
                "type": "room",
                "x": room.x,
                "y": room.y,
                "width": room.width,
                "height": room.height,
            }
        )

    selected_edges = _minimum_spanning_edges(rooms)
    for first in range(len(rooms)):
        for second in range(first + 1, len(rooms)):
            edge = (first, second)
            if edge not in selected_edges and rng.random() < extra_connection_probability / max(1, len(rooms)):
                selected_edges.add(edge)

    corridor_segments = 0
    for first, second in sorted(selected_edges):
        segments = carve_corridor(
            grid,
            rooms[first].center,
            rooms[second].center,
            corridor_width,
            horizontal_first=bool(rng.getrandbits(1)),
        )
        corridor_segments += len(segments)
        for segment in segments:
            area_encoding.append(
                {
                    "type": "corridor",
                    "x": segment.x,
                    "y": segment.y,
                    "width": segment.width,
                    "height": segment.height,
                }
            )

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=grid_rows(grid),
        metadata={
            "genome_representation_type": "all_black_constructive",
            "room_count": len(rooms),
            "corridor_count": len(selected_edges),
            "all_black_area_count": len(area_encoding),
            "all_black_areas": area_encoding,
            "placement_attempts": attempts,
            "corridor_rectangle_count": corridor_segments,
        },
    )


def _minimum_spanning_edges(rooms: list[Rect]) -> set[tuple[int, int]]:
    connected = {0}
    remaining = set(range(1, len(rooms)))
    edges: set[tuple[int, int]] = set()
    while remaining:
        first, second = min(
            ((a, b) for a in connected for b in remaining),
            key=lambda pair: _distance_sq(rooms[pair[0]].center, rooms[pair[1]].center),
        )
        edges.add(tuple(sorted((first, second))))
        connected.add(second)
        remaining.remove(second)
    return edges


def _distance_sq(first: tuple[int, int], second: tuple[int, int]) -> int:
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2
