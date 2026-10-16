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


def save_grid_text(canonical_map: CanonicalMap, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_map.grid) + "\n", encoding="utf-8")
    return path
