import random

from ..ab_genome.ab_genome import AB_NUM_ROOMS, AB_NUM_CORRIDORS


def crossover(ind1, ind2):
    if ind1.phenotype() == ind2.phenotype():
        print("Breed individuals impossible, they are the same!")
        return ind1, ind2

    # Two point crossover
    point_1 = random.randint(0, AB_NUM_ROOMS - 2)
    point_2 = random.randint(point_1 + 1, AB_NUM_ROOMS - 1)

    for x in range(point_1, point_2):
        t = ind1.rooms[x]
        ind1.rooms[x] = ind2.rooms[x]
        ind2.rooms[x] = t

    # Two point crossover
    point_1 = random.randint(0, AB_NUM_CORRIDORS - 2)
    point_2 = random.randint(point_1 + 1, AB_NUM_CORRIDORS - 1)

    for x in range(point_1, point_2):
        t = ind1.corridors[x]
        ind1.corridors[x] = ind2.corridors[x]
        ind2.corridors[x] = t

    return ind1, ind2