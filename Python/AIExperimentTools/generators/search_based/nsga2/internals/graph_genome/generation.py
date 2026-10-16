import random

from .genome import GG_NUM_ROWS, GG_NUM_COLUMNS, GG_MAX_ROOM_HEIGHT, GG_MAX_ROOM_WIDTH, \
    GG_MIN_ROOM_HEIGHT, GG_MIN_ROOM_WIDTH, GG_MAP_SCALE
from .room import Room

NO_ROOM_PROBABILITY = 0.3
MAX_ROOM_SIZE_PROBABILITY = 0.3
NO_CORRIDOR_PROBABILITY = 0.4


def create_full_room():
    left_col = 0
    bottom_row = 0
    right_col = GG_MAX_ROOM_WIDTH - 1
    top_row = GG_MAX_ROOM_HEIGHT - 1
    return Room(left_col, right_col, bottom_row, top_row)


def create_empty_genome(individual_init):
    rooms = []
    for row in range(GG_NUM_ROWS):
        rooms.append([])
        for col in range(GG_NUM_COLUMNS):
            rooms[row].append(create_full_room())

    vertical_corridors = __create_corridors(GG_NUM_ROWS - 1, GG_NUM_COLUMNS, 0)
    horizontal_corridors = __create_corridors(GG_NUM_ROWS, GG_NUM_COLUMNS - 1, 0)
    map_scale = 3.0
    return individual_init(rooms, vertical_corridors, horizontal_corridors, map_scale)


def create_random_genome(individual_init):
    rooms = __create_rooms()
    vertical_corridors = __create_corridors(GG_NUM_ROWS - 1, GG_NUM_COLUMNS, NO_CORRIDOR_PROBABILITY)
    horizontal_corridors = __create_corridors(GG_NUM_ROWS, GG_NUM_COLUMNS - 1, NO_CORRIDOR_PROBABILITY)
    map_scale = GG_MAP_SCALE
    return individual_init(rooms, vertical_corridors, horizontal_corridors, map_scale)


def __create_rooms():
    rooms = []
    for row in range(GG_NUM_ROWS):
        rooms.append([])
        for col in range(GG_NUM_COLUMNS):
            rooms[row].append(create_room())
    return rooms


def create_room():
    if random.random() < NO_ROOM_PROBABILITY:
        return None
    if random.random() < MAX_ROOM_SIZE_PROBABILITY:
        width = GG_MAX_ROOM_WIDTH
        height = GG_MAX_ROOM_HEIGHT
    else:
        width = random.randint(GG_MIN_ROOM_WIDTH, GG_MAX_ROOM_WIDTH)
        height = random.randint(GG_MIN_ROOM_HEIGHT, GG_MAX_ROOM_HEIGHT)

    left_col = random.randint(0, GG_MAX_ROOM_WIDTH - width)
    bottom_row = random.randint(0, GG_MAX_ROOM_HEIGHT - height)

    right_col = left_col + width
    top_row = bottom_row + height

    return Room(left_col, right_col, bottom_row, top_row)


def __create_corridors(rows, columns, probability):
    corridors = []
    for row in range(rows):
        corridors.append([])
        for col in range(columns):
            corridors[row].append(random.random() > probability)
    return corridors
