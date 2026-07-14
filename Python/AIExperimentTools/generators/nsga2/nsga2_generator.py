from __future__ import annotations

import copy
import json
import pickle
import random
from typing import Any

from generators.base_generator import (
    BaseGenerator,
    EvaluationFunction,
    EvaluationJob,
    GeneratorContext,
)
from map_schema.canonical_map import CanonicalMap


class NSGA2Generator(BaseGenerator):
    """NSGA-II adapter around the legacy Project Arena All-Black genome."""

    name = "nsga2"

    def generate_maps(self, context: GeneratorContext) -> list[CanonicalMap]:
        raise RuntimeError("NSGA-II is iterative. Call run() through ExperimentManager.")

    def run(
        self,
        context: GeneratorContext,
        evaluate_map: EvaluationFunction,
    ) -> list[dict[str, Any]]:
        try:
            from deap import base, creator, tools
        except ImportError as exc:
            raise RuntimeError(
                "NSGA-II requires DEAP. Install dependencies with "
                "'python -m pip install -r requirements.txt'."
            ) from exc

        from generators.nsga2.internals.ab_genome.ab_genome import ABGenome
        from generators.nsga2.internals.ab_genome.crossover import crossover
        from generators.nsga2.internals.ab_genome.generation import create_random_genome
        from generators.nsga2.internals.ab_genome.mutation import mutate

        if context.population_size < 4 or context.population_size % 4 != 0:
            raise ValueError(
                "NSGA-II population_size must be a multiple of four and at least four"
            )

        objectives = [
            str(value)
            for value in self.settings.get("objectives", ["entropy", "pace"])
        ]
        if len(objectives) < 2:
            raise ValueError("NSGA-II requires at least two objective names")

        fitness_name = "ThesisFitnessMulti"
        individual_name = "ThesisABIndividual"
        if hasattr(creator, fitness_name) is False:
            creator.create(
                fitness_name,
                base.Fitness,
                weights=tuple(1.0 for _ in objectives),
            )
        if hasattr(creator, individual_name) is False:
            creator.create(
                individual_name,
                ABGenome,
                fitness=getattr(creator, fitness_name),
            )

        toolbox = base.Toolbox()
        individual_class = getattr(creator, individual_name)
        toolbox.register("individual", create_random_genome, individual_class)
        toolbox.register("clone", copy.deepcopy)
        toolbox.register("mate", crossover)
        toolbox.register("mutate", mutate)
        toolbox.register("select", tools.selNSGA2)

        random.seed(context.seed)
        cache: dict[bytes, tuple[tuple[float, ...], dict[str, Any]]] = {}
        all_records: list[dict[str, Any]] = []

        def create_canonical_map(individual: Any, epoch: int, index: int) -> CanonicalMap:
            phenotype = individual.phenotype()
            return CanonicalMap.from_area_rectangles(
                map_id=f"nsga2_e{epoch:04d}_i{index:04d}",
                width=phenotype.mapWidth,
                height=phenotype.mapHeight,
                areas=[area.__dict__ for area in phenotype.areas],
                metadata={
                    "generator": self.name,
                    "epoch": epoch,
                    "individual": index,
                    "map_scale": phenotype.mapScale,
                },
            )

        def evaluate_batch(individuals: list[Any], epoch: int) -> None:
            """Prepare maps sequentially, then evaluate unique maps in parallel."""
            pending_jobs: list[EvaluationJob] = []
            pending_keys: list[bytes] = []
            waiting_individuals: dict[bytes, list[Any]] = {}

            for index, individual in enumerate(individuals):
                canonical_map = create_canonical_map(individual, epoch, index)
                key = canonical_map.grid_bytes()

                if key in cache:
                    values, cached_record = cache[key]
                    individual.fitness.values = values
                    individual.evaluation_record = cached_record
                    continue

                waiting_individuals.setdefault(key, []).append(individual)
                if len(waiting_individuals[key]) > 1:
                    continue

                pending_keys.append(key)
                pending_jobs.append(
                    (
                        canonical_map,
                        {
                            "generator": self.name,
                            "epoch": epoch,
                            "individual": index,
                            "population_size": len(individuals),
                            "final_candidate": False,
                        },
                    )
                )

            evaluated_records = self.evaluate_jobs(
                context=context,
                evaluate_map=evaluate_map,
                jobs=pending_jobs,
                epoch=epoch,
            )

            for key, record in zip(pending_keys, evaluated_records):
                values = tuple(
                    self._metric_value(record, objective)
                    for objective in objectives
                )
                cache[key] = (values, record)
                all_records.append(record)

                for individual in waiting_individuals[key]:
                    individual.fitness.values = values
                    individual.evaluation_record = record

        population = [toolbox.individual() for _ in range(context.population_size)]
        evaluate_batch(population, 0)
        population = toolbox.select(population, len(population))
        self._save_checkpoint(context, 0, population, all_records)

        mate_probability = float(self.settings.get("mate_probability", 0.3))
        mutate_probability = float(self.settings.get("mutate_probability", 0.3))

        for epoch in range(1, context.num_epochs + 1):
            offspring = tools.selTournamentDCD(population, len(population))
            offspring = [toolbox.clone(individual) for individual in offspring]

            for first, second in zip(offspring[::2], offspring[1::2]):
                if random.random() <= mate_probability:
                    toolbox.mate(first, second)
                    del first.fitness.values
                    del second.fitness.values

            for individual in offspring:
                if random.random() < mutate_probability:
                    toolbox.mutate(individual)
                    if individual.fitness.valid:
                        del individual.fitness.values

            invalid = [
                individual
                for individual in offspring
                if individual.fitness.valid is False
            ]
            evaluate_batch(invalid, epoch)

            population = toolbox.select(
                population + offspring,
                context.population_size,
            )
            if bool(self.settings.get("checkpoint_every_epoch", True)):
                self._save_checkpoint(context, epoch, population, all_records)

        final_records: list[dict[str, Any]] = []
        final_data: list[dict[str, Any]] = []
        for rank, individual in enumerate(population):
            record = individual.evaluation_record
            record.setdefault("generation_info", {})["final_candidate"] = True
            final_records.append(record)
            final_data.append(
                {
                    "rank_index": rank,
                    "map_id": record["map_id"],
                    "objectives": dict(zip(objectives, individual.fitness.values)),
                }
            )

        final_path = context.output_dir / "_metrics" / "nsga2_final_population.json"
        final_path.write_text(json.dumps(final_data, indent=2), encoding="utf-8")
        return final_records

    @staticmethod
    def _metric_value(record: dict[str, Any], metric: str) -> float:
        if record.get("validation", {}).get("valid") is False:
            return 0.0

        for group_name in ("simulation_metrics", "static_metrics"):
            value = record.get(group_name, {}).get(metric)
            if isinstance(value, (int, float)):
                return float(value)

        raise RuntimeError(
            f"NSGA-II objective '{metric}' is missing for map {record.get('map_id')}. "
            "Enable simulation or select an available static metric."
        )

    @staticmethod
    def _save_checkpoint(
        context: GeneratorContext,
        epoch: int,
        population: list[Any],
        records: list[dict[str, Any]],
    ) -> None:
        checkpoint_dir = context.output_dir / "_raw" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "epoch": epoch,
            "population": population,
            "random_state": random.getstate(),
            "evaluated_map_ids": [record["map_id"] for record in records],
        }
        with (checkpoint_dir / f"checkpoint_epoch_{epoch:04d}.pkl").open("wb") as handle:
            pickle.dump(payload, handle)
