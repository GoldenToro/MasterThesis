import random

from .genome import GG_NUM_COLUMNS, GG_NUM_ROWS


def crossover(ind1, ind2):
    if ind1.phenotype() == ind2.phenotype():
        print("Breed individuals impossible, they are the same!")
        return ind1, ind2

    mid_point_row = random.randint(0, GG_NUM_ROWS - 2)
    mid_point_column = random.randint(0, GG_NUM_COLUMNS - 2)

    if random.random() < 0.5:
        start_row = 0
        end_row = mid_point_row
    else:
        start_row = mid_point_row
        end_row = GG_NUM_ROWS - 1

    if random.random() < 0.5:
        start_column = 0
        end_column = mid_point_column
    else:
        start_column = mid_point_column
        end_column = GG_NUM_COLUMNS - 1

    # Rooms
    room1 = ind1.rooms
    room2 = ind2.rooms
    for row in range(start_row, end_row):
        for col in range(start_column, end_column):
            t = room1[row][col]
            room1[row][col] = room2[row][col]
            room2[row][col] = t

    # Horizontal corridors
    h_corr1 = ind1.horizontalCorridors
    h_corr2 = ind2.horizontalCorridors
    for row in range(start_row, end_row):
        for col in range(start_column, min(end_column, GG_NUM_COLUMNS - 2)):
            t = h_corr1[row][col]
            h_corr2[row][col] = h_corr1[row][col]
            h_corr1[row][col] = t

    # Vertical corridors
    v_corr1 = ind1.verticalCorridors
    v_corr2 = ind2.verticalCorridors
    for row in range(start_row, min(end_row, GG_NUM_ROWS - 2)):
        for col in range(start_column, end_column):
            t = v_corr1[row][col]
            v_corr2[row][col] = v_corr1[row][col]
            v_corr1[row][col] = t

    return ind1, ind2
