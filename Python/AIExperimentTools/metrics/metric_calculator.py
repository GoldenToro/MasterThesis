from __future__ import annotations

from statistics import mean
from typing import Any, Callable


def calculate_entropy(match_records: list[dict[str, Any]]) -> float | None:
    """Average Unity's entropy value across all successful matches."""
    return _mean_numeric(match_records, "entropy")


def calculate_pace(match_records: list[dict[str, Any]]) -> float | None:
    """Average Unity's pace value across all successful matches."""
    return _mean_numeric(match_records, "pace")


def calculate_metrics(
    match_records: list[dict[str, Any]],
    metric_names: list[str],
) -> dict[str, float | None]:
    """Calculate the configured metrics by their function names."""
    result: dict[str, float | None] = {}
    for name in metric_names:
        function = globals().get(f"calculate_{name}")
        if callable(function) is False:
            raise ValueError(
                f"Metric '{name}' has no calculate_{name} function in metric_calculator.py"
            )
        result[name] = function(match_records)
    return result


def _mean_numeric(
    match_records: list[dict[str, Any]],
    key: str,
) -> float | None:
    values = [
        float(record[key])
        for record in match_records
        if isinstance(record.get(key), (int, float))
        and isinstance(record.get(key), bool) is False
    ]
    return mean(values) if values else None
