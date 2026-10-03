import random


def crossover(ind1, ind2):
    for attribute in ("rooms", "corridors"):
        first = getattr(ind1, attribute)
        second = getattr(ind2, attribute)
        if len(first) != len(second):
            raise ValueError("Parents must have matching gene counts")
        if not first:
            continue

        start, end = sorted(random.sample(range(len(first) + 1), 2))
        first[start:end], second[start:end] = (
            second[start:end],
            first[start:end],
        )

    return ind1, ind2