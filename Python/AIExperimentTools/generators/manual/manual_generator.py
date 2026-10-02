from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable
from candidate import Candidate

from experiment_session import ExperimentSession
from map_schema.canonical_map import ALLOWED_SYMBOLS, CanonicalMap


LOGGER = logging.getLogger("FPS-EVALUATOR")

def run(base_generator: ExperimentSession) -> list[str]:
    """Load every text map in the configured folder and evaluate it once.

    One text file represents one map. All maps are placed in epoch 0
    and returned as final candidates.
    """
    map_directory = _resolve_map_directory(base_generator)
    map_files = sorted(
        path for path in map_directory.glob("*.txt") if path.is_file()
    )
    if len(map_files) == 0:
        raise FileNotFoundError(
            f"Manual generator found no .txt maps in {map_directory}"
        )

    LOGGER.info(
        "Load %s manual text maps from %s.",
        len(map_files),
        map_directory,
    )

    maps: list[CanonicalMap] = []
    used_ids: set[str] = set()

    for path in map_files:
        map_id = _unique_map_id(_safe_map_id(path.stem), used_ids)
        canonical_map = load_text_map(
            path,
            map_id=map_id,
            source_root=base_generator.framework_root,
        )
        maps.append(canonical_map)

        LOGGER.info(
            "    Loaded %s (%sx%s).",
            path.name,
            canonical_map.width,
            canonical_map.height,
        )

    candidates = [
        Candidate(canonical_map=item)
        for item in maps
    ]
    evaluated = base_generator.evaluate_candidates(
        candidates,
        epoch=0,
    )
    final_map_ids = [
        candidate.map_id
        for candidate in evaluated
    ]

    epoch_dir = base_generator.output_dir / "epoch_0000"

    # Analysis uses this file to identify the selected population.
    (epoch_dir / "checkpoint_summary.json").write_text(
        json.dumps(
            {
                "epoch": 0,
                "population_size": len(final_map_ids),
                "selected_map_ids": final_map_ids,
                "source": "manual_text_maps",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return final_map_ids


def load_text_map(
    path: Path,
    map_id: str | None = None,
    source_root: Path | None = None,
) -> CanonicalMap:
    """Parse one canonical map from a UTF-8 text file.

    Leading and trailing empty lines are ignored. Empty lines inside the map,
    unequal row widths, and unsupported symbols are rejected with a clear error.
    """
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()

    if len(lines) == 0:
        raise ValueError(f"Manual map {path} is empty")
    if any(line == "" for line in lines):
        raise ValueError(
            f"Manual map {path} contains an empty row inside the grid"
        )

    width = len(lines[0])
    if width == 0:
        raise ValueError(f"Manual map {path} has an empty first row")
    for row_number, row in enumerate(lines, start=1):
        if len(row) != width:
            raise ValueError(
                f"Manual map {path} row {row_number} has width {len(row)} "
                f"instead of {width}"
            )
        invalid = sorted(set(row) - set(ALLOWED_SYMBOLS))
        if invalid:
            rendered = ", ".join(repr(value) for value in invalid)
            raise ValueError(
                f"Manual map {path} row {row_number} contains unsupported "
                f"symbols: {rendered}"
            )

    source_path: str
    if source_root is not None:
        try:
            source_path = str(path.resolve().relative_to(source_root.resolve()))
        except ValueError:
            source_path = str(path.resolve())
    else:
        source_path = str(path.resolve())

    resolved_map_id = map_id or _safe_map_id(path.stem)
    return CanonicalMap(
        map_id=resolved_map_id,
        width=width,
        height=len(lines),
        grid=tuple(lines),
        metadata={
            "generator": "manual",
            "genome_representation_type": "manual_text",
            "source_text_map": source_path,
        },
    )


def _resolve_map_directory(base_generator: ExperimentSession) -> Path:
    configured = base_generator.generator_settings.get("maps_directory")
    if configured is not None:
        directory = Path(str(configured))
        if directory.is_absolute() is False:
            directory = base_generator.framework_root / directory
        directory = directory.resolve()
    else:
        paths = base_generator.technical_settings.get("paths", {})
        root = Path(str(paths.get("manual_maps_root", "manual_maps")))
        if root.is_absolute() is False:
            root = base_generator.framework_root / root
        directory = (root / base_generator.experiment_name).resolve()

    if directory.is_dir() is False:
        raise FileNotFoundError(
            "Manual map directory does not exist: "
            f"{directory}. Create it or set generator_settings.maps_directory."
        )
    return directory


def _safe_map_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    if normalized == "":
        normalized = "map"
    return f"manual_{normalized}"


def _unique_map_id(candidate: str, used_ids: set[str]) -> str:
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in used_ids:
        suffix += 1
    unique = f"{candidate}_{suffix}"
    used_ids.add(unique)
    return unique
