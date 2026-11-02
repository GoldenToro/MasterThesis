"""Plot each run's mean selected-final-map fitness. Requires: pip install plotly."""

import argparse
import csv
import html
import json
import math
import os
import random
from pathlib import Path


def load_results(results_dir):
    points = []
    counts = {name: 0 for name in (
        "runs", "plotted", "selected_slots", "repeated_slots", "no_selection_list",
        "empty_selection", "missing_fitness_runs", "unreadable_files")}
    skip = {"_raw", "export", "checkpoints", "llm_map_attempts", "template_attempts", "__pycache__"}
    for folder, directories, files in os.walk(results_dir):
        directories[:] = sorted(name for name in directories if name not in skip)
        if "results.csv" not in files:
            continue
        run = Path(folder)
        counts["runs"] += 1
        try:
            config = json.loads((run / "experiment_evaluated.json").read_text(encoding="utf-8-sig"))
            metadata = config.get("run_metadata", {})
            selected = metadata.get("final_candidate_map_ids")
            if not isinstance(selected, list):
                counts["no_selection_list"] += 1
                continue
            if not selected:
                counts["empty_selection"] += 1
                continue
            with (run / "results.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = {row["map_id"]: row for row in csv.DictReader(stream, delimiter=";")}
        except (OSError, ValueError, csv.Error, KeyError):
            counts["unreadable_files"] += 1
            continue
        try:
            values = [float(rows[map_id]["fitness_value"]) for map_id in selected]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Nonfinite selected fitness")
        except (KeyError, TypeError, ValueError):
            counts["missing_fitness_runs"] += 1
            continue
        pilot = config.get("pilot", {})
        recorded_generator = config.get("generator", "unknown")
        generator = pilot.get("original_generator") or recorded_generator
        mean = sum(values) / len(values)
        counts["selected_slots"] += len(selected)
        counts["repeated_slots"] += len(selected) - len(set(selected))
        details = {
            "Run": str(run.relative_to(results_dir)), "Experiment": config.get("experiment_name", run.name),
            "Generator": generator, "Recorded generator": recorded_generator,
            "Seed": config.get("seed", config.get("generator_settings", {}).get("seed", "unknown")),
            "Status": metadata.get("status"), "Selected members": len(selected),
            "Selected IDs": ", ".join(selected), "Selected fitness": str(values),
            "Selection": "saved final selection",
            "Stage": pilot.get("stage", "unmarked / legacy"), "Source stage": pilot.get("source_stage", ""),
            "Pilot metadata": json.dumps(pilot, ensure_ascii=False), "Source": str(run / "results.csv"),
        }
        hover = "<br>".join(f"{key}: {html.escape(str(item))}" for key, item in details.items())
        points.append((generator, mean, hover))
    counts["plotted"] = len(points)
    return points, counts


def plot_results(points, counts, output):
    import plotly.graph_objects as go

    figure, jitter = go.Figure(), random.Random(0)
    generators = sorted({point[0] for point in points})
    for index, generator in enumerate(generators):
        group = [point for point in points if point[0] == generator]
        figure.add_trace(go.Scattergl(
            x=[index + jitter.uniform(-0.24, 0.24) for _ in group], y=[p[1] for p in group],
            text=[p[2] for p in group], mode="markers", name=f"{generator} ({len(group)})",
            marker={"size": 7, "opacity": 0.65}, hovertemplate="Mean final fitness: %{y:.6g}<br>%{text}<extra></extra>",
        ))
    figure.update_layout(
        title=f"Mean selected final fitness ({len(points):,} runs)"
              "<br><sup>One point per run; mixed conditions and check stages. Hover for provenance.</sup>",
        xaxis={"title": "Generator (original generator for checks / replays)", "tickmode": "array",
               "tickvals": list(range(len(generators))), "ticktext": generators},
        yaxis_title="Mean fitness of all selected final maps", template="plotly_white", height=760,
        legend_title="Click to hide; double-click to isolate", margin={"b": 130},
        annotations=[{"text": html.escape(json.dumps(counts)), "xref": "paper", "yref": "paper",
                      "x": 0, "y": -0.2, "showarrow": False, "xanchor": "left", "font": {"size": 10}}],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(output), include_plotlyjs=True, config={"scrollZoom": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", nargs="?", type=Path, default=Path(__file__).resolve().parents[1] / "results")
    parser.add_argument("--output", type=Path, help="Default: <results_dir>/final_fitness.html")
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    if not results_dir.is_dir():
        parser.error(f"Results directory does not exist: {results_dir}")
    points, counts = load_results(results_dir)
    output = (args.output or results_dir / "final_fitness.html").resolve()
    plot_results(points, counts, output)
    print(json.dumps(counts, indent=2))
    print(output)
