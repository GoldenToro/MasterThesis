from collections import deque
from math import isfinite


class SlidingArchive:
    def __init__(self, bins=10, remap_interval=100, buffer_capacity=1000):
        if any(type(value) is not int for value in (
                bins, remap_interval, buffer_capacity
        )):
            raise ValueError("Archive settings must be integers")

        if bins < 2 or remap_interval < 1 or buffer_capacity < bins:
            raise ValueError("Invalid archive settings")

        self.bins = bins
        self.remap_interval = remap_interval
        self.boundaries = [
            [index / bins for index in range(1, bins)]
            for _ in range(2)
        ]
        self.cells = {}
        self.buffer = deque(maxlen=buffer_capacity)
        self.total = 0
        self.remaps = 0

    def add(self, candidate, descriptors):
        evaluation = candidate.evaluation
        if evaluation is None:
            raise ValueError(
                "Evaluate a candidate before adding it to the archive"
            )

        if not evaluation["valid"] or evaluation["status"] not in {
            "completed", "partial_failure", "partial_evaluation", "simulation_disabled"
        }:
            return

        fitness = float(evaluation["fitness_value"])
        if not isfinite(fitness):
            return

        values = tuple(float(value) for value in descriptors)
        if len(values) != 2 or any(
                not isfinite(value) or not 0.0 <= value <= 1.0
                for value in values
        ):
            raise ValueError(
                "Provide two finite descriptors between 0 and 1"
            )

        entry = {
            "candidate": candidate,
            "descriptors": values,
            "fitness_value": fitness,
        }
        self.buffer.append(entry)
        self.total += 1
        self._insert(entry)

        if self.total % self.remap_interval == 0:
            self._remap()

    def _insert(self, entry):
        cell = tuple(
            sum(value > boundary for boundary in boundaries)
            for value, boundaries in zip(
                entry["descriptors"], self.boundaries
            )
        )
        incumbent = self.cells.get(cell)
        if (
                incumbent is None
                or entry["fitness_value"] > incumbent["fitness_value"]
        ):
            self.cells[cell] = entry

    def _remap(self):
        for axis in range(2):
            values = sorted(
                entry["descriptors"][axis]
                for entry in self.buffer
            )
            self.boundaries[axis] = [
                _quantile(values, index / self.bins)
                for index in range(1, self.bins)
            ]

        entries = list(self.cells.values()) + list(self.buffer)
        self.cells.clear()
        for entry in entries:
            self._insert(entry)
        self.remaps += 1

    def candidates(self):
        return [
            entry["candidate"]
            for _, entry in sorted(self.cells.items())
        ]

    def state(self):
        return {
            "bins": self.bins,
            "boundaries": [
                list(values) for values in self.boundaries
            ],
            "eligible_candidate_count": self.total,
            "remaps": self.remaps,
            "entries": [
                {
                    "cell": list(cell),
                    "map_id": entry["candidate"].map_id,
                    "descriptors": list(entry["descriptors"]),
                    "fitness_value": entry["fitness_value"],
                }
                for cell, entry in sorted(self.cells.items())
            ],
        }


def _quantile(ordered_values, fraction):
    position = (len(ordered_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered_values) - 1)
    return ordered_values[lower] + (
            ordered_values[upper] - ordered_values[lower]
    ) * (position - lower)