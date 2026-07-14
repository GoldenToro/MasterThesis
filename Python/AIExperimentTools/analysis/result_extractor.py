from __future__ import annotations


import json
from pathlib import Path
from typing import Any


def read_final_results(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(item) for item in data]
    if isinstance(data, dict):
        return [dict(data)]
    raise ValueError(f"Unsupported Unity result format in {path}")


def collect_final_results(folder: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(folder.glob("final_results_*")):
        try:
            map_id = path.stem.removeprefix("final_results_")
            for match_index, record in enumerate(read_final_results(path)):
                records.append({"map_id": map_id, "match_index": match_index, **record})
        except (json.JSONDecodeError, ValueError):
            continue
    return records
