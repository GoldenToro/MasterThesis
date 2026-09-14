from __future__ import annotations

import random

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


def run(base_generator: BaseGenerator) -> list[str]:
    return run_constructive(base_generator, _generate, "grid_graph")


def _generate(
    width: int,
    height: int,
    rng: random.Random,
    settings: dict,
    map_id: str,
) -> CanonicalMap:
    rows = max(2, int(settings.get("graph_rows", 4)))
    columns = max(2, int(settings.get("graph_columns", 5)))
    fill_ratio = min(1.0, max(0.2, float(settings.get("room_fill_ratio", 0.75))))
    room_padding = max(1, int(settings.get("room_padding", 1)))
    corridor_width = max(1, int(settings.get("corridor_width", 2)))
    loop_probability = min(1.0, max(0.0, float(settings.get("loop_probability", 0.25))))

    interior_width = width - 2
    interior_height = height - 2
    cell_width = interior_width // columns
    cell_height = interior_height // rows
    if cell_width < 4 or cell_height < 4:
        raise ValueError(
            "Grid-graph cells are too small. Reduce graph_rows/graph_columns "
            "or increase map dimensions."
        )

    target_rooms = max(2, min(rows * columns, round(rows * columns * fill_ratio)))
    start = (columns // 2, rows // 2)
    occupied = {start}
    frontier = _neighbors(start, columns, rows)
    while len(occupied) < target_rooms and frontier:
        cell = rng.choice(sorted(frontier))
        frontier.remove(cell)
        occupied.add(cell)
        for neighbor in _neighbors(cell, columns, rows):
            if neighbor not in occupied:
                frontier.add(neighbor)

    room_by_cell: dict[tuple[int, int], Rect] = {}
    for column, row in sorted(occupied):
        cell_x = 1 + column * cell_width
        cell_y = 1 + row * cell_height
        actual_width = cell_width if column < columns - 1 else width - 1 - cell_x
        actual_height = cell_height if row < rows - 1 else height - 1 - cell_y
        max_room_width = max(3, actual_width - room_padding * 2)
        max_room_height = max(3, actual_height - room_padding * 2)
        room_width = rng.randint(max(3, max_room_width * 2 // 3), max_room_width)
        room_height = rng.randint(max(3, max_room_height * 2 // 3), max_room_height)
        x_offset = rng.randint(room_padding, max(room_padding, actual_width - room_width - room_padding))
        y_offset = rng.randint(room_padding, max(room_padding, actual_height - room_height - room_padding))
        room_by_cell[(column, row)] = Rect(
            cell_x + x_offset,
            cell_y + y_offset,
            room_width,
            room_height,
        )

    adjacency: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for cell in occupied:
        for neighbor in _neighbors(cell, columns, rows):
            if neighbor in occupied:
                adjacency.add(tuple(sorted((cell, neighbor))))

    tree_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    visited = {start}
    stack = [start]
    while stack:
        current = stack[-1]
        options = [
            neighbor
            for neighbor in _neighbors(current, columns, rows)
            if neighbor in occupied and neighbor not in visited
        ]
        if not options:
            stack.pop()
            continue
        neighbor = rng.choice(options)
        tree_edges.add(tuple(sorted((current, neighbor))))
        visited.add(neighbor)
        stack.append(neighbor)

    selected_edges = set(tree_edges)
    for edge in sorted(adjacency - tree_edges):
        if rng.random() < loop_probability:
            selected_edges.add(edge)

    grid = blank_grid(width, height)
    for room in room_by_cell.values():
        carve_rect(grid, room)
    for first, second in sorted(selected_edges):
        carve_corridor(
            grid,
            room_by_cell[first].center,
            room_by_cell[second].center,
            corridor_width,
            horizontal_first=first[0] != second[0],
        )

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=grid_rows(grid),
        metadata={
            "genome_representation_type": "grid_graph_constructive",
            "room_count": len(room_by_cell),
            "corridor_count": len(selected_edges),
            "graph_node_count": len(room_by_cell),
            "graph_edge_count": len(selected_edges),
        },
    )


def _neighbors(
    cell: tuple[int, int],
    columns: int,
    rows: int,
) -> set[tuple[int, int]]:
    x, y = cell
    return {
        (nx, ny)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        if 0 <= nx < columns and 0 <= ny < rows
    }
