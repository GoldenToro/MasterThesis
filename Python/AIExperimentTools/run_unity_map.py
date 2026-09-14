from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# -----------------------------------------------------------------------------
# Manual Unity-run settings
# -----------------------------------------------------------------------------
# Adjust these values for your local Project Arena build.
UNITY_RUNNER_DIRECTORY = Path(r"E:\Thesis-Projekt\ProjectArena-thesis\Builds")
UNITY_RUNNER_FILE = "Project Arena.exe"

# Bot JSON files used by map-test configurations that reference prefixes such as
# "assault", "shotgun", or "sniper".
BOTS_DIRECTORY = Path(__file__).resolve().parent / "configs" / "Bots"

# A separate folder is created for each manual run. The original Unity JSON is
# never modified.
OUTPUT_ROOT = Path(__file__).resolve().parent / "results_manual_runs"

TIMEOUT_SECONDS = 3600
CAPTURE_UNITY_LOG = True

# The requested default: keep Unity batch mode, but initialize graphics by
# omitting -nographics. Set USE_BATCHMODE to False to show the normal player
# window as well.
USE_BATCHMODE = False
USE_NOGRAPHICS = False


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if isinstance(payload, dict) is False:
        raise ValueError(f"Unity map configuration must be a JSON object: {path}")
    return payload


def _safe_name(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in value
    ).strip("_")
    return safe or "unity_map"


def _prepare_runtime_config(
    source_config: Path,
    run_directory: Path,
) -> Path:
    payload = copy.deepcopy(_load_json(source_config))

    if isinstance(payload.get("map"), dict) is False:
        raise ValueError(
            "The supplied file is not a Unity map-test configuration: "
            "the top-level 'map' object is missing."
        )

    export_directory = run_directory / "Export"
    export_directory.mkdir(parents=True, exist_ok=True)

    paths = payload.setdefault("paths", {})
    if isinstance(paths, dict) is False:
        raise ValueError("The Unity configuration field 'paths' must be an object.")

    # Use absolute paths so exported candidate .unity.json files can be launched
    # directly even though they have no adjacent Bots or Export directories.
    paths["bots_directory"] = str(BOTS_DIRECTORY.resolve())
    paths["output_directory"] = str(export_directory.resolve())
    paths["output_subdirectory"] = ""

    runtime_config = run_directory / "map_test_config.json"
    runtime_config.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return runtime_config


def run_unity_map(source_config: Path) -> Path:
    source_config = source_config.expanduser().resolve()
    if source_config.is_file() is False:
        raise FileNotFoundError(f"Unity map configuration is missing: {source_config}")

    executable = (UNITY_RUNNER_DIRECTORY / UNITY_RUNNER_FILE).expanduser().resolve()
    if executable.is_file() is False:
        raise FileNotFoundError(
            f"Unity build is missing: {executable}. "
            "Update UNITY_RUNNER_DIRECTORY and UNITY_RUNNER_FILE in "
            "run_unity_map.py."
        )

    if BOTS_DIRECTORY.is_dir() is False:
        raise FileNotFoundError(
            f"Bot configuration directory is missing: {BOTS_DIRECTORY}"
        )

    source_payload = _load_json(source_config)
    experiment_name = str(
        source_payload.get("experiment_name")
        or source_payload.get("map", {}).get("map_id")
        or source_config.stem
    )
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    run_directory = OUTPUT_ROOT / f"{timestamp}_{_safe_name(experiment_name)}"
    run_directory.mkdir(parents=True, exist_ok=False)

    runtime_config = _prepare_runtime_config(source_config, run_directory)
    command = [
        str(executable),
        "-experimentType=BOT_MAP_TESTER",
        f"-mapTestConfig={runtime_config.resolve()}",
    ]

    if USE_BATCHMODE:
        command.append("-batchmode")
    if USE_NOGRAPHICS:
        command.append("-nographics")

    if CAPTURE_UNITY_LOG:
        command.extend(
            ["-logFile", str((run_directory / "unity.log").resolve())]
        )
    else:
        command.append("-nolog")

    print(f"Run Unity map configuration: {source_config}")
    print(f"Runtime directory: {run_directory.resolve()}")
    print("Command:")
    print("  " + " ".join(f'\"{part}\"' if " " in part else part for part in command))

    try:
        completed = subprocess.run(
            command,
            cwd=UNITY_RUNNER_DIRECTORY,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Unity exceeded the {TIMEOUT_SECONDS}-second timeout. "
            f"Runtime data remains in {run_directory.resolve()}"
        ) from exc

    if completed.returncode != 0:
        raise RuntimeError(
            f"Unity exited with code {completed.returncode}. "
            f"Check {run_directory / 'unity.log'}"
        )

    print(f"Unity simulation finished. Results: {(run_directory / 'Export').resolve()}")
    return run_directory


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one Project Arena Unity map-test JSON with the manual settings "
            "defined near the top of this file."
        )
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to a generated *.unity.json or another map-test config JSON.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        run_unity_map(args.config)
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
