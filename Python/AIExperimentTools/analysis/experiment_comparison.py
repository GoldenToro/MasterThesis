"""Batch comparison reports for saved experiments."""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

from dataclasses import dataclass
from analysis.run_analysis import (
    RunAnalysis, GENERATION_MAP_METRICS, FINAL_POPULATION_METRICS, RUN_POPULATION_METRICS,
)
from generators.registry import generator_color, generator_family
from metrics.metric_calculator import (
    NUMERIC_METRIC_NAMES,
    POPULATION_METRIC_NAMES,
)

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def numeric(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def average(values):
    values = [value for value in values if numeric(value)]
    return mean(values) if values else None


@dataclass
class ExperimentComparison:
    """Compare runs and write reports without rewriting experiment results."""

    score_metrics: list
    epoch_metrics: list
    average_multiple_runs: bool = True
    create_overview: bool = True
    show_epoch_maximum: bool = True
    do_map_visualization: bool = False
    movement_log_scale: bool = True
    death_log_scale: bool = True
    bottom_padding: float = 0.65
    chart_size: float = 5.2
    image_dpi: int = 160
    do_graph_visualization: bool = False

    def __post_init__(self):
        self.validate_score_metrics()

    def validate_score_metrics(self):
        if not isinstance(self.score_metrics, (list, tuple)) or any(
                not isinstance(axis, dict) for axis in self.score_metrics):
            raise ValueError("Score axes must be dictionaries")
        names = [axis.get("name") for axis in self.score_metrics]
        if (len(names) < 3 or any(not isinstance(name, str) or not name for name in names)
                or len(set(names)) != len(names)):
            raise ValueError("Configure at least three distinct named score axes")
        for axis in self.score_metrics:
            name = axis["name"]
            if not isinstance(axis.get("label"), str) or not axis["label"]:
                raise ValueError(f"Score axis {name} needs a label")
            if not numeric(axis.get("weight")) or axis["weight"] <= 0:
                raise ValueError(f"Score axis {name} needs a finite positive weight")
            if not isinstance(axis.get("scored", True), bool):
                raise ValueError(f"scored must be a boolean for {name}")
            components = axis.get("components")
            if name == "performance_consistency":
                if components != [] or not axis.get("scored", True):
                    raise ValueError("Performance consistency needs empty components and scored=true")
                continue
            if not isinstance(components, (list, tuple)) or not components:
                raise ValueError(f"Score axis {name} needs metric components")
            for component in components:
                if not isinstance(component, (list, tuple)) or len(component) != 5:
                    raise ValueError(f"Invalid component in score axis {name}")
                metric, minimum, maximum, reverse, weight = component
                if not isinstance(metric, str) or metric not in NUMERIC_METRIC_NAMES:
                    raise ValueError(f"Invalid scalar metric: {metric}")
                if axis.get("scored", True) and (
                        not numeric(minimum) or not numeric(maximum) or minimum >= maximum):
                    raise ValueError(f"Invalid finite display range for {metric}")
                if not isinstance(reverse, bool):
                    raise ValueError(f"lower_is_better must be a boolean for {metric}")
                if not numeric(weight) or weight <= 0:
                    raise ValueError(f"Component {metric} needs a finite positive weight")

    def component_metric_names(self):
        return list(dict.fromkeys(component[0] for axis in self.score_metrics
                                  for component in axis["components"]))

    def report_metric_names(self):
        names = self.component_metric_names()
        if "generator_reliability" in names:
            names = list(dict.fromkeys(names + ["generator_success_rate", "repair_rate"]))
        return names

    def discover_runs(self, root):
        """Find run folders without walking raw simulation output or exports."""
        excluded = {"_raw", "export", "checkpoints", "experiment_analysis", "__pycache__"}
        runs = []
        for directory, children, files in os.walk(root):
            children[:] = sorted(name for name in children if name not in excluded)
            if "experiment.json" in files or "experiment_evaluated.json" in files:
                runs.append(Path(directory))
                children[:] = []
        return sorted(runs)

    def config_key(self, config):
        """Ignore repeat-specific seeds, retaining actual experiment parameters."""
        config = copy.deepcopy(config)
        for key in ("seed", "run_metadata", "experiment_name", "no_of_experiments"):
            config.pop(key, None)
        config.get("generator_settings", {}).pop("seed", None)
        return json.dumps(config, sort_keys=True)

    def load_run(self, path):
        config_path = path / "experiment.json"
        evaluated_path = path / "experiment_evaluated.json"
        config = read_json(config_path if config_path.exists() else evaluated_path)
        evaluated = read_json(evaluated_path) if evaluated_path.exists() else config
        analyzer = RunAnalysis(path, evaluated)
        records, paths, contexts = analyzer.load()
        selected = analyzer.select_final(contexts)
        if not selected:
            warnings.warn(f"{path.name}: no final selection; final-map axes unavailable")
        values, counts = {}, {}
        for name in self.report_metric_names():
            if name in POPULATION_METRIC_NAMES:
                population = selected if name in FINAL_POPULATION_METRICS | RUN_POPULATION_METRICS else contexts
                value = analyzer.population_metrics(selected, contexts, [name])[name]
                values[name] = value if numeric(value) else None
                counts[name] = len(population) if numeric(value) else 0
            else:
                population = contexts if name in GENERATION_MAP_METRICS else selected
                samples = analyzer.map_values(population, name)
                values[name] = average(samples)
                counts[name] = sum(numeric(value) for value in samples)
        axis_scores = self.calculate_axis_scores(values)
        generator = config.get("pilot", {}).get("original_generator") or config.get("generator", "manual")
        return {
            "folder": str(path), "name": path.name, "generator": generator,
            "config_key": self.config_key(config), "values": values, "sample_counts": counts,
            "status": evaluated.get("run_metadata", {}).get("status", "unknown"),
            "generated_maps": len(contexts), "selected_maps": len(selected),
            "selected_map_ids": [context.record["map_id"] for context in selected],
            "final_selection": "saved_final_selection",
            "epochs": self.load_epochs(analyzer, contexts),
            "axis_scores": axis_scores, "total_score": self.total_score(axis_scores),
        }

    def group_runs(self, runs):
        run_axes = [axis["name"] for axis in self.score_metrics
                    if axis["name"] != "performance_consistency"]
        has_consistency = any(axis["name"] == "performance_consistency" for axis in self.score_metrics)
        groups = defaultdict(list)
        for run in runs:
            path = Path(run["folder"])
            name = re.sub(r"_\d+$", "", run["name"]) if self.average_multiple_runs else run["name"]
            # Never merge different batches, generators, or parameter configurations.
            key = (str(path.parent), name, run["generator"], run["config_key"])
            groups[key].append(run)
        result = []
        for (_, name, generator, _), members in groups.items():
            values = {metric: average([run["values"][metric] for run in members])
                      for metric in self.report_metric_names()}
            counts = {metric: sum(numeric(run["values"][metric]) for run in members)
                      for metric in self.report_metric_names()}
            complete = [run for run in members
                        if all(numeric(run["axis_scores"][name]) for name in run_axes)]
            score_members = complete or members
            axes = {axis["name"]: average([run["axis_scores"][axis["name"]]
                                          for run in score_members])
                    for axis in self.score_metrics}
            axis_counts = {axis["name"]: sum(numeric(run["axis_scores"][axis["name"]])
                                            for run in score_members)
                           for axis in self.score_metrics}
            # All deviations use the same complete runs; never include consistency itself.
            deviations = {name: pstdev([run["axis_scores"][name] for run in complete])
                          if len(complete) >= 2 else None for name in run_axes}
            if has_consistency:
                axes["performance_consistency"] = (1 - 2 * max(deviations.values())
                                                    if len(complete) >= 2 else None)
                axis_counts["performance_consistency"] = len(complete) if len(complete) >= 2 else 0
            result.append({"name": name, "generator": generator, "run_count": len(members),
                           "values": values, "contributing_runs": counts,
                           "axis_scores": axes, "axis_contributing_runs": axis_counts,
                           "total_score": self.total_score(axes, len(members)) if complete else None,
                           "axis_standard_deviations": deviations,
                           "score_run_count": len(complete),
                           "axis_run_subset": "complete_scores" if complete else "available_per_axis",
                           "epochs": self.average_epochs(members),
                           "runs": [{k: v for k, v in run.items() if k != "config_key"}
                                    for run in members]})
        self.assign_plot_styles(result)
        return result

    @staticmethod
    def assign_plot_styles(groups):
        """Share config colors and unique output names across all report plots."""
        counts = Counter(group["generator"] for group in groups)
        variants = defaultdict(int)
        used_names = set()
        for group in groups:
            generator = group["generator"]
            group["color"] = generator_color(generator, variants[generator], counts[generator])
            variants[generator] += 1
            base = re.sub(r"[^A-Za-z0-9_.-]+", "_", group["name"]).strip("._") or "experiment"
            name, suffix = base, 2
            while name.casefold() in used_names:
                name = f"{base}_{suffix}"
                suffix += 1
            used_names.add(name.casefold())
            group["plot_name"] = name

    def calculate_axis_scores(self, values):
        return {axis["name"]: self.calculate_axis_score(axis, values)
                for axis in self.score_metrics}

    @staticmethod
    def calculate_axis_score(axis, values):
        if axis["name"] == "performance_consistency" or not axis.get("scored", True):
            return None
        weighted, weight_sum = 0.0, 0.0
        for metric, minimum, maximum, reverse, weight in axis["components"]:
            value = values.get(metric)
            if not numeric(value):
                return None
            value = max(0, min(1, (value - minimum) / (maximum - minimum)))
            value = 1 - value if reverse else value
            weighted += weight * value
            weight_sum += weight
        return weighted / weight_sum

    def score_metrics_for_runs(self, run_count):
        return [axis for axis in self.score_metrics
                if run_count != 1 or axis["name"] != "performance_consistency"]

    def total_score(self, axis_scores, run_count=None):
        score_metrics = self.score_metrics_for_runs(run_count)
        if any(not numeric(axis_scores.get(axis["name"])) for axis in score_metrics):
            return None
        return 100 * sum(axis["weight"] * axis_scores[axis["name"]] for axis in score_metrics) / sum(
            axis["weight"] for axis in score_metrics
        )

    def load_epochs(self, analyzer, contexts):
        epochs = {}
        map_names = [name for name, _ in self.epoch_metrics if name not in POPULATION_METRIC_NAMES]
        population_names = [name for name, _ in self.epoch_metrics if name in POPULATION_METRIC_NAMES]
        for epoch, view in analyzer.epoch_views(contexts).items():
            statistics = analyzer.epoch_statistics(view, map_names, population_names)
            epochs[epoch] = {
                name: {"mean": statistics.get(name) if name in POPULATION_METRIC_NAMES else statistics.get(f"{name}_mean"),
                       "max": None if name in POPULATION_METRIC_NAMES else statistics.get(f"{name}_max")}
                for name, _ in self.epoch_metrics
            }
            for values in epochs[epoch].values():
                for key, value in values.items():
                    if not numeric(value):
                        values[key] = None
        return epochs

    def average_epochs(self, runs):
        """Align actual epochs; absent epochs are not extrapolated or filled with zero."""
        epochs = sorted({epoch for run in runs for epoch in run["epochs"]})
        result = {}
        for epoch in epochs:
            result[epoch] = {}
            for name, _ in self.epoch_metrics:
                samples = [run["epochs"].get(epoch, {}).get(name, {}) for run in runs]
                result[epoch][name] = {
                    "mean": average([sample.get("mean") for sample in samples]),
                    "max": average([sample.get("max") for sample in samples]),
                    "contributing_runs": sum(numeric(sample.get("mean")) for sample in samples),
                }
        return result

    def overview_layout(self, groups):
        """Fill columns top-to-bottom, starting each family in a fresh column."""
        families = defaultdict(list)
        for group in groups:
            families[generator_family(group["generator"])].append(group)
        placements, headers, column = [], [], 0
        order = ["constructive", "search_based", "llm_based", "manual"]
        for family in order + sorted(set(families) - set(order)):
            members = families.get(family, [])
            if not members:
                continue
            width = math.ceil(len(members) / 2)
            headers.append((family, column, width))
            for index, group in enumerate(members):
                placements.append((index % 2, column + index // 2, group))
            column += width
        return placements, headers, column

    def draw_overview(self, plt, groups, path):
        placements, headers, columns = self.overview_layout(groups)
        rows = max(row for row, _, _ in placements) + 1
        figure = plt.figure(figsize=(self.chart_size * columns, (self.chart_size + self.bottom_padding) * rows + 0.6))
        grid = figure.add_gridspec(rows, columns, left=0.035, right=0.965,
                                  top=0.84, bottom=0.09, wspace=0.50, hspace=0.70)
        for row, column, group in placements:
            ax = figure.add_subplot(grid[row, column], projection="polar")
            # Reserve space inside each cell for radial labels and run titles.
            bounds = ax.get_position()
            ax.set_position(bounds.shrunk(0.75, 0.75).anchored("C", bounds))
            self.draw_chart(ax, group)
        titles = {"constructive": "Constructive", "search_based": "Search based", "llm_based": "LLM based", "manual": "Manual / other"}
        for family, column, width in headers:
            x = 0.035 + 0.93 * (column + width / 2) / columns
            figure.text(x, 0.965, titles.get(family, family), ha="center", fontsize=16, weight="bold")
        figure.savefig(path, dpi=self.image_dpi, facecolor="white")
        plt.close(figure)

    @staticmethod
    def group_maximum(group, name):
        """One observed maximum per config across its repeated runs and epochs."""
        field = "mean" if name in POPULATION_METRIC_NAMES else "max"
        values = [metrics.get(name, {}).get(field)
                  for run in group["runs"] for metrics in run["epochs"].values()]
        return max((value for value in values if numeric(value)), default=None)

    def draw_epoch_comparison(self, plt, groups, output):
        from matplotlib.ticker import MaxNLocator

        markers = ["o", "s", "^", "D", "v", "P", "X"]
        for name, label in self.epoch_metrics:
            figure, ax = plt.subplots(figsize=(12, 4.5), layout="constrained")
            for index, group in enumerate(groups):
                epochs = sorted(group["epochs"])
                if not epochs:
                    continue
                # Include missing epochs as gaps rather than connecting across them.
                x = list(range(min(epochs), max(epochs) + 1))
                summaries = [group["epochs"].get(epoch, {}).get(name, {}) for epoch in x]
                y = [s.get("mean") if numeric(s.get("mean")) else math.nan for s in summaries]
                color = group.get("color", generator_color(group["generator"]))
                ax.plot(x, y, color=color, marker=markers[index % len(markers)],
                        markersize=4, label=f"{group['name']} ({group['run_count']} runs)")
            if self.show_epoch_maximum:
                for group in groups:
                    maximum = self.group_maximum(group, name)
                    if maximum is not None:
                        ax.axhline(maximum, color=group.get("color", generator_color(group["generator"])),
                                   alpha=0.35, linestyle="--",
                                   label=f"{group['name']} maximum ({maximum:.3g})")
            ax.set(title=label, xlabel="Epoch", ylabel=label)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            ax.grid(alpha=0.2)
            ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
            figure.savefig(output / f"epoch_{name}.png", dpi=self.image_dpi, facecolor="white")
            plt.close(figure)

    def draw_chart(self, ax, group):
        import numpy as np

        score_metrics = self.score_metrics_for_runs(group["run_count"])
        angles = np.linspace(0, 2 * np.pi, len(score_metrics), endpoint=False)
        values, labels = [], []
        for axis in score_metrics:
            name, label = axis["name"], axis["label"]
            value = group["axis_scores"][name]
            values.append(np.nan if value is None else value)
            count = group["axis_contributing_runs"][name]
            suffix = "\nN/A" if not count else (f"\n(n={count})" if count < group["run_count"] else "")
            labels.append(label + suffix)
        color = group.get("color", generator_color(group["generator"]))
        star_angles = np.linspace(0, 2 * np.pi, 2 * len(values), endpoint=False)
        star_values = np.zeros(2 * len(values))
        star_values[::2] = values
        closed_angles = np.r_[star_angles, star_angles[0]]
        closed_values = np.r_[star_values, star_values[0]]
        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.plot(closed_angles, closed_values, color=color, linewidth=2)
        ax.plot(angles, values, linestyle="none", color=color, marker="o", markersize=4)
        if all(np.isfinite(values)):
            ax.fill(closed_angles, closed_values, color=color, alpha=0.16)
        ax.set_xticks(angles, labels, fontsize=9)
        ax.tick_params(axis="x", pad=13)
        ax.set_ylim(-0.25, 1)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0", ".25", ".50", ".75", "1.0"], fontsize=7, color="#64748B")
        ax.grid(color="#CBD5E1", alpha=0.7)
        ax.spines["polar"].set_color("#CBD5E1")
        score = group["total_score"]
        ax.text(0.5, 0.5, "N/A" if score is None else f"{score:.1f}",
                transform=ax.transAxes, ha="center", va="center", fontsize=17,
                weight="bold", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.0})

        ax.set_title(f"{group['name']}\n{group['generator']} | {group['run_count']} run(s)",
                     fontsize=10, color=color, pad=30)

    def run(self, argv=None):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("results_folder", type=Path)
        parser.add_argument("--output", type=Path, help="Override the report directory")
        args = parser.parse_args(argv)
        if not args.results_folder.is_dir():
            parser.error(f"Not a directory: {args.results_folder}")
        try:
            self.validate_score_metrics()
        except ValueError as error:
            parser.error(str(error))
        for name, _ in self.epoch_metrics:
            if name not in NUMERIC_METRIC_NAMES:
                parser.error(f"Invalid epoch metric: {name}")
            if name in RUN_POPULATION_METRICS:
                parser.error(f"Whole-run metric cannot be plotted per epoch: {name}")
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ModuleNotFoundError as error:
            parser.error(f"{error}. Install this toolkit's requirements.txt before plotting.")
        runs, errors = [], []
        for path in self.discover_runs(args.results_folder.resolve()):
            print(f"Reading {path.name}", flush=True)
            try:
                runs.append(self.load_run(path))
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append({"folder": str(path), "error": str(error)})
                warnings.warn(f"Skipping {path.name}: {error}")
        if not runs:
            parser.error("No readable experiment runs found")
        groups = self.group_runs(runs)
        output = args.output or args.results_folder / "experiment_analysis"
        output.mkdir(parents=True, exist_ok=True)
        summary_path = output / "summary.json"
        previous_report = read_json(summary_path) if summary_path.exists() else {}
        previous_maps = previous_report.get("map_visualizations", [])
        if self.create_overview:
            self.draw_overview(plt, groups, output / "overview.png")
        if self.epoch_metrics:
            self.draw_epoch_comparison(plt, groups, output)
        map_images = []
        if self.do_map_visualization:
            from analysis.map_visualizer import create_map_visualizations

            map_images = create_map_visualizations(plt, groups, output, self.image_dpi,
                                                  movement_log_scale=self.movement_log_scale,
                                                  death_log_scale=self.death_log_scale)
            current_names = {path.name for path in map_images}
            for filename in previous_maps:
                if (isinstance(filename, str) and Path(filename).name == filename
                        and filename.startswith("maps_") and filename.endswith(".png")
                        and filename not in current_names):
                    (output / filename).unlink(missing_ok=True)
        graph_images = []
        if self.do_graph_visualization:
            from analysis.graph_visualizer import create_graph_visualizations

            graph_images = create_graph_visualizations(plt, groups, output, self.image_dpi)
            current_names = {path.name for path in graph_images}
            for filename in previous_report.get("graph_visualizations", []):
                if (isinstance(filename, str) and Path(filename).name == filename
                        and filename.startswith("graphs_") and filename.endswith(".png")
                        and filename not in current_names):
                    (output / filename).unlink(missing_ok=True)
        report = {"score_metrics": self.score_metrics, "epoch_metrics": self.epoch_metrics,
                  "expressive_range_definition": "Occupied descriptor-grid cells divided by min(selected map count, grid cell count); default grid is 10 by 10.",
                  "movement_log_scale": self.movement_log_scale,
                  "death_log_scale": self.death_log_scale,
                  "score_definition": "Scored axes normalize and clip run-level component values, then combine them by component weights. Axes with scored=false retain raw measurements but have no quality score. Total is 100 times the weighted mean of the included axes. Single-run groups omit performance consistency from the overview and total; other unscored or unavailable axes make the total unavailable.",
                  "consistency_definition": "Performance consistency = 1 - 2 * max(population standard deviation of each other normalized axis across the same complete runs). The least stable axis determines consistency. At least two complete runs are required; otherwise N/A. axis_standard_deviations uses denominator n, not n-1.",
                  "epoch_maximum_definition": "Horizontal observed maximum per experiment config across its runs and epochs; population metrics use their epoch values", "average_multiple_runs": self.average_multiple_runs,
                  "aggregation": "Raw values average all available runs. Other radar axes average the same runs with complete scores when any exist; otherwise axes average available values and total is unavailable. Performance consistency uses that complete subset. Group total is the weighted mean of the resulting axes, excluding consistency for single-run groups. All run averages have equal weight.",
                  "count_definition": "sample_counts counts maps contributing each raw metric per run; contributing_runs counts runs with each raw metric. axis_contributing_runs counts the runs used for each plotted axis; unavailable consistency has count 0. score_run_count counts runs with all scores other than performance consistency.",
                  "experiments": groups, "skipped_runs": errors,
                  "map_visualizations": [path.name for path in map_images],
                  "graph_visualizations": ([path.name for path in graph_images] if self.do_graph_visualization
                                           else previous_report.get("graph_visualizations", [])),
                  "graph_visualization_enabled": self.do_graph_visualization,
                  "graph_visualization_definition": "Four diagnostic views adapted from Ballabio and Loiacono (2019, IV-C). Regions are a disjoint row-run rectangle decomposition of the final grid, not original All-Black rooms. Region links join shared orthogonal floor boundaries and use Euclidean center distance. Tile links use eight neighbours with weights 1 and sqrt(2), including diagonal corner contacts; simulation and existing four-neighbour metrics are unchanged. Spawn, health and ammo nodes connect to their containing region."}
        (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        print(f"Analyzed {len(groups)} experiment groups from {len(runs)} runs in {output.resolve()}")

