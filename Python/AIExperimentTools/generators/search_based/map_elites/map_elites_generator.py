import copy
import json
import logging
import math
import random

from candidate import Candidate
from generators.search_based.map_elites.archive import SlidingArchive
from generators.search_based.nsga2.internals.ab_genome.ab_genome import (
    ABGenome,
    AB_MAX_MAP_WIDTH,
    AB_MAX_MAP_HEIGHT,
    AB_SQUARE_SIZE,
)
from generators.search_based.nsga2.internals.ab_genome.crossover import crossover
from generators.search_based.nsga2.internals.ab_genome.generation import create_random_genome
from generators.search_based.nsga2.internals.ab_genome.mutation import mutate
from map_schema.canonical_map import CanonicalMap
from metrics.metric_calculator import MetricContext, calculate_metrics


LOGGER = logging.getLogger("FPS-EVALUATOR")
DESCRIPTORS = ("walkable_area_ratio", "max_symmetry")


def run(session):
    settings = session.generator_settings
    supported_size = (
        AB_MAX_MAP_WIDTH * AB_SQUARE_SIZE,
        AB_MAX_MAP_HEIGHT * AB_SQUARE_SIZE,
    )
    if (settings["map_width"], settings["map_height"]) != supported_size:
        raise ValueError(
            f"The All-Black genome requires {supported_size[0]}x"
            f"{supported_size[1]} maps"
        )

    initial_candidates = settings.get("initial_candidates", 20)
    candidates_per_epoch = settings.get("candidates_per_epoch", 10)
    for value in (initial_candidates, candidates_per_epoch):
        if type(value) is not int or value < 1:
            raise ValueError("Candidate counts must be positive integers")

    mate_probability = float(settings.get("mate_probability", 0.3))
    mutate_probability = float(settings.get("mutate_probability", 0.3))
    gene_mutation_probability = float(
        settings.get("gene_mutation_probability", 0.2)
    )
    if any(not 0 <= value <= 1 for value in (
            mate_probability, mutate_probability, gene_mutation_probability
    )):
        raise ValueError("Variation probabilities must be between 0 and 1")

    archive = SlidingArchive(
        bins=settings.get("bins", 10),
        remap_interval=settings.get("remap_interval", 100),
        buffer_capacity=settings.get("buffer_capacity", 1000),
    )
    random.seed(session.seed)
    epoch = 0

    while True:
        count = initial_candidates if epoch == 0 else candidates_per_epoch
        evaluated_count = 0

        for index in range(count):
            if session.production_time_expired():
                break

            if epoch == 0:
                genome = create_random_genome(ABGenome)
            else:
                parents = archive.candidates()
                genome = copy.deepcopy(random.choice(parents).genome)

                if random.random() < mate_probability:
                    partner = copy.deepcopy(random.choice(parents).genome)
                    crossover(genome, partner)

                if random.random() < mutate_probability:
                    mutate(genome, gene_mutation_probability)

            candidate = Candidate(
                canonical_map=_create_map(genome, epoch, index),
                genome=genome,
            )
            session.evaluate_candidates([candidate], epoch=epoch)
            evaluated_count += 1

            evaluation = candidate.evaluation
            if evaluation is None:
                raise RuntimeError(f"Missing evaluation for {candidate.map_id}")

            if not evaluation["valid"] or evaluation["status"] not in {
                "completed", "partial_failure", "partial_evaluation", "simulation_disabled"
            }:
                continue

            measured = calculate_metrics(
                [],
                list(DESCRIPTORS),
                MetricContext(
                    canonical_map=candidate.canonical_map,
                    experiment=session.experiment,
                ),
            )
            if any(
                    measured[name] is None
                    or not math.isfinite(float(measured[name]))
                    for name in DESCRIPTORS
            ):
                LOGGER.warning("Missing descriptors for %s.", candidate.map_id)
                continue

            archive.add(
                candidate,
                [measured[name] for name in DESCRIPTORS],
            )

        map_ids = [
            candidate.map_id
            for candidate in archive.candidates()
        ]
        directory = session.output_dir / f"epoch_{epoch:04d}"
        directory.mkdir(parents=True, exist_ok=True)

        summary = {
            "epoch": epoch,
            "population_size": len(map_ids),
            "selected_map_ids": map_ids,
            "evaluated_candidate_count": evaluated_count,
            "source": "map_elites",
        }
        (directory / "checkpoint_summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        (directory / "archive.json").write_text(
            json.dumps({
                "descriptor_names": list(DESCRIPTORS),
                **archive.state(),
            }, indent=2),
            encoding="utf-8",
        )

        yield map_ids

        if session.production_time_expired():
            return
        if not map_ids:
            LOGGER.warning("MAP-Elites has no eligible parents; stopping.")
            return

        epoch += 1


def _create_map(genome, epoch, index):
    phenotype = genome.phenotype()
    areas = [area.__dict__ for area in phenotype.areas]
    return CanonicalMap.from_area_rectangles(
        map_id=f"map_elites_e{epoch:04d}_i{index:04d}",
        width=phenotype.mapWidth,
        height=phenotype.mapHeight,
        areas=areas,
        metadata={
            "generator": "map_elites",
            "genome_representation_type": "all_black",
            "epoch": epoch,
            "id": index,
            "map_scale": phenotype.mapScale,
            "room_count": sum(not area["isCorridor"] for area in areas),
            "corridor_count": sum(area["isCorridor"] for area in areas),
        },
    )