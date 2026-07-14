import random

from ..ab_genome.ab_genome import AB_NUM_ROOMS, AB_MAX_MAP_WIDTH, AB_MAX_ROOM_SIZE, ABRoom, AB_NUM_CORRIDORS, \
    ABCorridor, AB_CORRIDOR_WIDTH, AB_MIN_ROOM_SIZE, AB_MAX_CORRIDOR_LENGTH, AB_MIN_CORRIDOR_LENGTH


def create_random_genome(individual_init):
    rooms = []
    corridors = []

    for x in range(AB_NUM_ROOMS):
        rooms.append(create_room())
    for x in range(AB_NUM_CORRIDORS):
        corridors.append(create_corridor())

    return individual_init(rooms, corridors)


def create_room():
    size = random.randint(AB_MIN_ROOM_SIZE, AB_MAX_ROOM_SIZE - 1)
    left_col = random.randint(1, AB_MAX_MAP_WIDTH - size - 1)
    bottom_row = random.randint(1, AB_MAX_MAP_WIDTH - size - 1)
    return ABRoom(left_col, bottom_row, size)


def create_corridor():
    length = random.randint(AB_MIN_CORRIDOR_LENGTH, AB_MAX_CORRIDOR_LENGTH - 1)
    if random.random() < 0.5:
        # Horizontal corridor
        left_col = random.randint(1, AB_MAX_MAP_WIDTH - length - 1)
        bottom_row = random.randint(1, AB_MAX_MAP_WIDTH - 1 - AB_CORRIDOR_WIDTH)
        return ABCorridor(left_col, bottom_row, length)
    else:
        # Vertical corridor
        left_col = random.randint(1, AB_MAX_MAP_WIDTH - 1 - AB_CORRIDOR_WIDTH)
        bottom_row = random.randint(1, AB_MAX_MAP_WIDTH - length - 1)
        return ABCorridor(left_col, bottom_row, -length)
