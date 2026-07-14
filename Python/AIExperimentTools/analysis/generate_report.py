from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

from analysis.plots import create_plots, render_grid
from map_schema.map_exporter import load_canonical_map
from metrics.diversity_metrics import calculate_map_set_diversity


def generate_report(
    run_dir: Path,
    records: list[dict[str, Any]],
    reporting_settings: dict[str, Any],
) -> dict[str, Any]:
    metrics_dir = run_dir / "_metrics"
    figures_dir = run_dir / "_figures"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    ranked = sorted(
        records,
        key=lambda record: (
            record.get("fitness", {}).get("score") is not None,
            record.get("fitness", {}).get("score") or -1.0,
        ),
        reverse=True,
    )
    _write_ranking(metrics_dir / "ranked_maps.csv", ranked)

    maps = []
    for record in records:
        map_path = record.get("artifacts", {}).get("canonical_map_json")
        if map_path and Path(map_path).is_file():
            maps.append(load_canonical_map(Path(map_path)))
    diversity = calculate_map_set_diversity(maps)

    valid_count = sum(1 for record in records if record.get("validation", {}).get("valid"))
    scores = [record.get("fitness", {}).get("score") for record in records]
    scores = [float(value) for value in scores if isinstance(value, (int, float))]
    summary = {
        "evaluated_map_count": len(records),
        "valid_map_count": valid_count,
        "invalid_map_count": len(records) - valid_count,
        "generator_success_rate": valid_count / len(records) if records else 0.0,
        "mean_fitness_score": mean(scores) if scores else None,
        "best_map_id": ranked[0]["map_id"] if ranked else None,
        "best_fitness_score": ranked[0].get("fitness", {}).get("score") if ranked else None,
        "diversity": diversity,
    }

    (metrics_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if ranked and bool(reporting_settings.get("copy_best_map", True)):
        source = Path(ranked[0]["artifacts"]["canonical_map_json"])
        if source.is_file():
            shutil.copy2(source, run_dir / "best_map.json")
            canonical_map = load_canonical_map(source)
            render_grid(canonical_map.grid, figures_dir / "best_map.png", canonical_map.map_id)

    if bool(reporting_settings.get("create_plots", True)):
        create_plots(records, figures_dir)
    return summary


def _write_ranking(path: Path, records: list[dict[str, Any]]) -> None:
    rows = []
    for rank, record in enumerate(records, start=1):
        row = {
            "rank": rank,
            "map_id": record.get("map_id"),
            "generator": record.get("generator"),
            "valid": record.get("validation", {}).get("valid"),
            "fitness_score": record.get("fitness", {}).get("score"),
        }
        for key, value in record.get("static_metrics", {}).items():
            if isinstance(value, (int, float)):
                row[f"static_{key}"] = value
        for key, value in record.get("simulation_metrics", {}).items():
            if isinstance(value, (int, float)):
                row[f"simulation_{key}"] = value
        rows.append(row)

    fieldnames = sorted({key for row in rows for key in row}) if rows else ["rank", "map_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
