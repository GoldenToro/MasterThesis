from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import secrets
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis.experiment_analyzer import ExperimentAnalyzer
from experiment_session import ExperimentSession


LOGGER = logging.getLogger("FPS-EVALUATOR")


class ExperimentManager:
    def __init__(self, framework_root: Path | None = None):
        self._configure_logging()
        self.framework_root = framework_root or Path(__file__).resolve().parent
        self.settings = self._load_json(
            self.framework_root / "configs" / "settings.json"
        )

    @staticmethod
    def _configure_logging() -> None:
        if logging.getLogger().handlers:
            return
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    def run_config(
        self,
        config_path: Path,
        dry_run: bool = False,
        *,
        batch_dir: Path | None = None,
    ) -> Path:
        source_experiment = self._load_json(config_path)
        experiment = copy.deepcopy(source_experiment)
        generator_settings = experiment.setdefault("generator_settings", {})
        generator_settings.setdefault(
            "map_scale",
            self.settings.get("unity", {}).get("map_scale", 2.0),
        )
        experiment["seed"] = self._resolve_seed(experiment.get("generator_settings", {}).get("seed"))
        if dry_run:
            experiment.setdefault("simulator_settings", {})["enabled"] = False

        self._validate_experiment(experiment, config_path)
        started_at = datetime.now().astimezone()

        if batch_dir is None:
            batch_dir = self._create_batch_directory(started_at)

        run_dir = self._create_run_directory(
            str(experiment["experiment_name"]),
            batch_dir,
        )
        (run_dir / "_raw").mkdir(parents=True, exist_ok=True)

        # Keep the submitted configuration unchanged.
        # Resolved settings and run information are saved separately.
        shutil.copy2(config_path, run_dir / "experiment.json")

        metadata: dict[str, Any] = {
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "duration_seconds": None,
            "status": "running",
            "successful": None,
            "framework_version": self.settings.get(
                "framework_version",
                "unknown",
            ),
            "source_config": str(config_path.resolve()),
            "dry_run": bool(dry_run),
        }
        self._write_evaluated_experiment(run_dir, experiment, metadata)

        LOGGER.info(
            "Start experiment '%s' with generator '%s' and seed %s.",
            experiment["experiment_name"],
            experiment["generator"],
            experiment["seed"],
        )

        base_generator = ExperimentSession(
            framework_root=self.framework_root,
            output_dir=run_dir,
            technical_settings=self.settings,
            experiment=experiment,
        )
        try:
            final_map_ids = base_generator.start()
            metadata["final_candidate_map_ids"] = list(final_map_ids)
            self._write_evaluated_experiment(run_dir, experiment, metadata)
            copied_final_candidate_maps = base_generator.copy_final_candidate_maps(
                final_map_ids
            )
            analysis_summary = ExperimentAnalyzer(
                run_dir, experiment
            ).run(final_map_ids)
            base_generator.cleanup_outputs()

            finished_at = datetime.now().astimezone()
            metadata.update(
                {
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(
                        (finished_at - started_at).total_seconds(),
                        6,
                    ),
                    "status": "completed",
                    "successful": True,
                    "final_candidate_map_ids": list(final_map_ids),
                    "copied_final_candidate_maps": [
                        str(path.relative_to(run_dir))
                        for path in copied_final_candidate_maps
                    ],
                    "analysis": analysis_summary,
                }
            )
            self._write_evaluated_experiment(run_dir, experiment, metadata)

            LOGGER.info("Finished experiment '%s'.", experiment["experiment_name"])
            return run_dir
        except Exception as exc:
            finished_at = datetime.now().astimezone()
            metadata.update(
                {
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(
                        (finished_at - started_at).total_seconds(),
                        6,
                    ),
                    "status": "failed",
                    "successful": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            self._write_evaluated_experiment(run_dir, experiment, metadata)

            LOGGER.error("Experiment failed. Raw failed simulation data was preserved.")
            traceback.print_exc()
            raise

    def run_all(
        self,
        dry_run: bool = False,
        *,
        directory: Path | None = None,
    ) -> list[Path]:
        if directory is None:
            directory = self._resolve_setting_path("experiments_root")

        if not directory.is_dir():
            raise NotADirectoryError(
                f"Experiment folder does not exist: {directory}"
            )

        configs = sorted(
            path for path in directory.glob("*.json") if path.is_file()
        )
        if not configs:
            raise FileNotFoundError(
                f"No experiment JSON files found in {directory}"
            )

        batch_dir = self._create_batch_directory(
            datetime.now().astimezone()
        )
        results: list[Path] = []
        continue_on_error = bool(
            self.settings.get("execution", {}).get(
                "continue_on_experiment_error",
                False,
            )
        )
        for path in configs:
            try:
                results.append(self.run_config(
                    path,
                    dry_run=dry_run,
                    batch_dir=batch_dir,
                ))
            except Exception:
                if not continue_on_error:
                    raise

        return results

    def _validate_experiment(
            self,
            experiment: dict[str, Any],
            path: Path,
    ) -> None:
        required = {
            "experiment_name",
            "generator",
            "seed",
            "generator_settings",
            "simulator_settings",
        }
        missing = sorted(required - experiment.keys())
        if missing:
            raise ValueError(f"Experiment {path} is missing fields: {missing}")

        generator = experiment["generator_settings"]
        width = generator.get("map_width")
        height = generator.get("map_height")
        if (width is None) != (height is None):
            raise ValueError("Provide map_width and map_height together")
        if width is not None and (
                type(width) is not int
                or type(height) is not int
                or width <= 0
                or height <= 0
        ):
            raise ValueError("map_width and map_height must be positive integers")

        scale = generator.get("map_scale")
        if (
                isinstance(scale, bool)
                or not isinstance(scale, (int, float))
                or not math.isfinite(scale)
                or scale <= 0
        ):
            raise ValueError(
                "generator_settings.map_scale must be positive and finite"
            )

        repair_enabled = generator.get("repair_enabled", False)
        if type(repair_enabled) is not bool:
            raise ValueError("repair_enabled must be true or false")
        if repair_enabled:
            repair_limit = generator.get("repair_max_changed_cells")
            if type(repair_limit) is not int or repair_limit <= 0:
                raise ValueError(
                    "Enabled repair requires a positive integer "
                    "repair_max_changed_cells"
                )
        completion = generator.get("map_completion")
        if not isinstance(completion, dict):
            raise ValueError("generator_settings.map_completion is required")

        mode = completion.get("mode")
        if mode not in ("generic", "generator"):
            raise ValueError("map_completion.mode must be generic or generator")

        if mode == "generic":
            for name in ("seed", "health_count", "ammo_count"):
                value = completion.get(name)
                if type(value) is not int or value < 0:
                    raise ValueError(
                        f"map_completion.{name} must be a non-negative integer"
                    )

            minimum_spawns = int(
                generator.get("validation", {}).get("minimum_spawn_count", 2)
            )
            if minimum_spawns > 2:
                raise ValueError(
                    "Generic map completion places exactly two spawns"
                )

        metric_specs = generator.get("fitness", {}).get("metrics", [])
        if len(metric_specs) == 0:
            raise ValueError("generator_settings.fitness.metrics requires entries")
        metric_names = [str(value.get("name", "")) for value in metric_specs]
        if any(name == "" for name in metric_names):
            raise ValueError("Every fitness metric requires a name")
        if len(set(metric_names)) != len(metric_names):
            raise ValueError("Fitness metric names must be unique")

        from metrics.metric_calculator import (
            MAP_NUMERIC_METRIC_NAMES,
            available_metric_names,
            normalize_metric_name,
        )

        normalized_fitness_names = [normalize_metric_name(name) for name in metric_names]
        unknown_fitness = sorted(
            set(normalized_fitness_names) - set(available_metric_names())
        )
        if unknown_fitness:
            raise ValueError(
                "Unknown fitness metrics: " + ", ".join(unknown_fitness)
            )
        invalid_fitness_scope = sorted(
            set(normalized_fitness_names) - set(MAP_NUMERIC_METRIC_NAMES)
        )
        if invalid_fitness_scope:
            raise ValueError(
                "Fitness metrics must be scalar values calculated for one map. "
                "Population metrics belong in results_by_epoch.csv: "
                + ", ".join(invalid_fitness_scope)
            )

        simulator = experiment["simulator_settings"]
        if bool(simulator.get("enabled", True)):
            simulator_required = {
                "simulations_per_map",
                "matches_per_simulation",
                "game_length",
                "bot1",
                "bot2",
            }
            missing_simulator = sorted(simulator_required - simulator.keys())
            if missing_simulator:
                raise ValueError(
                    f"Experiment {path} simulator_settings is missing fields: "
                    f"{missing_simulator}"
                )
            if int(simulator["simulations_per_map"]) <= 0:
                raise ValueError("simulations_per_map must be positive")
            if int(simulator["matches_per_simulation"]) != 2:
                raise ValueError(
                    "matches_per_simulation must be 2: "
                    "one match for each initial spawn assignment"
                )
            if int(simulator["game_length"]) <= 0:
                raise ValueError("game_length must be positive")

            for bot_name in ("bot1", "bot2"):
                if {"file", "skill"}.issubset(simulator[bot_name]) is False:
                    raise ValueError(f"{bot_name} requires file and skill")

        analysis = experiment.get("analysis_settings", {})
        if bool(analysis.get("enabled", False)):
            for list_name in ("calculate_metric", "create_diagram_for_metric"):
                value = analysis.get(list_name, [])
                if isinstance(value, list) is False:
                    raise ValueError(f"analysis_settings.{list_name} must be a list")
            requested = [
                normalize_metric_name(value)
                for value in analysis.get("calculate_metric", [])
            ]
            requested.extend(
                normalize_metric_name(value)
                for value in analysis.get("create_diagram_for_metric", [])
            )
            unknown = sorted(set(requested) - set(available_metric_names()))
            if unknown:
                raise ValueError(
                    "Unknown analysis metrics: " + ", ".join(unknown)
                )

    @staticmethod
    def _resolve_seed(value: Any) -> int:
        if value is None or str(value).strip() in {"", "-1"}:
            return secrets.randbelow(2 ** 31 - 1) + 1
        return int(value)

    def _create_batch_directory(self, started_at: datetime) -> Path:
        results_root = self._resolve_setting_path("results_root")
        timestamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
        suffix = 0

        while True:
            name = timestamp if suffix == 0 else f"{timestamp}_{suffix:02d}"
            batch_dir = results_root / name
            try:
                batch_dir.mkdir(parents=True)
            except FileExistsError:
                suffix += 1
            else:
                return batch_dir

    def _create_run_directory(
            self,
            experiment_name: str,
            batch_dir: Path,
    ) -> Path:
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in experiment_name
        ) or "experiment"
        suffix = 0

        while True:
            name = safe_name if suffix == 0 else f"{safe_name}_{suffix:02d}"
            run_dir = batch_dir / name
            try:
                run_dir.mkdir(parents=True)
            except FileExistsError:
                suffix += 1
            else:
                return run_dir

    def _resolve_setting_path(self, key: str) -> Path:
        path = Path(self.settings["paths"][key])
        if path.is_absolute() is False:
            path = (self.framework_root / path).resolve()
        return path

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write_evaluated_experiment(
            run_dir: Path,
            experiment: dict[str, Any],
            metadata: dict[str, Any],
    ) -> None:
        payload = {**experiment, "run_metadata": metadata}
        (run_dir / "experiment_evaluated.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FPS PCG experiments")
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        help=(
            "Experiment JSON file or folder; names also resolve "
            "under experiments_root"
        ),
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Alternative way to specify the experiment JSON file or folder",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Disable Unity and test generation, validation, and result writing",
    )
    args = parser.parse_args()

    if args.target is not None and args.config is not None:
        parser.error("Use either a positional target or --config, not both.")

    manager = ExperimentManager()
    target = args.target if args.target is not None else args.config

    if target is None:
        outputs = manager.run_all(dry_run=args.dry_run)
    else:
        target = target.expanduser()
        if not target.is_absolute():
            local_path = Path.cwd() / target
            if local_path.exists():
                target = local_path
            else:
                target = (
                        manager._resolve_setting_path("experiments_root") / target
                )
        target = target.resolve()

        if target.is_dir():
            outputs = manager.run_all(
                dry_run=args.dry_run,
                directory=target,
            )
        elif target.is_file() and target.suffix.lower() == ".json":
            outputs = [manager.run_config(target, dry_run=args.dry_run)]
        else:
            parser.error(
                f"Expected an existing JSON file or folder: {target}"
            )

    for output in outputs:
        LOGGER.info("Experiment completed: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())