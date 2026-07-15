from __future__ import annotations

import math
from pathlib import Path
from statistics import mean
from typing import Any


def create_epoch_line_diagram(
    records_by_epoch: dict[int, list[dict[str, Any]]],
    value_name: str,
    output_path: Path,
    title: str | None = None,
    best_goal: str | None = None,
) -> Path | None:
    """Create a mixed population diagram for a scalar map metric.

    Every population member is shown as a faint point, the population average
    is the main line, the min/max range is shaded, and an optional best line is
    added. For NSGA-II, ``records_by_epoch`` includes carried-over individuals
    from checkpoint summaries instead of only newly evaluated offspring.
    """

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    grouped: dict[int, list[float]] = {}
    for epoch, records in records_by_epoch.items():
        values = [
            value
            for record in records
            if (value := _extract_numeric(record, value_name)) is not None
        ]
        if values:
            grouped[int(epoch)] = values

    if len(grouped) == 0:
        return None

    epochs = sorted(grouped)
    averages = [mean(grouped[epoch]) for epoch in epochs]
    minimums = [min(grouped[epoch]) for epoch in epochs]
    maximums = [max(grouped[epoch]) for epoch in epochs]

    figure, axis = plt.subplots(figsize=(9, 5.5))
    for epoch in epochs:
        axis.scatter(
            [epoch] * len(grouped[epoch]),
            grouped[epoch],
            alpha=0.18,
            s=18,
            label="Population members" if epoch == epochs[0] else None,
        )
    axis.fill_between(
        epochs,
        minimums,
        maximums,
        alpha=0.16,
        label="Population min/max",
    )
    axis.plot(
        epochs,
        averages,
        marker="o",
        linewidth=2,
        label="Population average",
    )

    if best_goal in {"maximize", "minimize"}:
        selector = max if best_goal == "maximize" else min
        best_values = [selector(grouped[epoch]) for epoch in epochs]
        axis.plot(
            epochs,
            best_values,
            marker="x",
            linestyle="--",
            linewidth=1.5,
            label=f"Population best ({best_goal})",
        )

    axis.set_xlabel("Epoch")
    axis.set_ylabel(value_name.replace("_", " ").title())
    axis.set_title(title or f"{value_name.replace('_', ' ').title()} by epoch")
    axis.grid(True, alpha=0.25)
    axis.legend()
    axis.set_xticks(epochs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def create_epoch_summary_line_diagram(
    values_by_epoch: dict[int, float],
    value_name: str,
    output_path: Path,
    title: str | None = None,
) -> Path | None:
    """Create a line graph for one population-level value per epoch."""

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    clean = {
        int(epoch): float(value)
        for epoch, value in values_by_epoch.items()
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    }
    if len(clean) == 0:
        return None

    epochs = sorted(clean)
    values = [clean[epoch] for epoch in epochs]
    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.plot(epochs, values, marker="o", linewidth=2, label="Epoch value")
    axis.set_xlabel("Epoch")
    axis.set_ylabel(value_name.replace("_", " ").title())
    axis.set_title(title or f"{value_name.replace('_', ' ').title()} by epoch")
    axis.grid(True, alpha=0.25)
    axis.legend()
    axis.set_xticks(epochs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output_path


def _extract_numeric(record: dict[str, Any], value_name: str) -> float | None:
    if value_name == "fitness_value":
        value = record.get("fitness_value")
    else:
        value = record.get("metrics", {}).get(value_name)
    if isinstance(value, bool) or isinstance(value, (int, float)) is False:
        return None
    number = float(value)
    return number if math.isfinite(number) else None
