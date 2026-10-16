from __future__ import annotations

import random
from collections.abc import Iterator

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


def run(base_generator: ExperimentSession) -> [list[str]]:
    return run_constructive(base_generator, _generate, "fps_pattern")


def _generate(
        width: int,
        height: int,
        rng: random.Random,
        settings: dict,
        map_id: str,
) -> CanonicalMap:
    if width < 24 or height < 18:
        raise ValueError(
            "FPS pattern generator requires map dimensions of at least 24x18"
        )

    corridor_min = settings.get(
        "corridor_width_min", settings.get("corridor_width", 2)
    )
    corridor_max = settings.get(
        "corridor_width_max", settings.get("corridor_width", 2)
    )
    route_min = settings.get(
        "route_count_min", settings.get("route_count", 2)
    )
    route_max = settings.get(
        "route_count_max", settings.get("route_count", 3)
    )

    if any(
            type(value) is not int
            for value in (corridor_min, corridor_max, route_min, route_max)
    ):
        raise ValueError("Corridor widths and route counts must be integers")

    if not 1 <= corridor_min <= corridor_max <= 6:
        raise ValueError(
            "Corridor widths must satisfy 1 <= min <= max <= 6"
        )

    if not 2 <= route_min <= route_max <= 3:
        raise ValueError("FPS patterns support route counts of 2 or 3")

    corridor_width = rng.randint(corridor_min, corridor_max)
    route_count = rng.randint(route_min, route_max)

    side_width = max(5, width // 8)
    side_height = max(6, height // 3)
    arena_width = max(7, width // 4)
    arena_height = max(7, height // 3)
    support_width = max(5, width // 7)
    support_height = max(4, height // 5)

    center_y = height // 2
    left_room = Rect(
        2,
        center_y - side_height // 2,
        side_width,
        side_height,
        )
    right_room = Rect(
        width - 2 - side_width,
        center_y - side_height // 2,
        side_width,
        side_height,
        )
    arena = Rect(
        width // 2 - arena_width // 2,
        center_y - arena_height // 2,
        arena_width,
        arena_height,
        )
    top_room = Rect(
        width // 2 - support_width // 2,
        2,
        support_width,
        support_height,
        )
    bottom_room = Rect(
        width // 2 - support_width // 2,
        height - 2 - support_height,
        support_width,
        support_height,
        )

    rooms = [left_room, right_room, arena, top_room, bottom_room]
    grid = blank_grid(width, height)
    for room in rooms:
        carve_rect(grid, room)

    connections: list[tuple[tuple[int, int], tuple[int, int]]] = []

    def connect(
            first: tuple[int, int],
            second: tuple[int, int],
            horizontal_first: bool,
    ) -> None:
        carve_corridor(
            grid,
            first,
            second,
            corridor_width,
            horizontal_first=horizontal_first,
        )
        connections.append((first, second))

    # The three-route pattern includes a direct middle lane.
    if route_count == 3:
        connect(left_room.center, arena.center, True)
        connect(arena.center, right_room.center, True)

    # Both patterns include upper and lower flank lanes.
    top_lane_y = top_room.center[1]
    bottom_lane_y = bottom_room.center[1]

    connect(left_room.center, (left_room.center[0], top_lane_y), False)
    connect((left_room.center[0], top_lane_y), top_room.center, True)
    connect(top_room.center, (right_room.center[0], top_lane_y), True)
    connect((right_room.center[0], top_lane_y), right_room.center, False)

    connect(left_room.center, (left_room.center[0], bottom_lane_y), False)
    connect((left_room.center[0], bottom_lane_y), bottom_room.center, True)
    connect(bottom_room.center, (right_room.center[0], bottom_lane_y), True)
    connect((right_room.center[0], bottom_lane_y), right_room.center, False)

    # Make the central arena accessible in both patterns.
    connect(top_room.center, (arena.center[0], arena.y), False)
    connect(bottom_room.center, (arena.center[0], arena.bottom - 1), False)

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=grid_rows(grid),
        metadata={
            "genome_representation_type": "fps_pattern_rules",
            "room_count": len(rooms),
            "corridor_count": len(connections),
            "fps_pattern": "symmetric_multi_route",
            "route_count": route_count,
            "corridor_width": corridor_width,
        },
    )