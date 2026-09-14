from __future__ import annotations

import random
from dataclasses import dataclass

from generators.base_generator import BaseGenerator
from generators.constructive.common import (
    Rect,
    blank_grid,
    carve_corridor,
    carve_rect,
    grid_rows,
    run_constructive,
)
from map_schema.canonical_map import CanonicalMap


@dataclass
class _Node:
    rect: Rect
    left: "_Node | None" = None
    right: "_Node | None" = None
    room: Rect | None = None

    @property
    def leaf(self) -> bool:
        return self.left is None and self.right is None


def run(base_generator: BaseGenerator) -> list[str]:
    return run_constructive(base_generator, _generate, "divisive")


def _generate(
    width: int,
    height: int,
    rng: random.Random,
    settings: dict,
    map_id: str,
) -> CanonicalMap:
    min_room_size = max(3, int(settings.get("minimum_room_size", 5)))
    room_padding = max(1, int(settings.get("room_padding", 1)))
    min_leaf_size = max(
        min_room_size + room_padding * 2,
        int(settings.get("minimum_partition_size", min_room_size + room_padding * 2)),
    )
    max_depth = max(1, int(settings.get("max_depth", 5)))
    corridor_width = max(1, int(settings.get("corridor_width", 2)))
    extra_connection_probability = min(
        1.0,
        max(0.0, float(settings.get("extra_connection_probability", 0.15))),
    )

    root = _Node(Rect(1, 1, width - 2, height - 2))
    _split(root, rng, min_leaf_size, max_depth, 0)
    leaves = _leaves(root)
    rooms: list[Rect] = []
    for leaf in leaves:
        available_width = max(min_room_size, leaf.rect.width - room_padding * 2)
        available_height = max(min_room_size, leaf.rect.height - room_padding * 2)
        room_width = rng.randint(min_room_size, available_width)
        room_height = rng.randint(min_room_size, available_height)
        max_x_offset = max(0, leaf.rect.width - room_width - room_padding)
        max_y_offset = max(0, leaf.rect.height - room_height - room_padding)
        room_x = leaf.rect.x + rng.randint(room_padding, max(room_padding, max_x_offset))
        room_y = leaf.rect.y + rng.randint(room_padding, max(room_padding, max_y_offset))
        room = Rect(room_x, room_y, room_width, room_height)
        leaf.room = room
        rooms.append(room)

    grid = blank_grid(width, height)
    for room in rooms:
        carve_rect(grid, room)

    connections: set[tuple[int, int]] = set()
    room_indices = {id(room): index for index, room in enumerate(rooms)}

    def connect_tree(node: _Node) -> list[Rect]:
        if node.leaf:
            return [node.room] if node.room is not None else []
        left_rooms = connect_tree(node.left) if node.left is not None else []
        right_rooms = connect_tree(node.right) if node.right is not None else []
        if left_rooms and right_rooms:
            first, second = min(
                ((a, b) for a in left_rooms for b in right_rooms),
                key=lambda pair: _distance_sq(pair[0].center, pair[1].center),
            )
            carve_corridor(
                grid,
                first.center,
                second.center,
                corridor_width,
                horizontal_first=bool(rng.getrandbits(1)),
            )
            edge = tuple(sorted((room_indices[id(first)], room_indices[id(second)])))
            connections.add(edge)
        return left_rooms + right_rooms

    connect_tree(root)

    for first in range(len(rooms)):
        for second in range(first + 1, len(rooms)):
            if (first, second) in connections:
                continue
            if rng.random() < extra_connection_probability / max(1, len(rooms)):
                carve_corridor(
                    grid,
                    rooms[first].center,
                    rooms[second].center,
                    corridor_width,
                    horizontal_first=bool(rng.getrandbits(1)),
                )
                connections.add((first, second))

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=grid_rows(grid),
        metadata={
            "genome_representation_type": "binary_space_partition",
            "room_count": len(rooms),
            "corridor_count": len(connections),
            "partition_count": len(leaves),
        },
    )


def _split(
    node: _Node,
    rng: random.Random,
    minimum_size: int,
    max_depth: int,
    depth: int,
) -> None:
    rect = node.rect
    can_split_vertical = rect.width >= minimum_size * 2
    can_split_horizontal = rect.height >= minimum_size * 2
    if depth >= max_depth or not (can_split_vertical or can_split_horizontal):
        return

    if can_split_vertical and can_split_horizontal:
        if rect.width / rect.height >= 1.25:
            vertical = True
        elif rect.height / rect.width >= 1.25:
            vertical = False
        else:
            vertical = bool(rng.getrandbits(1))
    else:
        vertical = can_split_vertical

    if vertical:
        split = rng.randint(minimum_size, rect.width - minimum_size)
        node.left = _Node(Rect(rect.x, rect.y, split, rect.height))
        node.right = _Node(Rect(rect.x + split, rect.y, rect.width - split, rect.height))
    else:
        split = rng.randint(minimum_size, rect.height - minimum_size)
        node.left = _Node(Rect(rect.x, rect.y, rect.width, split))
        node.right = _Node(Rect(rect.x, rect.y + split, rect.width, rect.height - split))

    _split(node.left, rng, minimum_size, max_depth, depth + 1)
    _split(node.right, rng, minimum_size, max_depth, depth + 1)


def _leaves(node: _Node) -> list[_Node]:
    if node.leaf:
        return [node]
    result: list[_Node] = []
    if node.left is not None:
        result.extend(_leaves(node.left))
    if node.right is not None:
        result.extend(_leaves(node.right))
    return result


def _distance_sq(first: tuple[int, int], second: tuple[int, int]) -> int:
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2
