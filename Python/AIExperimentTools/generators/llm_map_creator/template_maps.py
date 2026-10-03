from map_schema.canonical_map import CanonicalMap
from map_schema.map_validator import MapValidator


MODULE_SIZE = 16
PORT_CELLS = (7, 8)


def validate_template(template):
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
            expected = "." if is_port else "#"

            if symbol != expected:
                raise ValueError(
                    f"Template border at ({x}, {y}) must be {expected!r}"
                )

    validator = MapValidator({
        "minimum_spawn_count": 0,
        "require_single_connected_region": True,
    })
    report = validator.validate(template)

    if not report.valid:
        raise ValueError("Invalid template: " + "; ".join(report.errors))


def assemble_templates(templates, rng, map_id, width, height):
    if not templates:
        raise ValueError("Cannot assemble a map without valid templates")

    for name, value in (("width", width), ("height", height)):
        if type(value) is not int or value < MODULE_SIZE or value % MODULE_SIZE:
            raise ValueError(f"Map {name} must be a positive multiple of 16")

    for template in templates:
        validate_template(template)

    grid = [["#"] * width for _ in range(height)]
    choices = []

    for module_y in range(height // MODULE_SIZE):
        for module_x in range(width // MODULE_SIZE):
            template_index = rng.randrange(len(templates))
            template = templates[template_index]
            rows = template.grid
            rotations = rng.randrange(4)

            for _ in range(rotations):
                rows = tuple("".join(row) for row in zip(*rows[::-1]))

            for y, row in enumerate(rows):
                for x, symbol in enumerate(row):
                    target_x = module_x * MODULE_SIZE + x
                    target_y = module_y * MODULE_SIZE + y

                    if 0 < target_x < width - 1 and 0 < target_y < height - 1:
                        grid[target_y][target_x] = symbol

            choices.append({
                "module_x": module_x,
                "module_y": module_y,
                "template_index": template_index,
                "template_id": template.map_id,
                "rotation": rotations,
            })

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=tuple("".join(row) for row in grid),
        metadata={
            "generator": "template_hybrid",
            "representation": "llm_module_assembly",
            "module_choices": choices,
        },
    )