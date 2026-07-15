from __future__ import annotations

import csv
import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from analysis.plots import (
    create_epoch_line_diagram,
    create_epoch_summary_line_diagram,
)
from map_schema.canonical_map import CanonicalMap
from map_schema.map_exporter import load_canonical_map
from metrics.metric_calculator import (
    ANALYSIS_METRIC_NAMES,
    MAP_METRIC_NAMES,
    NON_SCALAR_METRICS,
    NUMERIC_METRIC_NAMES,
    POPULATION_METRIC_NAMES,
    TEXT_METRICS,
    MetricContext,
    PopulationMetricContext,
    available_metric_names,
    calculate_metrics,
    calculate_population_metrics,
    normalize_metric_name,
)


LOGGER = logging.getLogger("FPS-EVALUATOR")


class ExperimentAnalyzer:
    """Post-process one completed experiment before the next JSON starts."""

    def __init__(self, run_dir: Path, experiment: dict[str, Any]):
        self.run_dir = run_dir
        self.experiment = experiment
        self.settings = dict(experiment.get("analysis_settings", {}))
        self.results_csv = run_dir / "results.csv"
        self.results_by_epoch_csv = run_dir / "results_by_epoch.csv"
        self.export_dir = run_dir / "export"

    def run(self) -> dict[str, Any]:
        if bool(self.settings.get("enabled", False)) is False:
            return {"enabled": False}

        records, paths = self._load_records()
        contexts = self._build_contexts(records, paths)
        for context in contexts:
            context.all_records = records
            context.all_contexts = contexts

        requested_metrics = self._requested_metrics()
        requested_map_metrics = [
            name for name in requested_metrics if name in MAP_METRIC_NAMES
        ]
        requested_population_metrics = [
            name for name in requested_metrics if name in POPULATION_METRIC_NAMES
        ]

        LOGGER.info(
            "Analyze experiment '%s' with %s metrics.",
            self.experiment.get("experiment_name"),
            len(requested_metrics),
        )

        unavailable_by_metric: dict[str, int] = {
            name: 0 for name in requested_map_metrics
        }
        experiment_population_context = PopulationMetricContext(
            population_contexts=contexts,
            evaluated_contexts=contexts,
            experiment=self.experiment,
        )
        experiment_metrics: dict[str, Any] = {}
        unavailable_experiment_metrics: dict[str, int] = {
            name: 0 for name in requested_population_metrics
        }

        metric_count = len(requested_metrics)
        for metric_index, metric_name in enumerate(requested_metrics, start=1):
            LOGGER.info(
                "    Analyze %s ... (Metric %s/%s)",
                metric_name,
                metric_index,
                metric_count,
            )
            if metric_name in POPULATION_METRIC_NAMES:
                value = calculate_population_metrics(
                    experiment_population_context,
                    [metric_name],
                )[metric_name]
                experiment_metrics[metric_name] = value
                if value is None:
                    unavailable_experiment_metrics[metric_name] = 1
                continue

            for context in contexts:
                value = calculate_metrics(
                    context.match_records,
                    [metric_name],
                    context,
                )[metric_name]
                context.record.setdefault("metrics", {})[metric_name] = value
                if value is None:
                    unavailable_by_metric[metric_name] += 1

        # Population metrics are deliberately kept out of individual result rows.
        for context, result_path in zip(contexts, paths):
            metrics = context.record.setdefault("metrics", {})
            for name in POPULATION_METRIC_NAMES:
                metrics.pop(name, None)
            context.record["analysis_metrics"] = requested_map_metrics
            context.record["analysis_population_metrics"] = requested_population_metrics
            result_path.write_text(
                json.dumps(context.record, indent=2),
                encoding="utf-8",
            )

        epoch_views = self._build_epoch_views(contexts)
        self._rewrite_results_csv(records, requested_map_metrics)
        epoch_rows, unavailable_by_epoch = self._write_results_by_epoch_csv(
            epoch_views,
            requested_map_metrics,
            requested_population_metrics,
        )
        diagrams = self._create_diagrams(
            epoch_views,
            epoch_rows,
            requested_metrics,
        )

        summary = {
            "enabled": True,
            "record_count": len(records),
            "epoch_count": len(epoch_views),
            "calculated_metrics": requested_metrics,
            "metric_scopes": {
                "individual_map": requested_map_metrics,
                "population_or_generator": requested_population_metrics,
            },
            "unavailable_value_count": unavailable_by_metric,
            "unavailable_epoch_count": unavailable_by_epoch,
            "unavailable_experiment_metric_count": unavailable_experiment_metrics,
            "experiment_metrics": experiment_metrics,
            "diagrams": [str(path.relative_to(self.run_dir)) for path in diagrams],
            "results_csv": str(self.results_csv.relative_to(self.run_dir)),
            "results_by_epoch_csv": str(
                self.results_by_epoch_csv.relative_to(self.run_dir)
            ),
        }
        self.export_dir.mkdir(parents=True, exist_ok=True)
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

    def _load_records(self) -> tuple[list[dict[str, Any]], list[Path]]:
        pairs: list[tuple[dict[str, Any], Path]] = []
        for path in self.run_dir.glob("epoch_*/*.result.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            pairs.append((record, path))
        pairs.sort(
            key=lambda item: (
                int(item[0].get("epoch", 0)),
                int(item[0].get("id", 0)),
            )
        )
        return [item[0] for item in pairs], [item[1] for item in pairs]

    def _build_contexts(
        self,
        records: list[dict[str, Any]],
        paths: list[Path],
    ) -> list[MetricContext]:
        contexts: list[MetricContext] = []
        for record, result_path in zip(records, paths):
            map_id = str(record.get("map_id"))
            epoch = int(record.get("epoch", 0))
            canonical_map = self._load_map(result_path.parent, map_id)
            raw_map_dir = self.run_dir / "_raw" / f"epoch_{epoch:04d}" / map_id
            context = MetricContext(
                canonical_map=canonical_map,
                match_records=self._load_match_records(raw_map_dir),
                record=record,
                raw_map_dir=raw_map_dir,
                experiment=self.experiment,
            )
            contexts.append(context)
        return contexts

    def _build_epoch_views(
        self,
        contexts: list[MetricContext],
    ) -> dict[int, dict[str, Any]]:
        """Build actual population snapshots where checkpoint summaries exist.

        NSGA-II only evaluates changed offspring in later epochs. The checkpoint
        summary lists the full selected population, including carried-over maps and
        duplicate individuals. Other generators fall back to the maps evaluated in
        that epoch.
        """

        evaluated_by_epoch: dict[int, list[MetricContext]] = defaultdict(list)
        context_by_map_id: dict[str, MetricContext] = {}
        for context in contexts:
            epoch = int(context.record.get("epoch", 0))
            evaluated_by_epoch[epoch].append(context)
            context_by_map_id[str(context.record.get("map_id"))] = context

        checkpoint_ids: dict[int, list[str]] = {}
        for path in sorted(self.run_dir.glob("epoch_*/checkpoint_summary.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            epoch = int(payload.get("epoch", path.parent.name.split("_")[-1]))
            selected = payload.get("selected_map_ids", [])
            if isinstance(selected, list):
                checkpoint_ids[epoch] = [str(value) for value in selected]

        epochs = sorted(set(evaluated_by_epoch) | set(checkpoint_ids))
        views: dict[int, dict[str, Any]] = {}
        for epoch in epochs:
            evaluated = list(evaluated_by_epoch.get(epoch, []))
            selected_ids = checkpoint_ids.get(epoch, [])
            population = [
                context_by_map_id[map_id]
                for map_id in selected_ids
                if map_id in context_by_map_id
            ]
            missing = [map_id for map_id in selected_ids if map_id not in context_by_map_id]
            if missing:
                LOGGER.warning(
                    "Epoch %s checkpoint references %s map IDs without result records.",
                    epoch,
                    len(missing),
                )
            if population:
                source = "checkpoint_population"
            else:
                population = evaluated
                source = "evaluated_maps"
            views[epoch] = {
                "population": population,
                "evaluated": evaluated,
                "population_source": source,
            }
        return views

    @staticmethod
    def _load_map(epoch_dir: Path, map_id: str) -> CanonicalMap | None:
        map_path = epoch_dir / f"{map_id}.map.json"
        if map_path.is_file():
            return load_canonical_map(map_path)
        unity_path = epoch_dir / f"{map_id}.unity.json"
        if unity_path.is_file():
            payload = json.loads(unity_path.read_text(encoding="utf-8"))
            map_payload = payload.get("map")
            if isinstance(map_payload, dict):
                return CanonicalMap.from_dict(map_payload)
        return None

    @staticmethod
    def _load_match_records(raw_map_dir: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if raw_map_dir.is_dir() is False:
            return records
        for path in sorted(
            raw_map_dir.glob("simulation_*/Export/final_results_*.json")
        ):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(dict(payload))
            elif isinstance(payload, list):
                records.extend(
                    dict(item) for item in payload if isinstance(item, dict)
                )
        return records

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

            self._add_numeric_stats(
                row,
                "fitness_value",
                [item.record.get("fitness_value") for item in population],
                best_goal="maximize",
            )

            for name in requested_map_metrics:
                values = [item.record.get("metrics", {}).get(name) for item in population]
                available = self._add_metric_epoch_values(
                    row,
                    name,
                    values,
                    goal_by_metric.get(name),
                )
                if available is False:
                    unavailable_by_epoch[name] += 1

            population_values = calculate_population_metrics(
                PopulationMetricContext(
                    population_contexts=population,
                    evaluated_contexts=evaluated,
                    experiment=self.experiment,
                ),
                requested_population_metrics,
            ) if requested_population_metrics else {}
            for name in requested_population_metrics:
                value = population_values.get(name)
                row[name] = "" if value is None else value
                if value is None:
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

    def _add_metric_epoch_values(
        self,
        row: dict[str, Any],
        name: str,
        values: list[Any],
        best_goal: str | None,
    ) -> bool:
        if name in TEXT_METRICS:
            texts = sorted({str(value) for value in values if value is not None})
            row[f"{name}_count"] = len([value for value in values if value is not None])
            row[f"{name}_values"] = "|".join(texts)
            return bool(texts)

        if name in NON_SCALAR_METRICS:
            dictionaries = [value for value in values if isinstance(value, dict)]
            keys = sorted({key for value in dictionaries for key in value})
            row[f"{name}_count"] = len(dictionaries)
            for key in keys:
                self._add_numeric_stats(
                    row,
                    f"{name}__{key}",
                    [value.get(key) for value in dictionaries],
                )
            return bool(dictionaries)

        count = self._add_numeric_stats(row, name, values, best_goal=best_goal)
        return count > 0

    @staticmethod
    def _add_numeric_stats(
        row: dict[str, Any],
        prefix: str,
        values: list[Any],
        best_goal: str | None = None,
    ) -> int:
        numeric = [
            float(value)
            for value in values
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ]
        row[f"{prefix}_count"] = len(numeric)
        if not numeric:
            row[f"{prefix}_mean"] = ""
            row[f"{prefix}_min"] = ""
            row[f"{prefix}_max"] = ""
            row[f"{prefix}_standard_deviation"] = ""
            if best_goal in {"maximize", "minimize"}:
                row[f"{prefix}_best"] = ""
            return 0

        row[f"{prefix}_mean"] = mean(numeric)
        row[f"{prefix}_min"] = min(numeric)
        row[f"{prefix}_max"] = max(numeric)
        row[f"{prefix}_standard_deviation"] = (
            pstdev(numeric) if len(numeric) > 1 else 0.0
        )
        if best_goal == "maximize":
            row[f"{prefix}_best"] = max(numeric)
        elif best_goal == "minimize":
            row[f"{prefix}_best"] = min(numeric)
        return len(numeric)

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
