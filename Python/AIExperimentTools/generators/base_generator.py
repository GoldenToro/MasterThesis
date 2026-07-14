from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from map_schema.canonical_map import CanonicalMap


LOGGER = logging.getLogger("FPS-EVALUATOR")
EvaluationFunction = Callable[[CanonicalMap, dict[str, Any]], dict[str, Any]]
EvaluationJob = tuple[CanonicalMap, dict[str, Any]]


@dataclass(frozen=True)
class GeneratorContext:
    experiment_name: str
    map_width: int
    map_height: int
    num_epochs: int
    population_size: int
    seed: int
    output_dir: Path
    framework_root: Path
    technical_settings: dict[str, Any]
    experiment: dict[str, Any]


class BaseGenerator(ABC):
    """Common interface for every map generation method."""

    name = "base"

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    @abstractmethod
    def generate_maps(self, context: GeneratorContext) -> list[CanonicalMap]:
        """Create final candidate maps for constructive generators."""

    def run(
        self,
        context: GeneratorContext,
        evaluate_map: EvaluationFunction,
    ) -> list[dict[str, Any]]:
        """Generate and evaluate maps.

        Constructive generators use the shared parallel evaluator here.
        Iterative generators such as NSGA-II reuse ``evaluate_jobs`` inside
        their optimization loop.
        """
        jobs: list[EvaluationJob] = []
        for index, canonical_map in enumerate(self.generate_maps(context)):
            jobs.append(
                (
                    canonical_map,
                    {
                "generator": self.name,
                "map_index": index,
                "seed": context.seed + index,
                "epoch": 0,
                "final_candidate": True,
                    },
                )
            )

        return self.evaluate_jobs(
            context=context,
            evaluate_map=evaluate_map,
            jobs=jobs,
            epoch=0,
        )

    @staticmethod
    def evaluate_jobs(
        context: GeneratorContext,
        evaluate_map: EvaluationFunction,
        jobs: Iterable[EvaluationJob],
        epoch: int,
    ) -> list[dict[str, Any]]:
        """Evaluate independent maps with a shared worker limit.

        The result order matches the input order. A worker count of one keeps
        the old sequential behavior, which is useful for debugging.
        """
        raw_jobs = list(jobs)
        if len(raw_jobs) == 0:
            LOGGER.info(
                "Start simulating epoch %s for experiment '%s': no new maps require evaluation.",
                epoch,
                context.experiment_name,
            )
            return []

        prepared_jobs: list[EvaluationJob] = []
        batch_size = len(raw_jobs)
        for batch_index, (canonical_map, generation_info) in enumerate(raw_jobs):
            info = dict(generation_info)
            info.setdefault("epoch", epoch)
            info["simulation_batch_map_index"] = batch_index
            info["simulation_batch_map_count"] = batch_size
            prepared_jobs.append((canonical_map, info))

        execution_settings = context.technical_settings.get("execution", {})
        configured_workers = int(
            execution_settings.get("max_parallel_map_evaluations", 1)
        )
        max_workers = max(1, min(configured_workers, batch_size))

        LOGGER.info(
            "Start simulating epoch %s for experiment '%s': %s maps, up to %s parallel map evaluations.",
            epoch,
            context.experiment_name,
            batch_size,
            max_workers,
        )

        def run_job(job: EvaluationJob) -> dict[str, Any]:
            canonical_map, generation_info = job
            return evaluate_map(canonical_map, generation_info)

        if max_workers == 1:
            results = [run_job(job) for job in prepared_jobs]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = list(executor.map(run_job, prepared_jobs))

        LOGGER.info(
            "Finished simulating epoch %s for experiment '%s'.",
            epoch,
            context.experiment_name,
        )
        return results
