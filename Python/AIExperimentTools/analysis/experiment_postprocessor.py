from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from analysis.run_analysis import (
    RunAnalysis, GENERATION_MAP_METRICS, FINAL_POPULATION_METRICS,
    RUN_POPULATION_METRICS,
)

from analysis.plots import (
    create_epoch_line_diagram,
    create_epoch_summary_line_diagram,
)
from metrics.metric_calculator import (
    ANALYSIS_METRIC_NAMES,
    MAP_METRIC_NAMES,
    NON_SCALAR_METRICS,
    NUMERIC_METRIC_NAMES,
    POPULATION_METRIC_NAMES,
    MetricContext,
    available_metric_names,
    normalize_metric_name,
)


LOGGER = logging.getLogger("FPS-EVALUATOR")


class ExperimentPostprocessor:
    """Post-process one completed run before the next JSON starts."""

    def __init__(self, run_dir: Path, experiment: dict[str, Any]):
        self.analysis = RunAnalysis(run_dir, experiment)
        self.run_dir = run_dir
        self.experiment = experiment
        self.settings = dict(experiment.get("analysis_settings", {}))
        self.results_csv = run_dir / "results.csv"
        self.results_by_epoch_csv = run_dir / "results_by_epoch.csv"
        self.export_dir = run_dir / "export"

    def run(self, final_map_ids) -> dict[str, Any]:
        if bool(self.settings.get("enabled", False)) is False:
            return {"enabled": False}

        records, paths, contexts = self.analysis.load()
        final_contexts = self.analysis.select_final(contexts, final_map_ids)

        requested_metrics = self._requested_metrics()
        requested_map_metrics = [
            name for name in requested_metrics if name in MAP_METRIC_NAMES
        ]
        requested_population_metrics = [
            name for name in requested_metrics if name in POPULATION_METRIC_NAMES
        ]

        generator_descriptors = GENERATION_MAP_METRICS | {
            "generator_method_label", "genome_representation_type",
        }
        generator_map_metrics = [
            name for name in requested_map_metrics
            if name in generator_descriptors
        ]
        final_map_metrics = [
            name for name in requested_map_metrics
            if name not in generator_descriptors
        ]
        final_population_metrics = [
            name for name in requested_population_metrics
            if name in FINAL_POPULATION_METRICS
        ]
        generator_population_metrics = [
            name for name in requested_population_metrics
            if name not in final_population_metrics
        ]

        LOGGER.info(
            "Analyze %s generated maps and %s selected population members.",
            len(contexts),
            len(final_contexts),
        )

        generator_statistics = self.analysis.metric_statistics(
            contexts, generator_map_metrics
        )
        generator_values = self.analysis.population_metrics(
            final_contexts, contexts, generator_population_metrics
        )

        diagram_names = {
            normalize_metric_name(name)
            for name in self.settings.get("create_diagram_for_metric", [])
        }

        for name in requested_map_metrics:
            if name in diagram_names:
                self.analysis.map_values(contexts, name)

        history_names = (
            set(self._goal_by_metric())
            | set(generator_map_metrics)
            | diagram_names
        )
        history_map_metrics = [
            name for name in requested_map_metrics
            if name in history_names
        ]
        history_population_metrics = [
            name for name in requested_population_metrics
            if name not in RUN_POPULATION_METRICS
            and (name in generator_population_metrics or name in diagram_names)
        ]

        epoch_views = self.analysis.epoch_views(contexts)
        epoch_rows, unavailable_by_epoch = self._write_results_by_epoch_csv(
            epoch_views,
            history_map_metrics,
            history_population_metrics,
        )
        diagrams = self._create_diagrams(
            epoch_views,
            epoch_rows,
            history_map_metrics + history_population_metrics,
        )

        final_analysis = {
            "selected_map_count": len(final_contexts),
            "map_statistics": self.analysis.metric_statistics(
                final_contexts, final_map_metrics
            ),
            "population_metrics": self.analysis.population_metrics(
                final_contexts, final_contexts, final_population_metrics
            ),
        }

        for context, result_path in zip(contexts, paths):
            result_path.write_text(
                json.dumps(context.record, indent=2),
                encoding="utf-8",
            )
        self._rewrite_results_csv(records, requested_map_metrics)

        self.export_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.export_dir / "analysis_final.json"
        final_path.write_text(
            json.dumps(final_analysis, indent=2),
            encoding="utf-8",
        )

        summary = {
            "enabled": True,
            "record_count": len(records),
            "epoch_count": len(epoch_views),
            "calculated_metrics": requested_metrics,
            "metric_scopes": {
                "individual_map": generator_map_metrics,
                "population_or_generator": generator_population_metrics,
            },
            "map_statistics": generator_statistics,
            "experiment_metrics": generator_values,
            "unavailable_value_count": {
                name: len(contexts) - generator_statistics[f"{name}_count"]
                for name in generator_map_metrics
            },
            "unavailable_epoch_count": unavailable_by_epoch,
            "unavailable_experiment_metric_count": {
                name: int(value is None)
                for name, value in generator_values.items()
            },
            "diagrams": [str(path.relative_to(self.run_dir)) for path in diagrams],
            "results_csv": str(self.results_csv.relative_to(self.run_dir)),
            "results_by_epoch_csv": str(
                self.results_by_epoch_csv.relative_to(self.run_dir)
            ),
            "analysis_final": str(final_path.relative_to(self.run_dir)),
        }
        (self.export_dir / "analysis_summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        LOGGER.info("Finished analysis. Exports: %s", self.export_dir)
        return summary

    def _requested_metrics(self) -> list[str]:
        if bool(self.settings.get("calculate_all_metrics", False)):
            requested = list(ANALYSIS_METRIC_NAMES)
        else:
            requested = [
                normalize_metric_name(value)
                for value in self.settings.get("calculate_metric", [])
            ]

        requested.extend(
            normalize_metric_name(value)
            for value in self.settings.get("create_diagram_for_metric", [])
        )
        objective_names = [
            normalize_metric_name(specification.get("name", ""))
            for specification in self.experiment.get("generator_settings", {})
            .get("fitness", {})
            .get("metrics", [])
        ]
        requested.extend(name for name in objective_names if name)

        available = set(available_metric_names())
        unknown = sorted({name for name in requested if name not in available})
        if unknown:
            raise ValueError(
                "Unknown analysis metrics: "
                + ", ".join(unknown)
                + ". Available metrics: "
                + ", ".join(sorted(available))
            )
        return list(dict.fromkeys(requested))

    def _rewrite_results_csv(
        self,
        records: list[dict[str, Any]],
        requested_map_metrics: list[str],
    ) -> None:
        base_fields = [
            "experiment",
            "generator",
            "epoch",
            "id",
            "map_id",
            "valid",
            "status",
            "simulations_requested",
            "simulations_successful",
            "simulations_failed",
            "simulations_skipped",
            "match_count",
        ]
        metric_fields = list(dict.fromkeys(requested_map_metrics))
        final_fields = ["fitness_value", "final_candidate"]
        fieldnames = base_fields + metric_fields + final_fields

        rows: list[dict[str, Any]] = []
        for record in records:
            row = {field: record.get(field) for field in base_fields}
            row["valid"] = str(bool(record.get("valid"))).lower()
            for name in metric_fields:
                value = record.get("metrics", {}).get(name)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, separators=(",", ":"), sort_keys=True)
                row[name] = "" if value is None else value
            row["fitness_value"] = record.get("fitness_value")
            row["final_candidate"] = str(bool(record.get("final_candidate"))).lower()
            rows.append(row)

        with self.results_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def _write_results_by_epoch_csv(
        self,
        epoch_views: dict[int, dict[str, Any]],
        requested_map_metrics: list[str],
        requested_population_metrics: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        goal_by_metric = self._goal_by_metric()
        unavailable_by_epoch = {
            name: 0 for name in requested_map_metrics + requested_population_metrics
        }
        rows: list[dict[str, Any]] = []

        for epoch, view in sorted(epoch_views.items()):
            population: list[MetricContext] = view["population"]
            evaluated: list[MetricContext] = view["evaluated"]
            row: dict[str, Any] = {
                "experiment": self.experiment.get("experiment_name"),
                "generator": self.experiment.get("generator"),
                "epoch": epoch,
                "population_source": view["population_source"],
                "population_size": len(population),
                "unique_map_count": len(
                    {str(item.record.get("map_id")) for item in population}
                ),
                "newly_evaluated_count": len(evaluated),
                "newly_valid_count": sum(
                    bool(item.record.get("valid")) for item in evaluated
                ),
                "newly_invalid_count": sum(
                    bool(item.record.get("valid")) is False for item in evaluated
                ),
            }

            self.analysis.add_numeric_statistics(
                row,
                "fitness_value",
                [item.record.get("fitness_value") for item in population],
                best_goal="maximize",
            )

            statistics = self.analysis.epoch_statistics(
                view, requested_map_metrics, requested_population_metrics, goal_by_metric
            )
            row.update({key: "" if value is None else value for key, value in statistics.items()})
            for name in requested_map_metrics:
                if not statistics.get(f"{name}_count", 0):
                    unavailable_by_epoch[name] += 1
            for name in requested_population_metrics:
                if statistics.get(name) is None:
                    unavailable_by_epoch[name] += 1

            rows.append(row)

        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with self.results_by_epoch_csv.open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
        return rows, unavailable_by_epoch

    def _create_diagrams(
        self,
        epoch_views: dict[int, dict[str, Any]],
        epoch_rows: list[dict[str, Any]],
        requested_metrics: list[str],
    ) -> list[Path]:
        created: list[Path] = []
        self.export_dir.mkdir(parents=True, exist_ok=True)
        goal_by_metric = self._goal_by_metric()
        records_by_epoch = {
            epoch: [item.record for item in view["population"]]
            for epoch, view in epoch_views.items()
        }

        if bool(self.settings.get("create_diagram_fitness", False)):
            path = create_epoch_line_diagram(
                records_by_epoch,
                "fitness_value",
                self.export_dir / "fitness_by_epoch.png",
                title="Fitness by epoch",
                best_goal="maximize",
            )
            if path:
                created.append(path)

        row_by_epoch = {int(row["epoch"]): row for row in epoch_rows}
        for raw_name in self.settings.get("create_diagram_for_metric", []):
            name = normalize_metric_name(raw_name)
            if name not in requested_metrics:
                continue
            if name not in NUMERIC_METRIC_NAMES or name in NON_SCALAR_METRICS:
                LOGGER.warning("Skip diagram for non-scalar metric '%s'.", name)
                continue

            if name in POPULATION_METRIC_NAMES:
                path = create_epoch_summary_line_diagram(
                    {
                        epoch: row.get(name)
                        for epoch, row in row_by_epoch.items()
                        if isinstance(row.get(name), (int, float))
                    },
                    name,
                    self.export_dir / f"{name}_by_epoch.png",
                )
            else:
                path = create_epoch_line_diagram(
                    records_by_epoch,
                    name,
                    self.export_dir / f"{name}_by_epoch.png",
                    best_goal=goal_by_metric.get(name),
                )
            if path:
                created.append(path)
        return created

    def _goal_by_metric(self) -> dict[str, str]:
        return {
            normalize_metric_name(specification.get("name", "")): str(
                specification.get("goal", "maximize")
            )
            for specification in self.experiment.get("generator_settings", {})
            .get("fitness", {})
            .get("metrics", [])
        }
