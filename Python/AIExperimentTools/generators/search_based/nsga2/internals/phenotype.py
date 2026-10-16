import jsonpickle
import numpy


class Phenotype:
    def __init__(self, map_width, map_height, map_scale, areas):
        self.mapWidth = map_width
        self.mapHeight = map_height
        self.mapScale = map_scale
        self.areas = tuple(areas)

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __hash__(self):
        return hash(tuple(self.__dict__.items()))

    def write_to_file(self, file_path):
        with open(file_path, 'w') as f:
            cp = dict(
                width=self.mapWidth,
                height=self.mapHeight,
                mapScale=self.mapScale,
                areas=self.areas,
            )
            genome_json = jsonpickle.encode(cp, unpicklable=False)
            f.write(genome_json)

    def map_matrix(self):
        map_matrix = numpy.zeros([self.mapHeight, self.mapWidth], dtype=numpy.int8)
        for area in self.areas:
            for row in range(area.bottomRow, area.topRow):
                for col in range(area.leftColumn, area.rightColumn):
                    map_matrix[row][col] = 1
        return tuple(map_matrix.tobytes())
