from __future__ import annotations

import json
from pathlib import Path

from map_schema.canonical_map import CanonicalMap


def save_canonical_map(
    canonical_map: CanonicalMap, path: Path, *, valid: bool | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_map.to_dict()
    if valid is not None:
        payload["valid"] = bool(valid)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_canonical_map(path: Path) -> CanonicalMap:
    data = json.loads(path.read_text(encoding="utf-8"))
    return CanonicalMap.from_dict(data)


def load_saved_map(epoch_dir: Path, map_id: str) -> CanonicalMap | None:
    """Read a canonical map, including from a cleaned-up run's Unity export."""
    map_path = epoch_dir / f"{map_id}.map.json"
    if map_path.is_file():
        return load_canonical_map(map_path)
    unity_path = epoch_dir / f"{map_id}.unity.json"
    if unity_path.is_file():
        payload = json.loads(unity_path.read_text(encoding="utf-8"))
        map_payload = payload.get("map")
        if isinstance(map_payload, dict):
            return CanonicalMap.from_dict(map_payload)
    return None


def save_grid_text(canonical_map: CanonicalMap, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_map.grid) + "\n", encoding="utf-8")
    return path
