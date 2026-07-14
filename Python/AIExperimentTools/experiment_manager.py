from __future__ import annotations

import argparse
import copy
import json
import logging
import secrets
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from generators.base_generator import BaseGenerator


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

    def run_config(self, config_path: Path, dry_run: bool = False) -> Path:
        source_experiment = self._load_json(config_path)
        experiment = copy.deepcopy(source_experiment)
        experiment["seed"] = self._resolve_seed(experiment.get("seed"))
        if dry_run:
            experiment.setdefault("simulator_settings", {})["enabled"] = False

        self._validate_experiment(experiment, config_path)
        started_at = datetime.now().astimezone()
        run_dir = self._create_run_directory(
            str(experiment["experiment_name"]),
            started_at,
        )
        (run_dir / "_raw").mkdir(parents=True, exist_ok=True)

        # Keep the submitted experiment file unchanged. The resolved seed and run
        # information are stored separately in experiment_evaluated.json.
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

        base_generator = BaseGenerator(
            framework_root=self.framework_root,
            output_dir=run_dir,
            technical_settings=self.settings,
            experiment=experiment,
        )
        try:
            final_map_ids = base_generator.start()
            base_generator.mark_final_candidates(final_map_ids)
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

    def run_all(self, dry_run: bool = False) -> list[Path]:
        experiments_root = self._resolve_setting_path("experiments_root")
        configs = sorted(experiments_root.glob("*.json"))
        if len(configs) == 0:
            raise FileNotFoundError(
                f"No experiment JSON files found in {experiments_root}"
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
                results.append(self.run_config(path, dry_run=dry_run))
            except Exception:
                if continue_on_error is False:
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
        generator_required = {
            "num_epochs",
            "population_size",
            "map_width",
            "map_height",
            "fitness",
        }
        missing_generator = sorted(generator_required - generator.keys())
        if missing_generator:
            raise ValueError(
                f"Experiment {path} generator_settings is missing fields: "
                f"{missing_generator}"
            )
        if int(generator["population_size"]) <= 0:
            raise ValueError("population_size must be positive")
        if int(generator["num_epochs"]) < 0:
            raise ValueError("num_epochs must be zero or positive")
        if int(generator["map_width"]) <= 0 or int(generator["map_height"]) <= 0:
            raise ValueError("map dimensions must be positive")

        metric_specs = generator.get("fitness", {}).get("metrics", [])
        if len(metric_specs) == 0:
            raise ValueError("generator_settings.fitness.metrics requires entries")
        metric_names = [str(value.get("name", "")) for value in metric_specs]
        if any(name == "" for name in metric_names):
            raise ValueError("Every fitness metric requires a name")
        if len(set(metric_names)) != len(metric_names):
            raise ValueError("Fitness metric names must be unique")

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
            if int(simulator["matches_per_simulation"]) <= 0:
                raise ValueError("matches_per_simulation must be positive")
            if int(simulator["game_length"]) <= 0:
                raise ValueError("game_length must be positive")
            for bot_name in ("bot1", "bot2"):
                if {"file", "skill"}.issubset(simulator[bot_name]) is False:
                    raise ValueError(f"{bot_name} requires file and skill")

    @staticmethod
    def _resolve_seed(value: Any) -> int:
        if value is None or str(value).strip() in {"", "-1"}:
            return secrets.randbelow(2**31 - 1) + 1
        return int(value)

    def _create_run_directory(
        self,
        experiment_name: str,
        started_at: datetime,
    ) -> Path:
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in experiment_name
        )
        timestamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
        results_root = self._resolve_setting_path("results_root")
        run_dir = results_root / safe_name / timestamp
        suffix = 1
        while run_dir.exists():
            run_dir = results_root / safe_name / f"{timestamp}_{suffix:02d}"
            suffix += 1
        run_dir.mkdir(parents=True)
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
    parser.add_argument("--config", type=Path, help="Run one experiment JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Disable Unity and test generation, validation, and result writing",
    )
    args = parser.parse_args()

    manager = ExperimentManager()
    if args.config:
        config_path = args.config
        if config_path.is_absolute() is False:
            config_path = (Path.cwd() / config_path).resolve()
        output = manager.run_config(config_path, dry_run=args.dry_run)
        LOGGER.info("Experiment completed: %s", output)
    else:
        for output in manager.run_all(dry_run=args.dry_run):
            LOGGER.info("Experiment completed: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())