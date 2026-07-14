from __future__ import annotations

import json
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analysis.result_extractor import read_final_results
from map_schema.canonical_map import CanonicalMap


LOGGER = logging.getLogger("thesis_framework")


@dataclass
class UnityRunResult:
    match_records: list[dict[str, Any]]
    exported_files: list[Path]
    command: list[str]
    log_file: Path | None
    config_file: Path
    commands: list[list[str]]
    log_files: list[Path]
    config_files: list[Path]


@dataclass
class _SingleUnityRunResult:
    match_records: list[dict[str, Any]]
    exported_files: list[Path]
    command: list[str]
    log_file: Path | None
    config_file: Path


class UnityRunner:
    """Run independent MapEvaluationTester processes for one map.

    ``simulations_per_map`` controls the total Unity launches for a map.
    ``max_parallel_simulations_per_map`` limits how many launches run at once.
    ``matches_per_simulation`` is forwarded to Unity as ``num_experiments``.
    With the current Unity map-reset issue, the stable value remains one.
    """

    def __init__(self, framework_root: Path, technical_settings: dict[str, Any]):
        self.framework_root = framework_root
        self.settings = technical_settings

    def run(
        self,
        canonical_map: CanonicalMap,
        run_dir: Path,
        experiment: dict[str, Any],
        generation_info: dict[str, Any] | None = None,
    ) -> UnityRunResult:
        unity_settings = self.settings["unity"]
        build_name = str(unity_settings["EXPERIMENT_RUNNER_FILE"])
        runner_directory = Path(
            str(unity_settings["EXPERIMENT_RUNNER_PATH"])
        ).expanduser().resolve()
        executable_path = runner_directory / build_name

        if executable_path.is_file() is False:
            raise FileNotFoundError(
                f"Unity build is missing: {executable_path}. Update configs/settings.json."
            )
        if runner_directory.is_dir() is False:
            raise FileNotFoundError(
                f"Unity build directory is missing: {runner_directory}."
            )

        simulation_count = int(experiment.get("simulations_per_map", 1))
        matches_per_simulation = int(experiment.get("matches_per_simulation", 1))
        if simulation_count <= 0:
            raise ValueError("simulations_per_map must be positive")
        if matches_per_simulation <= 0:
            raise ValueError("matches_per_simulation must be positive")

        if matches_per_simulation > 1:
            LOGGER.warning(
                "matches_per_simulation=%s uses Unity's internal map-reset path. "
                "Keep this at 1 until OptimizedMeshMapAssembler.ClearMap is fixed.",
                matches_per_simulation,
            )

        execution_settings = self.settings.get("execution", {})
        configured_workers = int(
            execution_settings.get("max_parallel_simulations_per_map", 1)
        )
        max_workers = max(1, min(configured_workers, simulation_count))
        progress_info = generation_info or {}

        def run_simulation(simulation_index: int) -> _SingleUnityRunResult:
            return self._run_single_simulation(
                canonical_map=canonical_map,
                run_dir=run_dir,
                experiment=experiment,
                generation_info=progress_info,
                simulation_index=simulation_index,
                simulation_count=simulation_count,
                matches_per_simulation=matches_per_simulation,
                executable_path=executable_path,
                runner_directory=runner_directory,
                unity_settings=unity_settings,
            )

        if max_workers == 1:
            single_results = [
                run_simulation(index)
                for index in range(simulation_count)
            ]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                single_results = list(
                    executor.map(run_simulation, range(simulation_count))
                )

        match_records: list[dict[str, Any]] = []
        exported_files: list[Path] = []
        commands: list[list[str]] = []
        log_files: list[Path] = []
        config_files: list[Path] = []

        for result in single_results:
            match_records.extend(result.match_records)
            exported_files.extend(result.exported_files)
            commands.append(result.command)
            config_files.append(result.config_file)
            if result.log_file is not None:
                log_files.append(result.log_file)

        first_result = single_results[0]
        return UnityRunResult(
            match_records=match_records,
            exported_files=exported_files,
            command=first_result.command,
            log_file=first_result.log_file,
            config_file=first_result.config_file,
            commands=commands,
            log_files=log_files,
            config_files=config_files,
        )

    def _run_single_simulation(
        self,
        canonical_map: CanonicalMap,
        run_dir: Path,
        experiment: dict[str, Any],
        generation_info: dict[str, Any],
        simulation_index: int,
        simulation_count: int,
        matches_per_simulation: int,
        executable_path: Path,
        runner_directory: Path,
        unity_settings: dict[str, Any],
    ) -> _SingleUnityRunResult:
        simulation_name = f"{canonical_map.map_id}_s{simulation_index:04d}"
        runtime_root = (
            run_dir
            / "_raw"
            / "unity_runtime"
            / canonical_map.map_id
            / f"simulation_{simulation_index:04d}"
        )
        bot_dir = runtime_root / "Bots"
        export_dir = runtime_root / "Export"
        bot_dir.mkdir(parents=True, exist_ok=True)
        export_dir.mkdir(parents=True, exist_ok=True)

        self._copy_bots(bot_dir)

        simulation = experiment.get("simulation", {})
        map_payload = canonical_map.to_dict()
        map_payload["map_scale"] = float(unity_settings.get("map_scale", 2))
        map_payload["symbols"] = {
            "wall": "#",
            "floor": ".",
            "spawn": "S",
            "cover": "C",
            "health": "H",
            "ammo": "A",
        }

        config_payload = {
            "schema_version": "1.0",
            "experiment_name": simulation_name,
            "num_experiments": matches_per_simulation,
            "game_length": int(experiment["game_length"]),
            "ready_duration": int(simulation.get("ready_duration", 1)),
            "score_duration": int(simulation.get("score_duration", 0)),
            "respawn_duration": float(simulation.get("respawn_duration", 3.0)),
            "paths": {
                "bots_directory": "Bots",
                "output_directory": "Export",
                "output_subdirectory": "",
            },
            "logging": {
                "save_map": bool(simulation.get("save_unity_map", True)),
                "log_positions": bool(simulation.get("log_positions", True)),
                "log_kill_distances": bool(
                    simulation.get("log_kill_distances", False)
                ),
                "log_death_positions": bool(
                    simulation.get("log_death_positions", True)
                ),
            },
            "map": map_payload,
            "bot1": {
                "id": 1,
                "file": str(experiment["bot1"]["file"]),
                "skill": float(experiment["bot1"]["skill"]),
            },
            "bot2": {
                "id": 2,
                "file": str(experiment["bot2"]["file"]),
                "skill": float(experiment["bot2"]["skill"]),
            },
        }
        config_file = runtime_root / "map_test_config.json"
        config_file.write_text(
            json.dumps(config_payload, indent=2),
            encoding="utf-8",
        )

        command = [
            str(executable_path.resolve()),
            "-experimentType=BOT_MAP_TESTER",
            f"-mapTestConfig={config_file.resolve()}",
        ]

        if bool(unity_settings.get("headless", True)):
            command.extend(["-batchmode", "-nographics"])

        log_file: Path | None = None
        if bool(unity_settings.get("capture_log", True)):
            log_file = (
                run_dir
                / "_raw"
                / "unity_logs"
                / canonical_map.map_id
                / f"simulation_{simulation_index:04d}.log"
            )
            log_file.parent.mkdir(parents=True, exist_ok=True)
            command.extend(["-logFile", str(log_file.resolve())])
        else:
            command.append("-nolog")

        map_number = int(generation_info.get("simulation_batch_map_index", 0)) + 1
        map_count = int(generation_info.get("simulation_batch_map_count", 1))
        for match_index in range(matches_per_simulation):
            LOGGER.info(
                "    Start simulating Map %s/%s, Simulation %s/%s, Match %s/%s: %s",
                map_number,
                map_count,
                simulation_index + 1,
                simulation_count,
                match_index + 1,
                matches_per_simulation,
                canonical_map.map_id,
            )

        completed = subprocess.run(
            command,
            cwd=runner_directory,
            check=False,
            timeout=int(unity_settings.get("timeout_seconds", 3600)),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Unity simulation {simulation_index + 1} for "
                f"{canonical_map.map_id} returned code {completed.returncode}. "
                f"See {log_file if log_file else 'terminal output'}."
            )

        final_results = export_dir / f"final_results_{simulation_name}.json"
        if final_results.is_file() is False:
            raise FileNotFoundError(
                f"Unity completed but result file is missing: {final_results}"
            )

        match_records = read_final_results(final_results)
        for match_index, record in enumerate(match_records):
            record["simulation_index"] = simulation_index
            record["match_index"] = match_index
            record["unity_experiment_name"] = simulation_name

        destination = (
            run_dir
            / "_unity_exports"
            / canonical_map.map_id
            / f"simulation_{simulation_index:04d}"
        )
        destination.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for source in sorted(export_dir.glob("*")):
            if source.is_file() is False:
                continue
            target = destination / source.name
            shutil.copy2(source, target)
            copied.append(target)

        LOGGER.info(
            "    Finished Map %s/%s, Simulation %s/%s: %s",
            map_number,
            map_count,
            simulation_index + 1,
            simulation_count,
            canonical_map.map_id,
        )

        return _SingleUnityRunResult(
            match_records=match_records,
            exported_files=copied,
            command=command,
            log_file=log_file,
            config_file=config_file,
        )

    def _copy_bots(self, destination: Path) -> None:
        configured = Path(self.settings["paths"]["bots_root"])
        if configured.is_absolute() is False:
            configured = (self.framework_root / configured).resolve()
        if configured.is_dir() is False:
            raise FileNotFoundError(
                f"Bot configuration folder is missing: {configured}"
            )
        for source in configured.glob("*.json"):
            shutil.copy2(source, destination / source.name)
