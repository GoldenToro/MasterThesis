from __future__ import annotations

import copy
import json
import pickle
import random
from time import perf_counter
from hashlib import sha1
from typing import Any

from experiment_session import ExperimentSession
from map_schema.canonical_map import CanonicalMap
from candidate import Candidate

def run(base_generator: ExperimentSession) -> list[str]:
    """Run NSGA-II and return the map IDs of the final population."""
    try:
        from deap import base, creator, tools
    except ImportError as exc:
        raise RuntimeError(
            "NSGA-II requires DEAP. Install dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    from generators.nsga2.internals.ab_genome.ab_genome import (
        ABGenome,
        AB_MAX_MAP_WIDTH,
        AB_MAX_MAP_HEIGHT,
        AB_SQUARE_SIZE,
    )
    from generators.nsga2.internals.ab_genome.crossover import crossover
    from generators.nsga2.internals.ab_genome.generation import create_random_genome
    from generators.nsga2.internals.ab_genome.mutation import mutate

    settings = base_generator.generator_settings
    supported_size = (
        AB_MAX_MAP_WIDTH * AB_SQUARE_SIZE,
        AB_MAX_MAP_HEIGHT * AB_SQUARE_SIZE,
    )
    configured_size = (
        settings.get("map_width", supported_size[0]),
        settings.get("map_height", supported_size[1]),
    )
    if configured_size != supported_size:
        raise ValueError(
            "The current NSGA-II genome only supports "
            f"{supported_size[0]}x{supported_size[1]} maps"
        )
    population_size = int(settings["population_size"])

    if population_size < 4 or population_size % 4 != 0:
        raise ValueError(
            "NSGA-II population_size must be a multiple of four and at least four"
        )

    objective_names = base_generator.objective_names
    if len(objective_names) < 2:
        raise ValueError("NSGA-II requires at least two fitness metrics")

    objective_weights = tuple(
        1.0 if str(specification.get("goal", "maximize")) == "maximize" else -1.0
        for specification in base_generator.metric_specs
    )
    if any(
        str(specification.get("goal", "maximize")) not in {"maximize", "minimize"}
        for specification in base_generator.metric_specs
    ):
        raise ValueError("NSGA-II fitness goals must be maximize or minimize")

    signature = sha1(repr(objective_weights).encode("utf-8")).hexdigest()[:10]
    fitness_name = f"ThesisFitnessMulti_{signature}"
    individual_name = f"ThesisABIndividual_{signature}"
    if hasattr(creator, fitness_name) is False:
        creator.create(
            fitness_name,
            base.Fitness,
            weights=objective_weights,
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
    gene_mutation_probability = float(
        settings.get("gene_mutation_probability", 0.2)
    )
    if not 0.0 <= gene_mutation_probability <= 1.0:
        raise ValueError("gene_mutation_probability must be between 0 and 1")

    toolbox.register(
        "mutate",
        mutate,
        gene_mutation_probability=gene_mutation_probability,
    )
    toolbox.register("select", tools.selNSGA2)

    random.seed(base_generator.seed)

    def create_canonical_map(
        individual: Any,
        epoch: int,
        numeric_id: int,
    ) -> CanonicalMap:
        started = perf_counter()
        phenotype = individual.phenotype()
        areas = [area.__dict__ for area in phenotype.areas]
        canonical_map = CanonicalMap.from_area_rectangles(
            map_id=f"nsga2_e{epoch:04d}_i{numeric_id:04d}",
            width=phenotype.mapWidth,
            height=phenotype.mapHeight,
            areas=areas,
            metadata={
                "generator": "nsga2",
                "epoch": epoch,
                "id": numeric_id,
                "map_scale": phenotype.mapScale,
                "genome_representation_type": "all_black",
                "room_count": sum(
                    bool(area.get("isCorridor", False)) is False
                    for area in areas
                ),
                "corridor_count": sum(
                    bool(area.get("isCorridor", False))
                    for area in areas
                ),
                "generation_time_seconds": perf_counter() - started,
            },
        )
        return canonical_map

    def evaluate_batch(
            individuals: list[Any],
            epoch: int,
            numeric_id_start: int = 0,
    ) -> None:
        if not individuals:
            return

        candidates = [
            Candidate(
                canonical_map=create_canonical_map(
                    individual,
                    epoch,
                    numeric_id_start + offset,
                    ),
                genome=individual,
            )
            for offset, individual in enumerate(individuals)
        ]

        evaluated = base_generator.evaluate_candidates(
            candidates,
            epoch=epoch,
        )

        for candidate in evaluated:
            if candidate.evaluation is None:
                raise RuntimeError(
                    f"Candidate '{candidate.map_id}' has no evaluation"
                )

            metrics = candidate.evaluation["metrics"]
            candidate.genome.fitness.values = tuple(
                float(metrics[name])
                for name in objective_names
            )
            candidate.genome.result_map_id = candidate.map_id
    population = [toolbox.individual() for _ in range(population_size)]
    evaluate_batch(population, epoch=0)

    population = toolbox.select(population, population_size)
    _save_checkpoint(base_generator, 0, population)

    yield [str(individual.result_map_id) for individual in population]

    mate_probability = float(settings.get("mate_probability", 0.3))
    mutate_probability = float(settings.get("mutate_probability", 0.3))
    epoch = 1

    while True:
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

        pending = [
            individual
            for individual in offspring
            if not individual.fitness.valid
        ]
        evaluate_batch(pending, epoch)
        if base_generator.production_time_expired():
            return
        population = toolbox.select(population + offspring, population_size)

        if bool(settings.get("checkpoint_every_epoch", True)):
            _save_checkpoint(base_generator, epoch, population)

        yield [str(individual.result_map_id) for individual in population]
        epoch += 1

def _save_checkpoint(
    base_generator: ExperimentSession,
    epoch: int,
    population: list[Any],
) -> None:
    epoch_dir = base_generator.output_dir / f"epoch_{epoch:04d}"
    epoch_dir.mkdir(parents=True, exist_ok=True)
    selected_map_ids = [
        str(getattr(individual, "result_map_id", ""))
        for individual in population
    ]
    payload = {
        "epoch": epoch,
        "population": population,
        "random_state": random.getstate(),
        "selected_map_ids": selected_map_ids,
    }
    with (epoch_dir / "checkpoint.pkl").open("wb") as handle:
        pickle.dump(payload, handle)

    # Lightweight summary for post-experiment analysis. This avoids unpickling
    # DEAP individuals and preserves duplicate map IDs in the selected population.
    (epoch_dir / "checkpoint_summary.json").write_text(
        json.dumps(
            {
                "epoch": epoch,
                "population_size": len(population),
                "selected_map_ids": selected_map_ids,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
