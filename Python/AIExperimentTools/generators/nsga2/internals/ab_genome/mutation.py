import random

from ..ab_genome.generation import create_room, create_corridor

def mutate(individual, gene_mutation_probability=0.2):
    for index in range(len(individual.rooms)):
        if random.random() < gene_mutation_probability:
            individual.rooms[index] = create_room()

    for index in range(len(individual.corridors)):
        if random.random() < gene_mutation_probability:
            individual.corridors[index] = create_corridor()

    return individual,