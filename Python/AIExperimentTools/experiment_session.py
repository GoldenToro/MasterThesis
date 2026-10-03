from __future__ import annotations

import csv
import importlib
import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from candidate import Candidate
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable
import math
from collections.abc import Generator
from time import monotonic

import numpy as np

from map_schema.canonical_map import CanonicalMap
from map_schema.map_exporter import load_canonical_map, save_canonical_map
from map_schema.map_repairer import MapRepairer
from map_schema.map_validator import MapValidator
from map_schema.map_completion import complete_map, strip_objects
from metrics.metric_calculator import MetricContext, calculate_metrics, normalize_metric_name
from generators.registry import load_generator
from simulation.unity_runner import UnityRunner

LOGGER = logging.getLogger("FPS-EVALUATOR")


class ExperimentSession:
    """Experiment state, map storage, evaluation, and result writing.

    A concrete generator module only creates maps and calls:

        epoch_dir = base.save_epoch_maps(epoch, maps)
        evaluation = base.evaluate_epoch(epoch_dir)

    ``evaluation`` is a NumPy structured array sorted by epoch and numeric map ID.
    """

    def __init__(
            self,
            framework_root: Path,
            output_dir: Path,
            technical_settings: dict[str, Any],
            experiment: dict[str, Any],
    ) -> None:
        self.framework_root = framework_root
        self.output_dir = output_dir
        self.technical_settings = technical_settings
        self.experiment = experiment
        self.generator_settings = dict(experiment.get("generator_settings", {}))
        self.simulator_settings = dict(experiment.get("simulator_settings", {}))
        self.experiment_name = str(experiment["experiment_name"])
        self.generator_name = str(experiment["generator"])
        self.seed = int(experiment["seed"])
        self.production_deadline = None
        self.results_csv = output_dir / "results.csv"

    @property
    def metric_specs(self) -> list[dict[str, Any]]:
        fitness = self.generator_settings.get("fitness", {})
        return [dict(value) for value in fitness.get("metrics", [])]

    @property
    def objective_names(self) -> list[str]:
        return [
            normalize_metric_name(str(specification["name"]))
            for specification in self.metric_specs
        ]

    def production_time_expired(self):
        return (
                self.production_deadline is not None
                and monotonic() >= self.production_deadline
        )
    def start(self) -> list[str]:
        """Control generation limits and select the final outputs."""
        settings = self.generator_settings
        num_epochs = settings.get("num_epochs", 0)
        seconds = settings.get("max_time_seconds", 0)
        final_count = settings.get("final_map_count")

        if type(num_epochs) is not int or num_epochs < 0:
            raise ValueError("num_epochs must be a non-negative integer")
        if (
                type(seconds) not in (int, float)
                or not math.isfinite(seconds)
                or seconds < 0
        ):
            raise ValueError("max_time_seconds must be finite and non-negative")
        if final_count is not None and (
                type(final_count) is not int or final_count <= 0
        ):
            raise ValueError("final_map_count must be a positive integer")

        run_function = load_generator(self.generator_name)
        steps = run_function(self)
        if not isinstance(steps, Generator):
            raise TypeError("Generator run() must yield completed populations")

        self.production_deadline = monotonic() + seconds if seconds > 0 else None
        population: list[str] = []

        try:
            # Initial generation, followed by at most num_epochs updates.
            for _ in range(num_epochs + 1):
                if self.production_time_expired():
                    LOGGER.info("Generation time limit reached.")
                    break

                try:
                    population = next(steps)
                except StopIteration:
                    break
        finally:
            steps.close()
            self.production_deadline = None

        final_map_ids = self._select_final_maps(population)
        self.mark_final_candidates(final_map_ids)
        return final_map_ids

    def evaluate_candidates(
            self,
            candidates: Iterable[Candidate],
            epoch: int,
    ) -> list[Candidate]:
        """Evaluate a fresh batch once and return the same candidates in order."""
        batch = list(candidates)
        if not batch:
            return []

        epoch_dir = self.output_dir / f"epoch_{epoch:04d}"
        map_ids = {candidate.map_id for candidate in batch}
        map_paths = {epoch_dir / f"{map_id}.map.json" for map_id in map_ids}

        if len(map_paths) != len(batch):
            raise ValueError("Map IDs must be unique within a batch")
        if any(candidate.evaluation is not None for candidate in batch):
            raise ValueError("Submit new candidates without an evaluation")

        for map_id in map_ids:
            for suffix in (".map.json", ".result.json"):
                if (epoch_dir / f"{map_id}{suffix}").exists():
                    raise FileExistsError(
                        f"Map '{map_id}' already has saved data in {epoch_dir}"
                    )

        existing_maps = [
            load_canonical_map(path)
            for path in epoch_dir.glob("*.map.json")
        ]
        next_id = 1 + max(
            (self._map_sort_key(item)[1] for item in existing_maps),
            default=-1,
        )

        self.save_epoch_maps(
            epoch,
            (candidate.canonical_map for candidate in batch),
            numeric_id_start=next_id,
        )
        self.evaluate_epoch(epoch_dir, map_ids=map_ids)

        for candidate in batch:
            map_id = candidate.map_id
            candidate.canonical_map = load_canonical_map(
                epoch_dir / f"{map_id}.map.json"
            )
            result_path = epoch_dir / f"{map_id}.result.json"
            candidate.evaluation = json.loads(
                result_path.read_text(encoding="utf-8")
            )

        return batch

    def save_epoch_maps(
            self,
            epoch: int,
            maps: Iterable[CanonicalMap],
            numeric_id_start: int = 0,
    ) -> Path:
        """Store one evaluation batch in one epoch folder."""
        epoch_dir = self.output_dir / f"epoch_{epoch:04d}"
        epoch_dir.mkdir(parents=True, exist_ok=True)

        for numeric_id, canonical_map in enumerate(
                maps,
                start=numeric_id_start,
        ):
            metadata = dict(canonical_map.metadata)
            metadata["epoch"] = int(epoch)
            metadata["id"] = int(numeric_id)
            metadata.setdefault("generator", self.generator_name)
            metadata["map_scale"] = float(self.generator_settings["map_scale"])

            normalized_map = replace(canonical_map, metadata=metadata)
            save_canonical_map(
                normalized_map,
                epoch_dir / f"{normalized_map.map_id}.map.json",
            )

        return epoch_dir

    def evaluate_epoch(
            self,
            epoch_dir: Path,
            map_ids: set[str] | None = None,
    ) -> np.ndarray:
        """Evaluate selected saved maps, or all maps when no IDs are given."""
        map_files = sorted(epoch_dir.glob("*.map.json"))

        if map_ids is not None:
            requested_files = {
                f"{map_id}.map.json"
                for map_id in map_ids
            }
            map_files = [
                path
                for path in map_files
                if path.name in requested_files
            ]

        if len(map_files) == 0:
            return self._records_to_numpy([])

        maps = [load_canonical_map(path) for path in map_files]
        maps.sort(key=self._map_sort_key)

        execution = self.technical_settings.get("execution", {})
        configured_workers = int(
            execution.get("max_parallel_map_evaluations", 1)
        )
        max_workers = max(1, min(configured_workers, len(maps)))

        LOGGER.info(
            "Start evaluating %s maps in %s with up to %s workers.",
            len(maps),
            epoch_dir.name,
            max_workers,
        )

        def evaluate(canonical_map: CanonicalMap) -> dict[str, Any]:
            return self._evaluate_map(canonical_map, epoch_dir)

        if max_workers == 1:
            records = [
                evaluate(canonical_map)
                for canonical_map in maps
            ]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                records = list(executor.map(evaluate, maps))

        records.sort(
            key=lambda record: (
                int(record["epoch"]),
                int(record["id"]),
            )
        )

        self._append_results_csv(records)
        LOGGER.info("Finished evaluating %s.", epoch_dir.name)

        return self._records_to_numpy(records)

    def mark_final_candidates(self, map_ids: Iterable[str]) -> None:
        """Mark the final population inside the existing results.csv file."""
        if self.results_csv.is_file() is False:
            return
        selected = {str(value) for value in map_ids}
        with self.results_csv.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        if len(rows) == 0:
            return
        for row in rows:
            row["final_candidate"] = str(row.get("map_id") in selected).lower()
        with self.results_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(rows[0].keys()),
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(rows)

        for result_path in self.output_dir.glob("epoch_*/*.result.json"):
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["final_candidate"] = str(payload.get("map_id")) in selected
            result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def copy_final_candidate_maps(self, map_ids: Iterable[str]) -> list[Path]:
        """Copy final-candidate Unity input JSON files into the run export folder.

        The behavior is controlled by
        ``generator_settings.copy_final_candidate_maps``. Missing Unity inputs are
        reported and skipped, which allows dry runs and invalid maps to complete.
        """
        if bool(self.generator_settings.get("copy_final_candidate_maps", False)) is False:
            return []

        selected = sorted({str(value) for value in map_ids})
        export_dir = self.output_dir / "export"
        export_dir.mkdir(parents=True, exist_ok=True)

        copied: list[Path] = []
        for map_id in selected:
            matches = sorted(
                self.output_dir.glob(f"epoch_*/{map_id}.unity.json")
            )
            if len(matches) == 0:
                LOGGER.warning(
                    "Final candidate '%s' has no Unity JSON to copy.",
                    map_id,
                )
                continue

            source = matches[-1]
            destination = export_dir / source.name
            shutil.copy2(source, destination)
            copied.append(destination)

        LOGGER.info(
            "Copied %s/%s final-candidate Unity JSON files to %s.",
            len(copied),
            len(selected),
            export_dir,
        )
        return copied

    def cleanup_outputs(self) -> None:
        """Remove temporary data after analysis has returned successfully."""
        for map_path in self.output_dir.glob("epoch_*/*.map.json"):
            unity_path = map_path.with_name(
                map_path.name.removesuffix(".map.json") + ".unity.json"
            )
            if unity_path.is_file():
                map_path.unlink()

        analysis_settings = self.experiment.get("analysis_settings", {})
        if bool(analysis_settings.get("only_keep_result_summary", False)):
            for directory_name in ("_raw", "llm_map_attempts"):
                directory = self.output_dir / directory_name
                if directory.is_dir():
                    shutil.rmtree(directory)

            for checkpoint_path in self.output_dir.glob(
                    "epoch_*/checkpoint.pkl"
            ):
                checkpoint_path.unlink()

            return

        raw_dir = self.output_dir / "_raw"
        self._remove_empty_directories(raw_dir)
        if raw_dir.is_dir() and next(raw_dir.iterdir(), None) is None:
            raw_dir.rmdir()
    def _select_final_maps(self, map_ids):
        if not map_ids:
            return []

        count = self.generator_settings.get("final_map_count")
        if count is None:
            count = len(map_ids)

        with self.results_csv.open(
                "r", newline="", encoding="utf-8"
        ) as handle:
            records = {
                row["map_id"]: row
                for row in csv.DictReader(handle, delimiter=";")
            }

        missing = set(map_ids) - records.keys()
        if missing:
            raise ValueError(
                "Final candidates have no results: "
                + ", ".join(sorted(missing))
            )

        eligible = []
        for map_id in map_ids:
            record = records[map_id]

            if record.get("valid") != "true":
                continue
            if record.get("status") not in {
                "completed",
                "partial_failure",
                "partial_evaluation",
                "simulation_disabled",
            }:
                continue

            try:
                fitness = float(record.get("fitness_value"))
            except (TypeError, ValueError):
                continue

            if math.isfinite(fitness):
                eligible.append((map_id, fitness))

        eligible.sort(key=lambda item: item[1], reverse=True)
        selected = [map_id for map_id, _ in eligible[:count]]

        if len(selected) < count:
            LOGGER.warning(
                "Requested %s final maps; only %s eligible outputs "
                "are available. No replacements will be generated.",
                count,
                len(selected),
            )

        return selected

    def _evaluate_map(
            self,
            canonical_map: CanonicalMap,
            epoch_dir: Path,
    ) -> dict[str, Any]:
        generation = self.generator_settings
        completion = generation["map_completion"]
        generic_placement = completion["mode"] == "generic"

        validation_settings = dict(generation.get("validation", {}))
        validation_settings["expected_width"] = generation.get("map_width")
        validation_settings["expected_height"] = generation.get("map_height")
        validation_settings["minimum_spawn_count"] = max(
            2, int(validation_settings.get("minimum_spawn_count", 2))
        )

        layout_settings = {
            **validation_settings,
            "minimum_spawn_count": 0,
        }
        layout_validator = MapValidator(layout_settings)

        if generic_placement:
            canonical_map = strip_objects(canonical_map)

        validation_before = layout_validator.validate(canonical_map)
        repair_report: dict[str, Any] = {
            "changed": False,
            "actions": [],
        }
        repair_error = None

        dimensions_match = (
                validation_settings["expected_width"]
                in (None, canonical_map.width)
                and validation_settings["expected_height"]
                in (None, canonical_map.height)
        )
        needs_connection = (
                bool(layout_settings.get("require_single_connected_region", True))
                and validation_before.measured["connected_components"] > 1
        )

        if (
                generation.get("repair_enabled", False)
                and dimensions_match
                and needs_connection
        ):
            try:
                canonical_map, repair = MapRepairer().repair(
                    canonical_map,
                    max_changed_cells=generation["repair_max_changed_cells"],
                )
                repair_report = repair.to_dict()
            except ValueError as exc:
                repair_error = str(exc)

        completion_error = None
        if generic_placement and layout_validator.validate(canonical_map).valid:
            try:
                canonical_map = complete_map(
                    canonical_map,
                    seed=completion["seed"],
                    health_count=completion["health_count"],
                    ammo_count=completion["ammo_count"],
                )
            except ValueError as exc:
                completion_error = str(exc)

        validation = MapValidator(validation_settings).validate(canonical_map)

        if repair_error is not None:
            validation.valid = False
            validation.errors.append(f"Repair rejected: {repair_error}")

        if completion_error is not None:
            validation.valid = False
            validation.errors.append(
                f"Map completion failed: {completion_error}"
            )

        save_canonical_map(
            canonical_map,
            epoch_dir / f"{canonical_map.map_id}.map.json",
        )

        epoch, numeric_id = self._map_sort_key(canonical_map)
        match_records: list[dict[str, Any]] = []
        requested = int(self.simulator_settings.get("simulations_per_map", 1))
        successful = 0
        failed = 0
        skipped = 0
        failures: list[dict[str, Any]] = []

        simulator_enabled = bool(self.simulator_settings.get("enabled", True))
        if validation.valid is False:
            status = "skipped_invalid_map"
            requested = 0
            LOGGER.warning(
                "Skip simulation for map '%s': %s",
                canonical_map.map_id,
                "; ".join(validation.errors) or "invalid map",
            )
        elif simulator_enabled is False:
            status = "simulation_disabled"
            requested = 0
        else:
            unity_result = UnityRunner(
                self.framework_root,
                self.technical_settings,
            ).run(
                canonical_map=canonical_map,
                run_dir=self.output_dir,
                epoch_dir=epoch_dir,
                simulator_settings=self.simulator_settings,
                epoch=epoch,
                numeric_id=numeric_id,
                production_deadline=self.production_deadline,
            )
            match_records = unity_result.match_records
            requested = unity_result.simulation_count_requested
            successful = unity_result.simulation_count_successful
            failed = unity_result.simulation_count_failed
            skipped = unity_result.simulation_count_skipped
            failures = unity_result.failures

            if successful > 0:
                if failed:
                    status = "partial_failure"
                elif skipped:
                    status = "partial_evaluation"
                else:
                    status = "completed"
            elif failed:
                status = "failed"
            else:
                status = "budget_exhausted"

        metric_context = MetricContext(
            canonical_map=canonical_map,
            match_records=match_records,
            record={
                "repair": repair_report,
                "validation_before_repair": validation_before.to_dict(),
                "validation": validation.to_dict(),
                "failed_simulations": failures,
            },
            raw_map_dir=(
                    self.output_dir
                    / "_raw"
                    / f"epoch_{epoch:04d}"
                    / canonical_map.map_id
            ),
            experiment=self.experiment,
        )
        metrics = calculate_metrics(
            match_records,
            self.objective_names,
            metric_context,
        )
        fitness_metrics = self._apply_missing_metric_penalties(
            metrics,
            force_penalty=(
                    validation.valid is False
                    or status in {"failed", "budget_exhausted"}
            ),
        )
        fitness_value = self._calculate_fitness(fitness_metrics)

        record = {
            "experiment": self.experiment_name,
            "generator": self.generator_name,
            "epoch": epoch,
            "id": numeric_id,
            "map_id": canonical_map.map_id,
            "valid": bool(validation.valid),
            "status": status,
            "simulations_requested": requested,
            "simulations_successful": successful,
            "simulations_failed": failed,
            "simulations_skipped": skipped,
            "match_count": len(match_records),
            "metrics": metrics,
            "fitness_metrics": fitness_metrics,
            "fitness_value": fitness_value,
            "final_candidate": False,
            "validation_before_repair": validation_before.to_dict(),
            "repair": repair_report,
            "validation": validation.to_dict(),
            "failed_simulations": failures,
        }
        result_path = epoch_dir / f"{canonical_map.map_id}.result.json"
        result_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

        return record

    def _apply_missing_metric_penalties(
            self,
            values: dict[str, float | None],
            force_penalty: bool,
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for specification in self.metric_specs:
            name = normalize_metric_name(str(specification["name"]))
            value = values.get(name)
            if force_penalty or value is None:
                goal = str(specification.get("goal", "maximize"))
                if goal == "maximize":
                    value = float(specification.get("minimum", 0.0))
                elif goal == "minimize":
                    value = float(specification.get("maximum", 1.0))
                else:
                    raise ValueError(
                        f"Unsupported fitness goal '{goal}' for metric '{name}'"
                    )
            result[name] = float(value)
        return result

    def _calculate_fitness(self, metrics: dict[str, float]) -> float:
        weighted_sum = 0.0
        total_weight = 0.0
        for specification in self.metric_specs:
            name = normalize_metric_name(str(specification["name"]))
            minimum = float(specification.get("minimum", 0.0))
            maximum = float(specification.get("maximum", 1.0))
            if maximum <= minimum:
                raise ValueError(
                    f"Fitness maximum must exceed minimum for metric '{name}'"
                )
            normalized = min(
                1.0,
                max(0.0, (metrics[name] - minimum) / (maximum - minimum)),
            )
            goal = str(specification.get("goal", "maximize"))
            if goal == "minimize":
                normalized = 1.0 - normalized
            elif goal != "maximize":
                raise ValueError(
                    f"Unsupported fitness goal '{goal}' for metric '{name}'"
                )
            weight = float(specification.get("weight", 1.0))
            weighted_sum += weight * normalized
            total_weight += weight
        return weighted_sum / total_weight if total_weight else 0.0

    def _append_results_csv(self, records: list[dict[str, Any]]) -> None:
        fieldnames = [
            "experiment",
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
            *self.objective_names,
            "fitness_value",
            "final_candidate",
        ]
        rows: list[dict[str, Any]] = []
        for record in records:
            row = {
                "experiment": record["experiment"],
                "epoch": record["epoch"],
                "id": record["id"],
                "map_id": record["map_id"],
                "valid": str(record["valid"]).lower(),
                "status": record["status"],
                "simulations_requested": record["simulations_requested"],
                "simulations_successful": record["simulations_successful"],
                "simulations_failed": record["simulations_failed"],
                "simulations_skipped": record["simulations_skipped"],
                "match_count": record["match_count"],
                "fitness_value": record["fitness_value"],
                "final_candidate": str(record["final_candidate"]).lower(),
            }
            row.update(record["metrics"])
            rows.append(row)

        write_header = self.results_csv.is_file() is False
        with self.results_csv.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                delimiter=";",
            )
            if write_header:
                writer.writeheader()
            writer.writerows(rows)

    def _records_to_numpy(self, records: list[dict[str, Any]]) -> np.ndarray:
        dtype: list[tuple[str, Any]] = [
            ("experiment", "U128"),
            ("epoch", np.int64),
            ("id", np.int64),
            ("map_id", "U160"),
            ("valid", np.bool_),
            ("status", "U64"),
        ]
        dtype.extend((name, np.float64) for name in self.objective_names)
        dtype.append(("fitness_value", np.float64))

        values = []
        for record in records:
            row: list[Any] = [
                record["experiment"],
                record["epoch"],
                record["id"],
                record["map_id"],
                record["valid"],
                record["status"],
            ]
            row.extend(
                float("nan") if record["metrics"][name] is None
                else record["metrics"][name]
                for name in self.objective_names
            )
            row.append(record["fitness_value"])
            values.append(tuple(row))
        return np.array(values, dtype=dtype)

    @staticmethod
    def _map_sort_key(canonical_map: CanonicalMap) -> tuple[int, int]:
        metadata = canonical_map.metadata
        return int(metadata.get("epoch", 0)), int(metadata.get("id", 0))

    @classmethod
    def _remove_empty_directories(cls, root: Path) -> None:
        if root.is_dir() is False:
            return
        for child in list(root.iterdir()):
            if child.is_dir():
                cls._remove_empty_directories(child)
                if child.exists() and next(child.iterdir(), None) is None:
                    child.rmdir()
