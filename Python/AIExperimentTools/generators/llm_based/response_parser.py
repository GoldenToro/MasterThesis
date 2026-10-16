from __future__ import annotations

import re
from typing import Any

from generators.llm_based.schemas import DirectCanonicalMapResponse
from map_schema.canonical_map import (
    ALLOWED_SYMBOLS,
    FLOOR,
    WALL,
    CanonicalMap,
)
from map_schema.map_validator import MapValidationError, MapValidator


def repair_errors(errors: list[str], width: int) -> list[str]:
    """Make repair feedback concise without changing the validation log."""
    result = []
    width_reported = False
    for error in errors:
        if re.fullmatch(r"Grid row \d+ has width \d+ instead of \d+", error):
            if not width_reported:
                result.append(f"All rows have to be {width} characters long.")
                width_reported = True
        elif re.fullmatch(r"Walkable layout contains \d+ connected regions", error):
            result.append(
                "All floor tiles must be reachable from every other floor tile through horizontal or vertical steps. "
                "Connect disconnected floor areas and rooms with new floor corridors; diagonal contact does not count."
            )
        else:
            result.append(error)
    return result


def build_repair_prompt(
    *,
    rules_text: str,
    previous_candidate: dict[str, Any] | None,
    errors: list[str],
    width: int,
    height: int,
    layout_only: bool,
) -> str:
    """Build corrective feedback after parsing or validation fails."""
    symbols = '"#" and "."' if layout_only else '"#", ".", "S", "H", and "A"'
    prompt = rules_text + (
        f"\n\nPlease repair the map. Return exactly {height} grid rows, "
        f"each containing exactly {width} characters. Use only {symbols}.\n"
    )
    previous_grid = (previous_candidate or {}).get("grid", [])
    if previous_grid:
        prompt += "\nPrevious map:\n" + "\n".join(previous_grid) + "\n"
    prompt += "\nErrors:\n" + "\n".join(f"- {error}" for error in errors)
    return prompt + "\n\nReturn the complete corrected JSON object."


def parse_response(
        response: DirectCanonicalMapResponse,
        *,
        map_id: str,
        width: int,
        height: int,
        metadata: dict[str, Any],
        layout_only: bool,
) -> CanonicalMap:
    """Convert a response without changing its geometry or symbols."""
    errors = MapValidator({
        "expected_width": width,
        "expected_height": height,
    }).validate_grid(
        response.width, response.height, response.grid,
        allowed_symbols=frozenset({WALL, FLOOR}) if layout_only else ALLOWED_SYMBOLS,
    )
    if errors:
        raise MapValidationError(errors)

    merged_metadata = dict(metadata)
    merged_metadata.update({
        "llm_suggested_map_id": response.map_id,
        "llm_response_width": response.width,
        "llm_response_height": response.height,
    })

    canonical_map = CanonicalMap(
        map_id=map_id,
        width=response.width,
        height=response.height,
        grid=tuple(response.grid),
        metadata=merged_metadata,
        schema_version=response.schema_version,
    )
    return canonical_map
