from __future__ import annotations

import json
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from time import monotonic
from map_schema.canonical_map import CanonicalMap


LOGGER = logging.getLogger("FPS-EVALUATOR")


def _read_final_results(
        path: Path,
        expected_count: int,
) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        data = [data]

    if (
            not isinstance(data, list)
            or not data
            or len(data) != expected_count
    ):
        raise ValueError(
            f"Expected {expected_count} Unity match results in {path}"
        )

    for match_index, record in enumerate(data):
        if not isinstance(record, dict):
            raise ValueError(
                f"Invalid Unity result for match {match_index} in {path}"
            )

        for key in ("numberOfFrags1", "numberOfFrags2"):
            value = record.get(key)
            if type(value) is not int or value < 0:
                raise ValueError(
                    f"Missing or invalid {key} for match "
                    f"{match_index} in {path}"
                )

    return data

@dataclass
class UnityRunResult:
    match_records: list[dict[str, Any]]
    simulation_count_requested: int
    simulation_count_successful: int
    simulation_count_failed: int
    failures: list[dict[str, Any]]
    simulation_count_skipped: int = 0


@dataclass
class _SingleUnityRunResult:
    successful: bool
    match_records: list[dict[str, Any]]
    simulation_index: int
    runtime_dir: Path
    error: str | None = None
    skipped: bool = False


class UnityRunner:
    """Run Unity simulations and keep runtime folders until final cleanup."""

    def __init__(self, framework_root: Path, technical_settings: dict[str, Any]):
        self.framework_root = framework_root
        self.settings = technical_settings

    def run(
        self,
        canonical_map: CanonicalMap,
        run_dir: Path,
        epoch_dir: Path,
        simulator_settings: dict[str, Any],
        epoch: int,
        numeric_id: int,
        production_deadline: float | None = None,
    ) -> UnityRunResult:
        simulation_count = int(
            simulator_settings.get("simulations_per_map", 1)
        )

        if (
            production_deadline is not None
            and monotonic() >= production_deadline
        ):
            return UnityRunResult(
                match_records=[],
                simulation_count_requested=simulation_count,
                simulation_count_successful=0,
                simulation_count_failed=0,
                failures=[],
                simulation_count_skipped=simulation_count,
            )

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
                epoch_dir=epoch_dir,
                simulator_settings=simulator_settings,
                epoch=epoch,
                numeric_id=numeric_id,
                simulation_index=simulation_index,
                simulation_count=simulation_count,
                matches_per_simulation=matches_per_simulation,
                executable_path=executable_path,
                runner_directory=runner_directory,
                unity_settings=unity_settings,
                production_deadline=production_deadline,
            )

        if max_workers == 1:
            single_results = [
                run_one(index)
                for index in range(simulation_count)
            ]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                single_results = list(
                    executor.map(run_one, range(simulation_count))
                )

        matches = []
        failures = []
        successful = 0
        skipped = 0

        for result in single_results:
            if result.skipped:
                skipped += 1
            elif result.successful:
                successful += 1
                matches.extend(result.match_records)
            else:
                failures.append({
                    "simulation_index": result.simulation_index,
                    "error": result.error,
                    "runtime_directory": str(result.runtime_dir.resolve()),
                })

        if skipped:
            LOGGER.info(
                "Map %s: production deadline skipped %s of %s simulations.",
                canonical_map.map_id,
                skipped,
                simulation_count,
            )

        return UnityRunResult(
            match_records=matches,
            simulation_count_requested=simulation_count,
            simulation_count_successful=successful,
            simulation_count_failed=len(failures),
            failures=failures,
            simulation_count_skipped=skipped,
        )

    def _run_single_simulation(
        self,
        canonical_map: CanonicalMap,
        run_dir: Path,
        epoch_dir: Path,
        simulator_settings: dict[str, Any],
        epoch: int,
        numeric_id: int,
        simulation_index: int,
        simulation_count: int,
        matches_per_simulation: int,
        executable_path: Path,
        runner_directory: Path,
        unity_settings: dict[str, Any],
        production_deadline: float | None = None,
    ) -> _SingleUnityRunResult:
        simulation_name = f"{canonical_map.map_id}_s{simulation_index:04d}"
        runtime_root = (
            run_dir
            / "_raw"
            / f"epoch_{epoch:04d}"
            / canonical_map.map_id
            / f"simulation_{simulation_index:04d}"
        )
        if (
                production_deadline is not None
                and monotonic() >= production_deadline
        ):
            return _SingleUnityRunResult(
                successful=False,
                match_records=[],
                simulation_index=simulation_index,
                runtime_dir=runtime_root,
                skipped=True,
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
            serialized_config = json.dumps(config_payload, indent=2)
            config_file.write_text(serialized_config, encoding="utf-8")

            # Keep one exact Unity input JSON per map in the epoch folder.
            # Additional simulation configs remain available below _raw when
            # only_keep_result_summary is false.
            if simulation_index == 0:
                unity_input_path = (
                    epoch_dir / f"{canonical_map.map_id}.unity.json"
                )
                unity_input_path.write_text(
                    serialized_config,
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
            if (
                    production_deadline is not None
                    and monotonic() >= production_deadline
            ):
                return _SingleUnityRunResult(
                    successful=False,
                    match_records=[],
                    simulation_index=simulation_index,
                    runtime_dir=runtime_root,
                    skipped=True,
                )
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

            match_records = _read_final_results(
                final_results,
                matches_per_simulation,
            )
            for match_index, record in enumerate(match_records):
                record["simulation_index"] = simulation_index
                record["match_index"] = match_index

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
