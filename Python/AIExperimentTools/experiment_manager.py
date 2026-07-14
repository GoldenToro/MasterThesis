from __future__ import annotations

import argparse
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

from analysis.generate_report import generate_report
from analysis.score_calculator import calculate_score
from generators.base_generator import GeneratorContext
from generators.registry import available_generators, load_generator
from map_schema.map_exporter import save_canonical_map, save_grid_text
from map_schema.map_repairer import MapRepairer
from map_schema.map_validator import MapValidator
from metrics.simulation_metrics import aggregate_match_records
from metrics.static_metrics import calculate_static_metrics
from simulation.unity_runner import UnityRunner


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
        """Configure one thread-safe console logger for the whole framework."""
        if logging.getLogger().handlers:
            return
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    def run_config(self, config_path: Path, dry_run: bool = False) -> Path:
        source_experiment = self._load_json(config_path)
        seed_value = source_experiment.get("seed")
        if seed_value is None or str(seed_value).strip() in {"", "-1"}:
            source_experiment["seed"] = secrets.randbelow(2**31 - 1) + 1

        self._validate_experiment(source_experiment, config_path)

        generator, generator_settings = load_generator(
            source_experiment["generator"],
            self.framework_root,
            source_experiment.get("generator_settings", {}),
        )
        resolved_experiment = dict(source_experiment)
        resolved_experiment["generator_settings"] = generator_settings
        if dry_run:
            resolved_experiment.setdefault("simulation", {})["enabled"] = False

        started_at = datetime.now().astimezone()
        run_dir = self._create_run_directory(resolved_experiment["experiment_name"], started_at)
        self._create_output_folders(run_dir)
        shutil.copy2(config_path, run_dir / "experiment.json")

        metadata = {
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "status": "running",
            "framework_version": self.settings.get("framework_version", "unknown"),
            "source_config": str(config_path.resolve()),
        }
        self._write_resolved(run_dir, resolved_experiment, metadata)

        LOGGER.info(
            "Start experiment '%s' with generator '%s'.",
            resolved_experiment["experiment_name"],
            resolved_experiment["generator"],
        )

        records: list[dict[str, Any]] = []

        records_path = run_dir / "_metrics" / "map_evaluations.jsonl"

        try:
            context = GeneratorContext(
                experiment_name=str(resolved_experiment["experiment_name"]),
                map_width=int(resolved_experiment["map_width"]),
                map_height=int(resolved_experiment["map_height"]),
                num_epochs=int(resolved_experiment.get("num_epochs", 1)),
                population_size=int(resolved_experiment.get("population_size", 4)),
                seed=int(resolved_experiment["seed"]),
                output_dir=run_dir,
                framework_root=self.framework_root,
                technical_settings=self.settings,
                experiment=resolved_experiment,
            )

            def evaluate_map(canonical_map, generation_info):
                record = self._evaluate_map(
                    canonical_map,
                    generation_info,
                    resolved_experiment,
                    run_dir,
                )
                records.append(record)
                with records_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\n")
                return record

            final_records = generator.run(context, evaluate_map)
            report_records = records if records else final_records
            summary = generate_report(
                run_dir,
                report_records,
                self.settings.get("reporting", {}),
            )
            metadata.update(
                {
                    "finished_at": datetime.now().astimezone().isoformat(),
                    "status": "completed",
                    "summary": summary,
                    "final_candidate_map_ids": [record["map_id"] for record in final_records],
                }
            )
            self._write_resolved(run_dir, resolved_experiment, metadata)
            LOGGER.info(
                "Finished experiment '%s'.",
                resolved_experiment["experiment_name"],
            )
            return run_dir
        except Exception as exc:
            metadata.update(
                {
                    "finished_at": datetime.now().astimezone().isoformat(),
                    "status": "failed",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            self._write_resolved(run_dir, resolved_experiment, metadata)
            raise

    def run_all(self, dry_run: bool = False) -> list[Path]:
        experiments_root = self._resolve_setting_path("experiments_root")
        configs = sorted(experiments_root.glob("*.json"))
        if len(configs) == 0:
            raise FileNotFoundError(f"No experiment JSON files found in {experiments_root}")

        LOGGER.info("Found %s experiments:", len(configs))
        for path in configs:
            LOGGER.info("- %s", path.name)

        results: list[Path] = []
        continue_on_error = bool(
            self.settings.get("execution", {}).get("continue_on_experiment_error", False)
        )
        for path in configs:
            try:
                results.append(self.run_config(path, dry_run=dry_run))
            except Exception:
                if continue_on_error is False:
                    raise
                traceback.print_exc()
        return results

    def _evaluate_map(
        self,
        canonical_map,
        generation_info: dict[str, Any],
        experiment: dict[str, Any],
        run_dir: Path,
    ) -> dict[str, Any]:
        validator = MapValidator(experiment.get("validation", {}))
        initial_validation = validator.validate(canonical_map)
        repair_report = {"changed": False, "actions": []}

        if initial_validation.valid is False and bool(experiment.get("repair", {}).get("enabled", False)):
            canonical_map, repair = MapRepairer().repair(
                canonical_map,
                minimum_spawn_count=int(experiment.get("validation", {}).get("minimum_spawn_count", 2)),
            )
            repair_report = repair.to_dict()

        validation = validator.validate(canonical_map)
        if not validation.valid:
            LOGGER.warning(
                "Skip simulation for map '%s': map is invalid after repair. Reasons: %s",
                canonical_map.map_id,
                "; ".join(validation.errors) or "unspecified",
            )
        map_json = save_canonical_map(canonical_map, run_dir / "_maps" / f"{canonical_map.map_id}.json")
        grid_text = save_grid_text(canonical_map, run_dir / "_maps" / f"{canonical_map.map_id}.txt")
        static_metrics = calculate_static_metrics(canonical_map)

        simulation_metrics: dict[str, Any] = {}
        simulation_info: dict[str, Any] = {"status": "skipped", "match_records": []}
        simulation_enabled = bool(experiment.get("simulation", {}).get("enabled", True))
        if simulation_enabled and validation.valid:
            unity_result = UnityRunner(self.framework_root, self.settings).run(
                canonical_map,
                run_dir,
                experiment,
                generation_info=generation_info,
            )
            simulation_metrics = aggregate_match_records(unity_result.match_records)
            simulation_info = {
                "status": "completed",
                "match_records": unity_result.match_records,
                "command": unity_result.command,
                "commands": unity_result.commands,
                "config_file": str(unity_result.config_file),
                "config_files": [str(path) for path in unity_result.config_files],
                "log_file": str(unity_result.log_file) if unity_result.log_file else None,
                "log_files": [str(path) for path in unity_result.log_files],
                "exported_files": [str(path) for path in unity_result.exported_files],
            }
        elif simulation_enabled and validation.valid is False:
            simulation_info["status"] = "skipped_invalid_map"

        fitness = calculate_score(
            static_metrics,
            simulation_metrics,
            experiment.get("fitness", {}),
            valid=validation.valid,
        )
        return {
            "map_id": canonical_map.map_id,
            "generator": experiment["generator"],
            "generation_info": generation_info,
            "validation_before_repair": initial_validation.to_dict(),
            "repair": repair_report,
            "validation": validation.to_dict(),
            "static_metrics": static_metrics,
            "simulation_metrics": simulation_metrics,
            "simulation": simulation_info,
            "fitness": fitness,
            "artifacts": {
                "canonical_map_json": str(map_json.resolve()),
                "canonical_grid_text": str(grid_text.resolve()),
            },
        }

    def _validate_experiment(self, experiment: dict[str, Any], path: Path) -> None:
        required = {
            "experiment_name",
            "generator",
            "simulations_per_map",
            "game_length",
            "map_width",
            "map_height",
            "seed",
            "bot1",
            "bot2",
        }
        missing = sorted(required - experiment.keys())
        if missing:
            raise ValueError(f"Experiment {path} is missing fields: {missing}")
        if experiment["generator"] not in available_generators():
            raise ValueError(
                f"Unsupported generator '{experiment['generator']}'. "
                f"Available: {', '.join(available_generators())}"
            )
        for bot_name in ("bot1", "bot2"):
            if {"file", "skill"}.issubset(experiment[bot_name]) is False:
                raise ValueError(f"{bot_name} requires file and skill")
        if int(experiment["population_size"]) <= 0:
            raise ValueError("population_size must be positive")
        if int(experiment["simulations_per_map"]) <= 0:
            raise ValueError("simulations_per_map must be positive")
        if int(experiment.get("matches_per_simulation", 1)) <= 0:
            raise ValueError("matches_per_simulation must be positive")
        if int(experiment["map_width"]) <= 0 or int(experiment["map_height"]) <= 0:
            raise ValueError("map dimensions must be positive")

    def _create_run_directory(self, experiment_name: str, started_at: datetime) -> Path:
        safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in experiment_name)
        timestamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
        results_root = self._resolve_setting_path("results_root")
        run_dir = results_root / safe_name / timestamp
        suffix = 1
        while run_dir.exists():
            run_dir = results_root / safe_name / f"{timestamp}_{suffix:02d}"
            suffix += 1
        run_dir.mkdir(parents=True)
        return run_dir

    @staticmethod
    def _create_output_folders(run_dir: Path) -> None:
        for name in ("_raw", "_maps", "_unity_exports", "_metrics", "_figures"):
            (run_dir / name).mkdir(parents=True, exist_ok=True)

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
    def _write_resolved(
        run_dir: Path,
        experiment: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        payload = {**experiment, "run_metadata": metadata}
        (run_dir / "resolved_experiment.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FPS PCG experiments")
    parser.add_argument("--config", type=Path, help="Run specific experiment JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Disable Unity simulation and run generation/static evaluation only",
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
        outputs = manager.run_all(dry_run=args.dry_run)
        for output in outputs:
            LOGGER.info("Experiment completed: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
