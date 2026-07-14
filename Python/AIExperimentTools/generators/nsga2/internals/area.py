
class Area:
    def __init__(self, left_column=0, bottom_row=0, right_column=0, top_row=0, is_corridor=False):
        self.bottomRow = bottom_row
        self.topRow = top_row
        self.leftColumn = left_column
        self.rightColumn = right_column
        self.isCorridor = is_corridor
        self.bottomRow = bottom_row

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __hash__(self):
        return hash(tuple(self.__dict__.items()))


def scale_area(area, scale):
    return Area(
        scale * area.leftColumn,
        scale * area.bottomRow,
        scale * area.rightColumn,
        scale * area.topRow,
        area.isCorridor,
    )
