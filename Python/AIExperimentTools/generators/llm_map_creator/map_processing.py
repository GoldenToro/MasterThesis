from __future__ import annotations

from typing import Any

from generators.llm_map_creator.schemas import DirectCanonicalMapResponse
from map_schema.canonical_map import (
    ALLOWED_SYMBOLS,
    FLOOR,
    WALL,
    CanonicalMap,
)


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
    errors: list[str] = []

    if response.width != width:
        errors.append(
            f"Response width is {response.width}; expected {width}"
        )
    if response.height != height:
        errors.append(
            f"Response height is {response.height}; expected {height}"
        )

    rows = tuple(response.grid)
    if len(rows) != height:
        errors.append(
            f"Grid contains {len(rows)} rows; expected {height}"
        )

    for index, row in enumerate(rows):
        if len(row) != width:
            errors.append(
                f"Grid row {index} has width {len(row)}; expected {width}"
            )

    allowed = {WALL, FLOOR} if layout_only else ALLOWED_SYMBOLS
    unsupported = sorted({
        symbol
        for row in rows
        for symbol in row
        if symbol not in allowed
    })
    if unsupported:
        errors.append(f"Unsupported grid symbols: {unsupported}")

    if errors:
        raise ValueError("; ".join(errors))

    merged_metadata = dict(metadata)
    merged_metadata.update({
        "llm_suggested_map_id": response.map_id,
        "llm_design_summary": response.metadata.design_summary,
        "llm_features": list(response.metadata.features),
        "llm_response_width": response.width,
        "llm_response_height": response.height,
    })

    return CanonicalMap(
        map_id=map_id,
        width=width,
        height=height,
        grid=rows,
        metadata=merged_metadata,
        schema_version=response.schema_version,
    )