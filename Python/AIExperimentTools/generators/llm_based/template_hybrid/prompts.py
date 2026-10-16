import json
from typing import Any

from generators.llm_based.template_hybrid.template_maps import MODULE_SIZE, PORT_CELLS


def build_prompt(
        *,
        template: bool = False,
        layout_only: bool = False,
        rules_text: str,
        map_id: str,
        map_index: int,
        map_count: int,
        width: int,
        height: int,
        seed: int,
        validation: dict[str, Any],
        examples: list[Any],
        attempt: int,
        feedback: dict[str, Any] | None,
) -> str:
    if template:
        first, second = PORT_CELLS
        last = MODULE_SIZE - 1
        border_requirements = [
            "- coordinates use zero-based (x, y), starting at the top-left",
            "- choose one to four open doorways; at least one is required",
            f"- top/bottom doorways occupy x={first},{second} in rows y=0,{last}",
            f"- left/right doorways occupy y={first},{second} in columns x=0,{last}",
            "- each doorway is either two floor cells (..) or two walls (##)",
            "- every other border cell is #",
            "- all floor cells and doorways connect using only horizontal "
            "or vertical steps",
            "- the interior must stay connected if all border doorways are sealed",
            "- do not place spawns, health, or ammo",
        ]
    else:
        border_requirements = [
            "- the first and last row contain only #",
            "- the first and last symbol of every row are #",
        ]

    sections = [
        (
            "Create a reusable canonical JSON room template."
            if template
            else "Create a complete canonical JSON map."
        ),
        f"Map: {map_index + 1} of {map_count}",
        f"Required map_id: {map_id}",
        f"Dimensions: width {width}, height {height}",
        f"Variation seed: {seed}",
        "",
        "Rules written by the designer:",
        rules_text,
        "",
        "Canonical JSON requirements:",
        f"- width equals {width}",
        f"- height equals {height}",
        f"- grid contains exactly {height} strings",
        f"- every grid string contains exactly {width} symbols",
        *border_requirements,
        "- use only # ." if layout_only else "- use only # . S H A",
        "- all walkable cells form one connected region",
        f"- validation settings: {json.dumps(validation, sort_keys=True)}",
    ]

    if examples:
        sections.extend([
            "",
            (
                "Existing map parts (each is a list of grid rows). Create a new, "
                "distinct part for this library; return the canonical JSON format above:"
                if template else
                "Optional examples of the expected output format and quality:"
            ),
            json.dumps(examples, ensure_ascii=False, indent=2),
        ])

    if feedback:
        sections.extend([
            "",
            f"Correction attempt {attempt}:",
            "Improve the previous candidate using this local validation feedback:",
            json.dumps(feedback, ensure_ascii=False, indent=2),
        ])

    sections.extend([
        "",
        "Return the complete JSON object as the final answer.",
    ])
    return "\n".join(sections)

