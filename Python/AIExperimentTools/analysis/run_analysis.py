"""Shared, in-memory analysis of saved experiments. No file writes."""
from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from map_schema.map_exporter import load_saved_map
from metrics.metric_calculator import (
    MetricContext, PopulationMetricContext, NON_SCALAR_METRICS, TEXT_METRICS,
    calculate_metrics, calculate_population_metrics,
)

LOGGER = logging.getLogger("FPS-EVALUATOR")
GENERATION_MAP_METRICS = {"generation_time_per_map", "repair_count", "constraint_violation_count"}
FINAL_POPULATION_METRICS = {"map_diversity", "unique_map_ratio", "expressive_range"}
RUN_POPULATION_METRICS = {
    "generator_efficiency", "generation_time_per_output_map", "generation_cost_per_output_map",
}


class RunAnalysis:
    def __init__(self, run_dir: Path, experiment: dict):
        self.run_dir = run_dir
        self.experiment = experiment

    def load(self):
        records, paths = self.load_records()
        return records, paths, self.build_contexts(records, paths)

    def load_final(self):
        """Load simulation logs only for the selected maps used in galleries."""
        records, paths = self.load_records()
        map_ids = self.final_map_ids(records)
        selected_ids = set(map_ids)
        pairs = [(record, path) for record, path in zip(records, paths)
                 if record["map_id"] in selected_ids]
        contexts = self.build_contexts([record for record, _ in pairs], [path for _, path in pairs])
        return self.select_final(contexts, map_ids)

    def select_final(self, contexts, map_ids=None):
        if map_ids is None:
            map_ids = self.final_map_ids([context.record for context in contexts])
        by_id = {c.record["map_id"]: c for c in contexts}
        missing = set(map_ids) - by_id.keys()
        if missing:
            raise ValueError("Selected maps have no results: " + ", ".join(sorted(missing)))
        return [by_id[map_id] for map_id in map_ids]

    def final_map_ids(self, records):
        map_ids = self.experiment.get("run_metadata", {}).get("final_candidate_map_ids")
        if map_ids is None:
            map_ids = [record["map_id"] for record in records if record.get("final_candidate")]
        return map_ids

    @staticmethod
    def map_values(contexts, name):
        """Reuse saved values; refresh repair counts to match the run exporter."""
        values = []
        for context in contexts:
            saved = context.record.setdefault("metrics", {})
            if name not in saved or name == "repair_count":
                saved.update(calculate_metrics(context.match_records, [name], context))
            values.append(saved.get(name))
        return values

    def metric_statistics(self, contexts, metric_names):
        statistics = {}
        for name in metric_names:
            self.add_metric_statistics(statistics, name, self.map_values(contexts, name), None)
        return {key: None if value == "" else value for key, value in statistics.items()}

    def epoch_statistics(self, view, map_metrics, population_metrics, goals=None):
        row = {}
        goals = goals or {}
        for name in map_metrics:
            self.add_metric_statistics(row, name, self.map_values(view["population"], name), goals.get(name))
        row.update(self.population_metrics(
            view["population"], view["evaluated"], population_metrics, whole_run=False,
        ))
        return row

    def population_metrics(self, population, evaluated, names, *, whole_run=True):
        return calculate_population_metrics(PopulationMetricContext(
            population_contexts=population,
            evaluated_contexts=evaluated,
            experiment=self.experiment,
            run_dir=self.run_dir,
            whole_run=whole_run,
        ), names)

    def load_records(self) -> tuple[list[dict[str, Any]], list[Path]]:
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

    def build_contexts(
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
                record=record,
                raw_map_dir=raw_map_dir,
                experiment=self.experiment,
            )
            context.match_records = self._load_match_records(context)
            contexts.append(context)
        for context in contexts:
            context.all_records = records
            context.all_contexts = contexts
        return contexts

    def epoch_views(
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
            if epoch in checkpoint_ids:
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

    _load_map = staticmethod(load_saved_map)

    @staticmethod
    def _load_match_records(
            context: MetricContext,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        for path in context.raw_files("final_results_*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if isinstance(payload, dict):
                records.append(dict(payload))
            elif isinstance(payload, list):
                records.extend(
                    dict(item)
                    for item in payload
                    if isinstance(item, dict)
                )

        return records

    def add_metric_statistics(
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
            row[f"{name}_count"] = len(dictionaries)
            keys = sorted({key for value in dictionaries for key in value})
            row[f"{name}_count"] = len(dictionaries)
            for key in keys:
                self.add_numeric_statistics(
                    row,
                    f"{name}__{key}",
                    [value.get(key) for value in dictionaries],
                )
            return bool(dictionaries)

        count = self.add_numeric_statistics(row, name, values, best_goal=best_goal)
        return count > 0

    @staticmethod
    def add_numeric_statistics(
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

