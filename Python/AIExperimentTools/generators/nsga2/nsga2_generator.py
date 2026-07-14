from __future__ import annotations

import copy
import json
import pickle
import random
from hashlib import sha1
from typing import Any

from generators.base_generator import BaseGenerator
from map_schema.canonical_map import CanonicalMap


def run(base_generator: BaseGenerator) -> list[str]:
    """Run NSGA-II and return the map IDs of the final population."""
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

    settings = base_generator.generator_settings
    population_size = int(settings["population_size"])
    num_epochs = int(settings["num_epochs"])
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
    toolbox.register("mutate", mutate)
    toolbox.register("select", tools.selNSGA2)

    random.seed(base_generator.seed)

    def create_canonical_map(
        individual: Any,
        epoch: int,
        numeric_id: int,
    ) -> CanonicalMap:
        phenotype = individual.phenotype()
        return CanonicalMap.from_area_rectangles(
            map_id=f"nsga2_e{epoch:04d}_i{numeric_id:04d}",
            width=phenotype.mapWidth,
            height=phenotype.mapHeight,
            areas=[area.__dict__ for area in phenotype.areas],
            metadata={
                "generator": "nsga2",
                "epoch": epoch,
                "id": numeric_id,
                "map_scale": phenotype.mapScale,
            },
        )

    def evaluate_batch(individuals: list[Any], epoch: int) -> None:
        if len(individuals) == 0:
            return
        maps = [
            create_canonical_map(individual, epoch, numeric_id)
            for numeric_id, individual in enumerate(individuals)
        ]
        epoch_dir = base_generator.save_epoch_maps(epoch, maps)
        table = base_generator.evaluate_epoch(epoch_dir)
        if len(table) != len(individuals):
            raise RuntimeError(
                f"Expected {len(individuals)} evaluation rows, received {len(table)}"
            )

        table = table[np.argsort(table["id"])]
        for individual, row in zip(individuals, table):
            individual.fitness.values = tuple(
                float(row[name]) for name in objective_names
            )
            individual.result_map_id = str(row["map_id"])

    import numpy as np

    population = [toolbox.individual() for _ in range(population_size)]
    evaluate_batch(population, 0)
    population = toolbox.select(population, len(population))
    _save_checkpoint(base_generator, 0, population)

    mate_probability = float(settings.get("mate_probability", 0.3))
    mutate_probability = float(settings.get("mutate_probability", 0.3))

    for epoch in range(1, num_epochs + 1):
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
            if individual.fitness.valid is False
        ]
        evaluate_batch(pending, epoch)
        population = toolbox.select(population + offspring, population_size)

        if bool(settings.get("checkpoint_every_epoch", True)):
            _save_checkpoint(base_generator, epoch, population)

    final_map_ids = [
        str(getattr(individual, "result_map_id"))
        for individual in population
    ]
    return final_map_ids


def _save_checkpoint(
    base_generator: BaseGenerator,
    epoch: int,
    population: list[Any],
) -> None:
    epoch_dir = base_generator.output_dir / f"epoch_{epoch:04d}"
    epoch_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "epoch": epoch,
        "population": population,
        "random_state": random.getstate(),
        "selected_map_ids": [
            str(getattr(individual, "result_map_id", ""))
            for individual in population
        ],
    }
    with (epoch_dir / "checkpoint.pkl").open("wb") as handle:
        pickle.dump(payload, handle)
