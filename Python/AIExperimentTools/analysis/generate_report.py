from __future__ import annotations

from pathlib import Path
from typing import Any

from analysis.experiment_analyzer import ExperimentAnalyzer


def generate_report(
    run_dir: Path,
    records: list[dict[str, Any]] | None = None,
    reporting_settings: dict[str, Any] | None = None,
    experiment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(experiment or {})
    payload.setdefault("analysis_settings", reporting_settings or {"enabled": True})
    return ExperimentAnalyzer(run_dir, payload).run()
