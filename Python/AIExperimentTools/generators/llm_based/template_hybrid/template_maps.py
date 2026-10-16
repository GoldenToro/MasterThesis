from math import ceil, floor

from map_schema.canonical_map import CanonicalMap
from map_schema.map_validator import MapValidator


MODULE_SIZE = 16
PORT_CELLS = (7, 8)
PORTS = {
    (0, -1): ((7, 0), (8, 0)),
    (1, 0): ((15, 7), (15, 8)),
    (0, 1): ((7, 15), (8, 15)),
    (-1, 0): ((0, 7), (0, 8)),
}


def open_ports(grid):
    return {side for side, cells in PORTS.items() if grid[cells[0][1]][cells[0][0]] == "."}


def validate_template(template, *, require_connected_interior=False, require_all_ports=False):
    if (template.width, template.height) != (MODULE_SIZE, MODULE_SIZE):
        raise ValueError("Templates must be 16 by 16 cells")

    for x, y, symbol in template.iter_cells():
        if symbol not in "#.":
            raise ValueError("Templates may contain only walls and floor")

        if x in (0, MODULE_SIZE - 1) or y in (0, MODULE_SIZE - 1):
            is_port = (
                              x in (0, MODULE_SIZE - 1) and y in PORT_CELLS
                      ) or (
                              y in (0, MODULE_SIZE - 1) and x in PORT_CELLS
                      )
            if not is_port and symbol != "#":
                raise ValueError(
                    f"Template border at ({x}, {y}) must be '#' outside centered doorways"
                )

    for cells in PORTS.values():
        if len({template.grid[y][x] for x, y in cells}) != 1:
            raise ValueError("Template doorways must be fully closed or two cells wide")
    ports = open_ports(template.grid)
    if not ports:
        raise ValueError("Templates must have at least one doorway")
    if require_all_ports and len(ports) != 4:
        raise ValueError("Templates must have all four centered doorways")

    validator = MapValidator({
        "minimum_spawn_count": 0,
        "require_single_connected_region": True,
    })
    report = validator.validate(template)

    if not report.valid:
        raise ValueError("Invalid template: " + "; ".join(report.errors))

    if require_connected_interior or len(ports) < 4:
        interior = CanonicalMap(
            map_id=template.map_id,
            width=MODULE_SIZE - 2,
            height=MODULE_SIZE - 2,
            grid=tuple(row[1:-1] for row in template.grid[1:-1]),
        )
        if not validator.validate(interior).valid:
            raise ValueError(
                f"Template {template.map_id!r} must remain connected when its doorways are sealed"
            )


def assemble_templates(templates, rng, map_id, width, height, room_count=None):
    if not templates:
        raise ValueError("Cannot assemble a map without valid templates")

    for name, value in (("width", width), ("height", height)):
        if type(value) is not int or value < MODULE_SIZE or value % MODULE_SIZE:
            raise ValueError(f"Map {name} must be a positive multiple of 16")

    columns = width // MODULE_SIZE
    rows_count = height // MODULE_SIZE
    total_rooms = columns * rows_count
    if room_count is None:
        minimum = ceil(total_rooms * 0.4)
        maximum = floor(total_rooms * 0.7)
        if minimum > maximum:
            raise ValueError("Map has too few template slots for 40-70% coverage")
        room_count = rng.randint(minimum, maximum)
    if type(room_count) is not int or not 1 <= room_count <= total_rooms:
        raise ValueError(f"room_count must be an integer from 1 to {total_rooms}")

    for template in templates:
        validate_template(template, require_connected_interior=True)

    rotated_templates = []
    for template in templates:
        rotations = []
        grid = template.grid
        for _ in range(4):
            rotations.append((grid, open_ports(grid)))
            grid = tuple("".join(row) for row in zip(*grid[::-1]))
        rotated_templates.append(rotations)

    positions = [(x, y) for y in range(rows_count) for x in range(columns)]
    # Grow a connected room graph. Only its tree edges are mandatory, allowing
    # one-door templates at leaves even when other rooms are adjacent.
    occupied = {rng.choice(positions)}
    required_ports = {position: set() for position in occupied}
    while len(occupied) < room_count:
        frontier = sorted(
            (x, y, dx, dy)
            for x, y in occupied
            for dx, dy in PORTS
            if 0 <= x + dx < columns and 0 <= y + dy < rows_count
            and (x + dx, y + dy) not in occupied
        )
        x, y, dx, dy = rng.choice(frontier)
        neighbor = (x + dx, y + dy)
        occupied.add(neighbor)
        required_ports[(x, y)].add((dx, dy))
        required_ports[neighbor] = {(-dx, -dy)}

    grid = [["#"] * width for _ in range(height)]
    choices = []
    selected = {}

    for module_y in range(rows_count):
        for module_x in range(columns):
            if (module_x, module_y) not in occupied:
                continue
            compatible = []
            for index, variants in enumerate(rotated_templates):
                allowed = [
                    r for r, (_, ports) in enumerate(variants)
                    if required_ports[(module_x, module_y)] <= ports
                ]
                if allowed:
                    compatible.append((index, allowed))
            if not compatible:
                raise ValueError(
                    f"No template rotation can connect module ({module_x}, {module_y}) "
                    "along the planned connections; include templates with more doorways"
                )
            template_index, allowed = compatible[rng.randrange(len(compatible))]
            rotations = allowed[rng.randrange(len(allowed))]
            template = templates[template_index]
            rows = rotated_templates[template_index][rotations][0]
            selected[(module_x, module_y)] = rows

            choices.append({
                "module_x": module_x,
                "module_y": module_y,
                "template_index": template_index,
                "template_id": template.map_id,
                "rotation": rotations,
            })

    for (module_x, module_y), rows in selected.items():
        room = [list(row) for row in rows]
        for (dx, dy), cells in PORTS.items():
            neighbor = selected.get((module_x + dx, module_y + dy))
            if neighbor is None or (-dx, -dy) not in open_ports(neighbor):
                for x, y in cells:
                    room[y][x] = "#"
        for y, row in enumerate(room):
            for x, symbol in enumerate(row):
                grid[module_y * MODULE_SIZE + y][module_x * MODULE_SIZE + x] = symbol

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=tuple("".join(row) for row in grid),
        metadata={
            "generator": "template_hybrid",
            "representation": "template_module_assembly",
            "room_count": room_count,
            "template_coverage_ratio": room_count / total_rooms,
            "module_choices": choices,
        },
    )
