from __future__ import annotations

import json
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from map_schema.canonical_map import CanonicalMap


LOGGER = logging.getLogger("FPS-EVALUATOR")


def _read_final_results(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(item) for item in data]
    if isinstance(data, dict):
        return [dict(data)]
    raise ValueError(f"Unsupported Unity result format in {path}")


@dataclass
class UnityRunResult:
    match_records: list[dict[str, Any]]
    simulation_count_requested: int
    simulation_count_successful: int
    simulation_count_failed: int
    failures: list[dict[str, Any]]


@dataclass
class _SingleUnityRunResult:
    successful: bool
    match_records: list[dict[str, Any]]
    simulation_index: int
    runtime_dir: Path
    error: str | None = None


class UnityRunner:
    """Run Unity simulations and retain only failed runtime folders."""

    def __init__(self, framework_root: Path, technical_settings: dict[str, Any]):
        self.framework_root = framework_root
        self.settings = technical_settings

    def run(
        self,
        canonical_map: CanonicalMap,
        run_dir: Path,
        simulator_settings: dict[str, Any],
        epoch: int,
        numeric_id: int,
    ) -> UnityRunResult:
        unity_settings = self.settings["unity"]
        runner_directory = Path(
            str(unity_settings["EXPERIMENT_RUNNER_PATH"])
        ).expanduser().resolve()
        executable_path = runner_directory / str(
            unity_settings["EXPERIMENT_RUNNER_FILE"]
        )
        if executable_path.is_file() is False:
            raise FileNotFoundError(
                f"Unity build is missing: {executable_path}. Update configs/settings.json."
            )

        simulation_count = int(simulator_settings.get("simulations_per_map", 1))
        matches_per_simulation = int(
            simulator_settings.get("matches_per_simulation", 1)
        )
        execution = self.settings.get("execution", {})
        configured_workers = int(
            execution.get("max_parallel_simulations_per_map", 1)
        )
        max_workers = max(1, min(configured_workers, simulation_count))

        def run_one(simulation_index: int) -> _SingleUnityRunResult:
            return self._run_single_simulation(
                canonical_map=canonical_map,
                run_dir=run_dir,
                simulator_settings=simulator_settings,
                epoch=epoch,
                numeric_id=numeric_id,
                simulation_index=simulation_index,
                simulation_count=simulation_count,
                matches_per_simulation=matches_per_simulation,
                executable_path=executable_path,
                runner_directory=runner_directory,
                unity_settings=unity_settings,
            )

        if max_workers == 1:
            single_results = [run_one(index) for index in range(simulation_count)]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                single_results = list(executor.map(run_one, range(simulation_count)))

        matches: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for result in single_results:
            if result.successful:
                matches.extend(result.match_records)
            else:
                failures.append(
                    {
                        "simulation_index": result.simulation_index,
                        "error": result.error,
                        "runtime_directory": str(result.runtime_dir.resolve()),
                    }
                )

        return UnityRunResult(
            match_records=matches,
            simulation_count_requested=simulation_count,
            simulation_count_successful=simulation_count - len(failures),
            simulation_count_failed=len(failures),
            failures=failures,
        )

    def _run_single_simulation(
        self,
        canonical_map: CanonicalMap,
        run_dir: Path,
        simulator_settings: dict[str, Any],
        epoch: int,
        numeric_id: int,
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
            / f"epoch_{epoch:04d}"
            / canonical_map.map_id
            / f"simulation_{simulation_index:04d}"
        )
        bot_dir = runtime_root / "Bots"
        export_dir = runtime_root / "Export"
        bot_dir.mkdir(parents=True, exist_ok=True)
        export_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._copy_bots(bot_dir)
            map_payload = canonical_map.to_dict()
            map_payload["map_scale"] = float(
                canonical_map.metadata.get(
                    "map_scale",
                    unity_settings.get("map_scale", 2),
                )
            )
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
                "game_length": int(simulator_settings["game_length"]),
                "ready_duration": int(
                    simulator_settings.get("ready_duration", 1)
                ),
                "score_duration": int(
                    simulator_settings.get("score_duration", 0)
                ),
                "respawn_duration": float(
                    simulator_settings.get("respawn_duration", 3.0)
                ),
                "paths": {
                    "bots_directory": "Bots",
                    "output_directory": "Export",
                    "output_subdirectory": "",
                },
                "logging": {
                    "save_map": bool(
                        simulator_settings.get("save_unity_map", True)
                    ),
                    "log_positions": bool(
                        simulator_settings.get("log_positions", True)
                    ),
                    "log_kill_distances": bool(
                        simulator_settings.get("log_kill_distances", False)
                    ),
                    "log_death_positions": bool(
                        simulator_settings.get("log_death_positions", True)
                    ),
                },
                "map": map_payload,
                "bot1": {
                    "id": 1,
                    "file": str(simulator_settings["bot1"]["file"]),
                    "skill": float(simulator_settings["bot1"]["skill"]),
                },
                "bot2": {
                    "id": 2,
                    "file": str(simulator_settings["bot2"]["file"]),
                    "skill": float(simulator_settings["bot2"]["skill"]),
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

            if bool(unity_settings.get("capture_log", True)):
                command.extend(
                    ["-logFile", str((runtime_root / "unity.log").resolve())]
                )
            else:
                command.append("-nolog")

            LOGGER.info(
                "    Map %s, simulation %s/%s: %s",
                numeric_id,
                simulation_index + 1,
                simulation_count,
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
                    f"Unity returned code {completed.returncode}"
                )

            final_results = export_dir / f"final_results_{simulation_name}.json"
            if final_results.is_file() is False:
                raise FileNotFoundError(
                    f"Unity result file is missing: {final_results}"
                )

            match_records = _read_final_results(final_results)
            for match_index, record in enumerate(match_records):
                record["simulation_index"] = simulation_index
                record["match_index"] = match_index

            shutil.rmtree(runtime_root)
            self._prune_empty_parents(runtime_root.parent, run_dir / "_raw")
            return _SingleUnityRunResult(
                successful=True,
                match_records=match_records,
                simulation_index=simulation_index,
                runtime_dir=runtime_root,
            )
        except Exception as exc:
            LOGGER.error(
                "    Simulation failed for %s. Files kept in %s: %s",
                canonical_map.map_id,
                runtime_root,
                exc,
            )
            return _SingleUnityRunResult(
                successful=False,
                match_records=[],
                simulation_index=simulation_index,
                runtime_dir=runtime_root,
                error=str(exc),
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

    @staticmethod
    def _prune_empty_parents(path: Path, stop: Path) -> None:
        current = path
        while current != stop and current.is_dir():
            if next(current.iterdir(), None) is not None:
                break
            current.rmdir()
            current = current.parent
