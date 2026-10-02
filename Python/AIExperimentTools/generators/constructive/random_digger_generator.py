from __future__ import annotations

import random

from experiment_session import ExperimentSession
from generators.constructive.common import (
    Rect,
    blank_grid,
    carve_rect,
    grid_rows,
    run_constructive,
)
from map_schema.canonical_map import FLOOR, CanonicalMap


def run(base_generator: ExperimentSession) -> list[str]:
    return run_constructive(base_generator, _generate, "random_digger")


def _generate(
    width: int,
    height: int,
    rng: random.Random,
    settings: dict,
    map_id: str,
) -> CanonicalMap:
    grid = blank_grid(width, height)
    target_ratio = float(settings.get("target_walkable_ratio", 0.35))
    target_ratio = min(0.9, max(0.05, target_ratio))
    target_tiles = max(1, int((width - 2) * (height - 2) * target_ratio))

    forward = max(0.0, float(settings.get("forward_probability", 0.55)))
    left = max(0.0, float(settings.get("left_probability", 0.15)))
    right = max(0.0, float(settings.get("right_probability", 0.15)))
    revisit = max(0.0, float(settings.get("revisit_probability", 0.15)))
    total = forward + left + right + revisit
    if total <= 0:
        raise ValueError("Random digger movement probabilities must sum to more than zero")
    forward, left, right, revisit = (
        forward / total,
        left / total,
        right / total,
        revisit / total,
    )

    room_chance = min(1.0, max(0.0, float(settings.get("room_chance", 0.03))))
    room_min_size = max(2, int(settings.get("room_min_size", 3)))
    room_max_size = max(room_min_size, int(settings.get("room_max_size", 7)))

    directions = ((0, -1), (1, 0), (0, 1), (-1, 0))
    direction = 0
    x, y = width // 2, height // 2
    visited: set[tuple[int, int]] = {(x, y)}
    visit_order = [(x, y)]
    grid[y][x] = FLOOR
    room_count = 0

    max_steps = max(target_tiles * 80, width * height * 4)
    steps = 0
    while len(visited) < target_tiles and steps < max_steps:
        steps += 1
        roll = rng.random()
        if roll < forward:
            pass
        elif roll < forward + left:
            direction = (direction - 1) % 4
        elif roll < forward + left + right:
            direction = (direction + 1) % 4
        else:
            x, y = rng.choice(visit_order)
            direction = rng.randrange(4)
            continue

        dx, dy = directions[direction]
        nx, ny = x + dx, y + dy
        if not (1 <= nx < width - 1 and 1 <= ny < height - 1):
            direction = rng.randrange(4)
            continue

        x, y = nx, ny
        grid[y][x] = FLOOR
        if (x, y) not in visited:
            visited.add((x, y))
            visit_order.append((x, y))

        if rng.random() < room_chance:
            room_width = rng.randint(room_min_size, room_max_size)
            room_height = rng.randint(room_min_size, room_max_size)
            room = Rect(
                x - room_width // 2,
                y - room_height // 2,
                room_width,
                room_height,
            )
            before = len(visited)
            carve_rect(grid, room)
            for ry in range(max(1, room.y), min(height - 1, room.bottom)):
                for rx in range(max(1, room.x), min(width - 1, room.right)):
                    if grid[ry][rx] == FLOOR and (rx, ry) not in visited:
                        visited.add((rx, ry))
                        visit_order.append((rx, ry))
            if len(visited) > before:
                room_count += 1

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=grid_rows(grid),
        metadata={
            "genome_representation_type": "agent_carving",
            "room_count": room_count,
            "corridor_count": 1,
            "target_walkable_ratio": target_ratio,
            "digger_steps": steps,
        },
    )
