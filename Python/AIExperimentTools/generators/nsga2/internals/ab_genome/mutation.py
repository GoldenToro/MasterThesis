import random

from ..ab_genome.ab_genome import AB_NUM_ROOMS, AB_NUM_CORRIDORS
from ..ab_genome.generation import create_room, create_corridor

MUTATE_PROBABILITY = 0.2


def mutate(individual):
    for x in range(AB_NUM_ROOMS):
        if random.random() < MUTATE_PROBABILITY:
            individual.rooms[x] = create_room()

    for x in range(AB_NUM_CORRIDORS):
        if random.random() < MUTATE_PROBABILITY:
            individual.corridors[x] = create_corridor()

    return individual,

