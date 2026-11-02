"""Plot all per-map fitness values from results.csv files. Requires: pip install plotly."""

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
    counts = {"rows": 0, "plotted": 0, "unavailable_or_nonfinite": 0, "unreadable_csv_files": 0}
    skip = {"_raw", "export", "checkpoints", "llm_map_attempts", "template_attempts", "__pycache__"}
    for folder, directories, files in os.walk(results_dir):
        directories[:] = sorted(name for name in directories if name not in skip)
        if "results.csv" not in files:
            continue
        run = Path(folder)
        config = {}
        for name in ("experiment_evaluated.json", "experiment.json"):
            try:
                config = json.loads((run / name).read_text(encoding="utf-8-sig"))
                if isinstance(config, dict):
                    break
            except (OSError, ValueError):
                pass
            config = {}
        pilot = config.get("pilot", {})
        try:
            with (run / "results.csv").open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream, delimiter=";"):
                    counts["rows"] += 1
                    try:
                        value = float(row.get("fitness_value", ""))
                        if not math.isfinite(value):
                            raise ValueError("Nonfinite fitness")
                    except (TypeError, ValueError):
                        counts["unavailable_or_nonfinite"] += 1
                        continue
                    generator = row.get("generator") or config.get("generator", "unknown")
                    details = {
                        "Run": str(run.relative_to(results_dir)), "Experiment": row.get("experiment", run.name),
                        "Seed": config.get("generator_settings", {}).get("seed", "unknown"),
                        "Map": row.get("map_id"), "Epoch": row.get("epoch"),
                        "Status": row.get("status"), "Valid": row.get("valid"),
                        "Stage": pilot.get("stage", "unmarked / legacy"),
                        "Pilot metadata": json.dumps(pilot, ensure_ascii=False), "Source": str(run / "results.csv"),
                    }
                    hover = "<br>".join(f"{key}: {html.escape(str(item))}" for key, item in details.items())
                    points.append((generator, value, hover))
        except (OSError, csv.Error, UnicodeError):
            counts["unreadable_csv_files"] += 1
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
            marker={"size": 5, "opacity": 0.5}, hovertemplate="Fitness: %{y:.6g}<br>%{text}<extra></extra>",
        ))
    figure.update_layout(
        title=f"All fitness values ({len(points):,})<br><sup>Mixed historical conditions; not a generator ranking.</sup>",
        xaxis={"title": "Generator (horizontal jitter separates points)", "tickmode": "array",
               "tickvals": list(range(len(generators))), "ticktext": generators},
        yaxis_title="Fitness value", template="plotly_white", height=760,
        legend_title="Click to hide; double-click to isolate", margin={"b": 130},
        annotations=[{"text": html.escape(json.dumps(counts)), "xref": "paper", "yref": "paper",
                      "x": 0, "y": -0.2, "showarrow": False, "xanchor": "left"}],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(output), include_plotlyjs=True, config={"scrollZoom": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", nargs="?", type=Path, default=Path(__file__).resolve().parents[1] / "results")
    parser.add_argument("--output", type=Path, help="Default: <results_dir>/all_fitness.html")
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    if not results_dir.is_dir():
        parser.error(f"Results directory does not exist: {results_dir}")
    points, counts = load_results(results_dir)
    output = (args.output or results_dir / "all_fitness.html").resolve()
    plot_results(points, counts, output)
    print(json.dumps(counts, indent=2))
    print(output)
