from __future__ import annotations

from statistics import mean, pstdev
from typing import Any


def enrich_match_record(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    frags1 = _number(result.get("numberOfFrags1"))
    frags2 = _number(result.get("numberOfFrags2"))
    if frags1 is not None and frags2 is not None:
        result["kill_difference"] = frags1 - frags2
        result["kill_ratio"] = frags1 / frags2 if frags2 else frags1
        result["total_frags"] = frags1 + frags2
    return result


def aggregate_match_records(records: list[dict[str, Any]]) -> dict[str, float | int]:
    enriched = [enrich_match_record(record) for record in records]
    numeric_keys = sorted(
        {
            key
            for record in enriched
            for key, value in record.items()
            if isinstance(value, (int, float)) and isinstance(value, bool) is False
        }
    )
    result: dict[str, float | int] = {"match_count": len(enriched)}
    for key in numeric_keys:
        values = [float(record[key]) for record in enriched if isinstance(record.get(key), (int, float))]
        if values:
            result[key] = mean(values)
            result[f"{key}_std"] = pstdev(values) if len(values) > 1 else 0.0
    return result


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and isinstance(value, bool) is False:
        return float(value)
    return None
