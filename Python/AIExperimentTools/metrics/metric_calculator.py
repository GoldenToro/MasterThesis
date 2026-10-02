from __future__ import annotations

import json
import math
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Callable

from map_schema.canonical_map import (
    AMMO,
    FLOOR,
    HEALTH,
    SPAWN,
    WALL,
    WALKABLE_SYMBOLS,
    CanonicalMap,
)

try:
    import networkx as nx
except ImportError:  # pragma: no cover - handled through a clear runtime error
    nx = None


MetricValue = float | int | str | dict[str, float] | None
MetricFunction = Callable[["MetricContext"], MetricValue]


@dataclass
class MetricContext:
    """All data sources available while calculating one map's metrics."""

    canonical_map: CanonicalMap | None = None
    match_records: list[dict[str, Any]] = field(default_factory=list)
    record: dict[str, Any] = field(default_factory=dict)
    raw_map_dir: Path | None = None
    experiment: dict[str, Any] = field(default_factory=dict)
    all_records: list[dict[str, Any]] = field(default_factory=list)
    all_contexts: list["MetricContext"] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict)

    def map_scale(self) -> float:
        if self.canonical_map is None:
            return 1.0
        return float(self.canonical_map.metadata.get("map_scale", 1.0))

    def raw_files(self, pattern: str) -> list[Path]:
        if self.raw_map_dir is None or self.raw_map_dir.is_dir() is False:
            return []
        return sorted(self.raw_map_dir.glob(f"simulation_*/Export/{pattern}"))

    def positions(self, bot_index: int) -> list[tuple[float, float]]:
        key = f"positions_{bot_index}"
        if key not in self.cache:
            values: list[tuple[float, float]] = []
            for path in self.raw_files(f"position_*_bot{bot_index}.csv"):
                values.extend(_read_decimal_comma_rows(path, expected_values=2))
            self.cache[key] = values
        return list(self.cache[key])

    def death_positions(self, bot_index: int) -> list[tuple[float, float]]:
        key = f"death_positions_{bot_index}"
        if key not in self.cache:
            values: list[tuple[float, float]] = []
            for path in self.raw_files(f"death_positions_*_bot{bot_index}.csv"):
                for row in _read_decimal_comma_rows(path, expected_values=4):
                    values.append((row[0], row[1]))
            self.cache[key] = values
        return list(self.cache[key])

    def kill_distances(self, bot_index: int | None = None) -> list[float]:
        suffix = "all" if bot_index is None else str(bot_index)
        key = f"kill_distances_{suffix}"
        if key not in self.cache:
            pattern = "kill_distances_*_bot*.csv" if bot_index is None else f"kill_distances_*_bot{bot_index}.csv"
            values: list[float] = []
            for path in self.raw_files(pattern):
                rows = _read_decimal_comma_rows(path, expected_values=1)
                values.extend(row[0] for row in rows)
            self.cache[key] = values
        return list(self.cache[key])


@dataclass
class PopulationMetricContext:
    """Data sources for metrics that describe a generation or experiment set."""

    population_contexts: list[MetricContext] = field(default_factory=list)
    evaluated_contexts: list[MetricContext] = field(default_factory=list)
    experiment: dict[str, Any] = field(default_factory=dict)




# Names exposed by analysis_settings.calculate_metric and calculate_all_metrics.
# Raw position arrays stay in Unity CSV files. The analysis CSV stores counts and
# derived values to keep results.csv manageable.
ANALYSIS_METRIC_NAMES: tuple[str, ...] = (
    "map_width",
    "map_height",
    "total_tile_count",
    "walkable_tile_count",
    "wall_tile_count",
    "room_count",
    "corridor_count",
    "spawn_count",
    "pickup_count",
    "walkable_area_ratio",
    "largest_navigable_region_ratio",
    "connectivity",
    "number_of_connected_components",
    "symmetry_x",
    "symmetry_y",
    "max_symmetry",
    "average_eccentricity",
    "graph_diameter",
    "graph_radius",
    "graph_density",
    "degree_centrality",
    "closeness_centrality",
    "betweenness_centrality",
    "chokepoint_count",
    "loop_count",
    "alternative_path_count",
    "average_visibility",
    "maximum_visibility",
    "visibility_local_maxima_count",
    "maximum_sightline_length",
    "spawn_distance_balance",
    "spawn_exposure",
    "spawn_escape_routes",
    "number_of_frags_bot_1",
    "number_of_frags_bot_2",
    "number_of_shots_bot_1",
    "number_of_shots_bot_2",
    "number_of_hits_bot_1",
    "number_of_hits_bot_2",
    "accuracy_bot_1",
    "accuracy_bot_2",
    "number_of_fights_bot_1",
    "number_of_fights_bot_2",
    "time_in_fight_bot_1",
    "time_in_fight_bot_2",
    "time_to_engage_bot_1",
    "time_to_engage_bot_2",
    "number_of_sights_bot_1",
    "number_of_sights_bot_2",
    "time_between_sights_bot_1",
    "time_between_sights_bot_2",
    "number_of_retreats_bot_1",
    "number_of_retreats_bot_2",
    "time_to_surrender_bot_1",
    "time_to_surrender_bot_2",
    "number_of_suicides_bot_1",
    "number_of_suicides_bot_2",
    "kill_streak_average_bot_1",
    "kill_streak_average_bot_2",
    "kill_streak_max_bot_1",
    "kill_streak_max_bot_2",
    "entropy",
    "pace",
    "fight_time",
    "pursue_time",
    "sight_loss_rate",
    "target_loss_rate",
    "kill_difference",
    "kill_ratio",
    "movement_position_count_bot_1",
    "movement_position_count_bot_2",
    "movement_heatmap_coverage",
    "area_dominance",
    "death_position_count_bot_1",
    "death_position_count_bot_2",
    "death_hotspot_concentration",
    "kill_distance_count",
    "average_combat_distance",
    "combat_distance_distribution",
    "spawn_death_rate",
    "map_diversity",
    "expressive_range",
    "generator_success_rate",
    "generator_efficiency",
    "controllability_score",
    "overall_map_quality_score",
    "overall_generator_score",
    "generated_map_count",
    "valid_map_count",
    "invalid_map_count",
    "generation_time_per_map",
    "repair_count",
    "constraint_violation_count",
    "generator_method_label",
    "genome_representation_type",
)

# These metrics describe a set of maps. They belong in results_by_epoch.csv
# and the experiment summary, rather than being repeated on every map row.
POPULATION_METRIC_NAMES = frozenset(
    {
        "map_diversity",
        "expressive_range",
        "generator_success_rate",
        "generator_efficiency",
        "overall_generator_score",
        "generated_map_count",
        "valid_map_count",
        "invalid_map_count",
    }
)
MAP_METRIC_NAMES = tuple(
    name for name in ANALYSIS_METRIC_NAMES if name not in POPULATION_METRIC_NAMES
)

NON_SCALAR_METRICS = frozenset({"combat_distance_distribution"})
TEXT_METRICS = frozenset({"generator_method_label", "genome_representation_type"})
NUMERIC_METRIC_NAMES = frozenset(ANALYSIS_METRIC_NAMES) - NON_SCALAR_METRICS - TEXT_METRICS
MAP_NUMERIC_METRIC_NAMES = frozenset(MAP_METRIC_NAMES) - NON_SCALAR_METRICS - TEXT_METRICS


def available_metric_names() -> list[str]:
    return list(ANALYSIS_METRIC_NAMES)


def calculate_entropy(match_records: list[dict[str, Any]]) -> float | None:
    return _mean_numeric(match_records, "entropy")


def calculate_pace(match_records: list[dict[str, Any]]) -> float | None:
    return _mean_numeric(match_records, "pace")


def calculate_metrics(
    match_records: list[dict[str, Any]],
    metric_names: list[str],
    context: MetricContext | None = None,
) -> dict[str, MetricValue]:
    """Calculate metrics that describe one generated map."""

    metric_context = context or MetricContext(match_records=list(match_records))
    if context is not None and len(metric_context.match_records) == 0:
        metric_context.match_records = list(match_records)

    result: dict[str, MetricValue] = {}
    for requested_name in metric_names:
        name = normalize_metric_name(requested_name)
        if name in POPULATION_METRIC_NAMES:
            raise ValueError(
                f"Metric '{requested_name}' describes a map set and requires "
                "calculate_population_metrics()."
            )
        function = _METRIC_FUNCTIONS.get(name)
        if function is None:
            raise ValueError(
                f"Metric '{requested_name}' is unavailable. Available map metrics: "
                + ", ".join(MAP_METRIC_NAMES)
            )
        result[name] = function(metric_context)
    return result


def calculate_population_metrics(
    context: PopulationMetricContext,
    metric_names: list[str],
) -> dict[str, MetricValue]:
    """Calculate metrics that describe one epoch population or the full run."""

    result: dict[str, MetricValue] = {}
    for requested_name in metric_names:
        name = normalize_metric_name(requested_name)
        function = _POPULATION_METRIC_FUNCTIONS.get(name)
        if function is None:
            raise ValueError(
                f"Metric '{requested_name}' is unavailable as a population metric. "
                "Available population metrics: "
                + ", ".join(sorted(POPULATION_METRIC_NAMES))
            )
        result[name] = function(context)
    return result


def normalize_metric_name(name: str) -> str:
    return "_".join(str(name).strip().lower().replace("-", " ").split())


def _canonical_map(context: MetricContext) -> CanonicalMap | None:
    return context.canonical_map


def _walkable_cells(context: MetricContext) -> list[tuple[int, int]]:
    key = "walkable_cells"
    if key not in context.cache:
        canonical_map = _canonical_map(context)
        context.cache[key] = canonical_map.walkable_cells() if canonical_map else []
    return list(context.cache[key])


def _graph_bundle(context: MetricContext) -> dict[str, Any]:
    if "graph_bundle" in context.cache:
        return context.cache["graph_bundle"]
    if nx is None:
        raise RuntimeError(
            "Graph metrics require networkx. Install dependencies with "
            "'python -m pip install -r requirements.txt'."
        )

    graph = nx.Graph()
    walkable = set(_walkable_cells(context))
    graph.add_nodes_from(walkable)
    for x, y in walkable:
        for neighbor in ((x + 1, y), (x, y + 1)):
            if neighbor in walkable:
                graph.add_edge((x, y), neighbor)
    components = [set(component) for component in nx.connected_components(graph)] if graph.number_of_nodes() else []
    components.sort(key=len, reverse=True)
    largest = graph.subgraph(components[0]).copy() if components else nx.Graph()
    bundle = {"graph": graph, "components": components, "largest": largest}
    context.cache["graph_bundle"] = bundle
    return bundle


def _distance_bundle(context: MetricContext) -> dict[str, Any]:
    if "distance_bundle" in context.cache:
        return context.cache["distance_bundle"]
    graph = _graph_bundle(context)["largest"]
    if graph.number_of_nodes() == 0:
        bundle = {"eccentricities": {}, "closeness": {}}
    elif graph.number_of_nodes() == 1:
        node = next(iter(graph.nodes))
        bundle = {"eccentricities": {node: 0}, "closeness": {node: 0.0}}
    else:
        eccentricities: dict[tuple[int, int], int] = {}
        closeness: dict[tuple[int, int], float] = {}
        node_count = graph.number_of_nodes()
        for node, distances in nx.all_pairs_shortest_path_length(graph):
            values = list(distances.values())
            eccentricities[node] = max(values)
            total = sum(values)
            closeness[node] = (node_count - 1) / total if total else 0.0
        bundle = {"eccentricities": eccentricities, "closeness": closeness}
    context.cache["distance_bundle"] = bundle
    return bundle


def _visibility_bundle(context: MetricContext) -> dict[str, Any]:
    """Eight-direction grid visibility used consistently by all visibility metrics."""

    if "visibility_bundle" in context.cache:
        return context.cache["visibility_bundle"]
    canonical_map = _canonical_map(context)
    walkable = set(_walkable_cells(context))
    if canonical_map is None or len(walkable) == 0:
        bundle = {"counts": {}, "scores": {}, "max_length": 0.0}
        context.cache["visibility_bundle"] = bundle
        return bundle

    directions = (
        (-1, -1), (0, -1), (1, -1),
        (-1, 0),            (1, 0),
        (-1, 1),  (0, 1),   (1, 1),
    )
    counts: dict[tuple[int, int], int] = {}
    longest = 0.0
    for x, y in walkable:
        visible = 0
        for dx, dy in directions:
            step = 1
            while True:
                candidate = (x + dx * step, y + dy * step)
                if candidate not in walkable:
                    break
                visible += 1
                longest = max(longest, math.hypot(dx * step, dy * step))
                step += 1
        counts[(x, y)] = visible
    denominator = max(1, len(walkable) - 1)
    scores = {cell: count / denominator for cell, count in counts.items()}
    bundle = {
        "counts": counts,
        "scores": scores,
        "max_length": longest,
    }
    context.cache["visibility_bundle"] = bundle
    return bundle


def _mean_unity(context: MetricContext, key: str) -> float | None:
    return _mean_numeric(context.match_records, key)


def _maximum_unity(context: MetricContext, key: str) -> float | None:
    values = [
        float(record[key])
        for record in context.match_records
        if _is_number(record.get(key))
    ]
    return max(values) if values else None


def _pooled_accuracy(
    context: MetricContext,
    hit_key: str,
    shot_key: str,
    fallback_key: str,
) -> float | None:
    hits = [float(record[hit_key]) for record in context.match_records if _is_number(record.get(hit_key))]
    shots = [float(record[shot_key]) for record in context.match_records if _is_number(record.get(shot_key))]
    if len(hits) == len(shots) and len(hits) > 0:
        total_shots = sum(shots)
        return sum(hits) / total_shots if total_shots > 0 else 0.0
    return _mean_unity(context, fallback_key)


def _raw_count(context: MetricContext, pattern: str, values: list[Any]) -> int | None:
    # Missing log files mean the metric is unavailable. Existing empty files mean 0.
    return len(values) if context.raw_files(pattern) else None


def _map_width(context: MetricContext) -> int | None:
    return context.canonical_map.width if context.canonical_map else None


def _map_height(context: MetricContext) -> int | None:
    return context.canonical_map.height if context.canonical_map else None


def _total_tile_count(context: MetricContext) -> int | None:
    canonical_map = context.canonical_map
    return canonical_map.width * canonical_map.height if canonical_map else None


def _walkable_tile_count(context: MetricContext) -> int | None:
    return len(_walkable_cells(context)) if context.canonical_map else None


def _wall_tile_count(context: MetricContext) -> int | None:
    canonical_map = context.canonical_map
    return len(canonical_map.cells_with({WALL})) if canonical_map else None


def _symbol_count(context: MetricContext, symbol: str) -> int | None:
    canonical_map = context.canonical_map
    return len(canonical_map.cells_with({symbol})) if canonical_map else None


def _metadata_number(context: MetricContext, key: str) -> float | int | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    value = canonical_map.metadata.get(key)
    if isinstance(value, (int, float)) and isinstance(value, bool) is False:
        return value
    return None


def _walkable_area_ratio(context: MetricContext) -> float | None:
    total = _total_tile_count(context)
    walkable = _walkable_tile_count(context)
    return walkable / total if total and walkable is not None else None


def _largest_region_ratio(context: MetricContext) -> float | None:
    walkable = len(_walkable_cells(context))
    components = _graph_bundle(context)["components"]
    return len(components[0]) / walkable if walkable and components else None


def _connectivity(context: MetricContext) -> float | None:
    """Fraction of all walkable tile pairs that can reach each other."""

    component_sizes = [len(component) for component in _graph_bundle(context)["components"]]
    total = sum(component_sizes)
    if total <= 1:
        return 1.0 if total == 1 else None
    reachable_pairs = sum(size * (size - 1) / 2 for size in component_sizes)
    all_pairs = total * (total - 1) / 2
    return reachable_pairs / all_pairs


def _component_count(context: MetricContext) -> int | None:
    if context.canonical_map is None:
        return None
    return len(_graph_bundle(context)["components"])


def _symmetry(context: MetricContext, axis: str) -> float | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    binary = [[symbol in WALKABLE_SYMBOLS for symbol in row] for row in canonical_map.grid]
    equal = 0
    total = canonical_map.width * canonical_map.height
    for y in range(canonical_map.height):
        for x in range(canonical_map.width):
            mirror_x = canonical_map.width - 1 - x if axis == "x" else x
            mirror_y = canonical_map.height - 1 - y if axis == "y" else y
            equal += int(binary[y][x] == binary[mirror_y][mirror_x])
    return equal / total if total else None


def _average_eccentricity(context: MetricContext) -> float | None:
    values = list(_distance_bundle(context)["eccentricities"].values())
    return mean(values) if values else None


def _graph_diameter(context: MetricContext) -> float | None:
    values = list(_distance_bundle(context)["eccentricities"].values())
    return float(max(values)) if values else None


def _graph_radius(context: MetricContext) -> float | None:
    values = list(_distance_bundle(context)["eccentricities"].values())
    return float(min(values)) if values else None


def _graph_density(context: MetricContext) -> float | None:
    graph = _graph_bundle(context)["largest"]
    return float(nx.density(graph)) if graph.number_of_nodes() else None


def _degree_centrality(context: MetricContext) -> float | None:
    graph = _graph_bundle(context)["largest"]
    values = list(nx.degree_centrality(graph).values()) if graph.number_of_nodes() else []
    return mean(values) if values else None


def _closeness_centrality(context: MetricContext) -> float | None:
    values = list(_distance_bundle(context)["closeness"].values())
    return mean(values) if values else None


def _betweenness_centrality(context: MetricContext) -> float | None:
    graph = _graph_bundle(context)["largest"]
    node_count = graph.number_of_nodes()
    if node_count == 0:
        return None
    sample_size = min(100, node_count)
    values = nx.betweenness_centrality(
        graph,
        k=sample_size if sample_size < node_count else None,
        normalized=True,
        seed=0,
    ).values()
    return mean(values) if values else None


def _chokepoint_count(context: MetricContext) -> int | None:
    graph = _graph_bundle(context)["largest"]
    return sum(1 for _ in nx.articulation_points(graph)) if graph.number_of_nodes() else None


def _loop_count(context: MetricContext) -> int | None:
    graph = _graph_bundle(context)["graph"]
    if graph.number_of_nodes() == 0:
        return None
    component_count = nx.number_connected_components(graph)
    return graph.number_of_edges() - graph.number_of_nodes() + component_count


def _alternative_path_count(context: MetricContext) -> int | None:
    graph = _graph_bundle(context)["largest"]
    if graph.number_of_nodes() == 0:
        return None
    return sum(1 for component in nx.biconnected_components(graph) if len(component) >= 3)


def _average_visibility(context: MetricContext) -> float | None:
    scores = list(_visibility_bundle(context)["scores"].values())
    return mean(scores) if scores else None


def _maximum_visibility(context: MetricContext) -> float | None:
    scores = list(_visibility_bundle(context)["scores"].values())
    return max(scores) if scores else None


def _visibility_local_maxima_count(context: MetricContext) -> int | None:
    scores = _visibility_bundle(context)["scores"]
    if len(scores) == 0:
        return None
    maxima = 0
    for (x, y), score in scores.items():
        neighbors = [
            scores[position]
            for position in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            if position in scores
        ]
        if len(neighbors) == 0 or (score >= max(neighbors) and any(score > value for value in neighbors)):
            maxima += 1
    return maxima


def _maximum_sightline_length(context: MetricContext) -> float | None:
    if context.canonical_map is None:
        return None
    return float(_visibility_bundle(context)["max_length"])


def _spawn_distance_balance(context: MetricContext) -> float | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    spawns = canonical_map.cells_with({SPAWN})
    graph = _graph_bundle(context)["graph"]
    if len(spawns) < 2 or graph.number_of_nodes() == 0:
        return None
    average_distances: list[float] = []
    for spawn in spawns:
        if spawn not in graph:
            continue
        distances = nx.single_source_shortest_path_length(graph, spawn)
        average_distances.append(mean(distances.values()))
    if len(average_distances) < 2:
        return None
    maximum = max(average_distances)
    return 1.0 - ((maximum - min(average_distances)) / maximum) if maximum else 1.0


def _spawn_exposure(context: MetricContext) -> float | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    scores = _visibility_bundle(context)["scores"]
    values = [scores[cell] for cell in canonical_map.cells_with({SPAWN}) if cell in scores]
    return mean(values) if values else None


def _spawn_escape_routes(context: MetricContext) -> float | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    walkable = set(_walkable_cells(context))
    values = []
    for x, y in canonical_map.cells_with({SPAWN}):
        exits = sum(
            (neighbor in walkable)
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        )
        values.append(exits / 4.0)
    return mean(values) if values else None

def _kill_difference(context: MetricContext) -> float | None:
    values = []
    for record in context.match_records:
        first = record.get("numberOfFrags1")
        second = record.get("numberOfFrags2")
        if _is_number(first) and _is_number(second):
            values.append(abs(float(first) - float(second)))
    return mean(values) if values else None


def _kill_ratio(context: MetricContext) -> float | None:
    """Balanced kill ratio: lower frags / higher frags, in the range 0..1."""

    values = []
    for record in context.match_records:
        first = record.get("numberOfFrags1")
        second = record.get("numberOfFrags2")
        if _is_number(first) and _is_number(second):
            high = max(float(first), float(second))
            low = min(float(first), float(second))
            values.append(low / high if high else 1.0)
    return mean(values) if values else None


def _world_to_cell(context: MetricContext, position: tuple[float, float]) -> tuple[int, int] | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    scale = max(context.map_scale(), 1e-9)
    x = int(math.floor(position[0] / scale))
    unity_y = int(math.floor(position[1] / scale))
    y = canonical_map.height - 1 - unity_y
    if 0 <= x < canonical_map.width and 0 <= y < canonical_map.height:
        return x, y
    return None


def _movement_heatmap_coverage(context: MetricContext) -> float | None:
    if not (context.raw_files("position_*_bot1.csv") or context.raw_files("position_*_bot2.csv")):
        return None
    walkable = set(_walkable_cells(context))
    if len(walkable) == 0:
        return None
    visited = {
        cell
        for bot in (1, 2)
        for position in context.positions(bot)
        if (cell := _world_to_cell(context, position)) in walkable
    }
    return len(visited) / len(walkable)


def _area_dominance(context: MetricContext) -> float | None:
    if not (context.raw_files("position_*_bot1.csv") or context.raw_files("position_*_bot2.csv")):
        return None
    first = {
        cell
        for position in context.positions(1)
        if (cell := _world_to_cell(context, position)) is not None
    }
    second = {
        cell
        for position in context.positions(2)
        if (cell := _world_to_cell(context, position)) is not None
    }
    total = len(first) + len(second)
    return abs(len(first) - len(second)) / total if total else None


def _death_hotspot_concentration(context: MetricContext) -> float | None:
    cells = [
        cell
        for bot in (1, 2)
        for position in context.death_positions(bot)
        if (cell := _world_to_cell(context, position)) is not None
    ]
    if len(cells) == 0:
        return None
    counts = Counter(cells)
    return max(counts.values()) / len(cells)


def _average_combat_distance(context: MetricContext) -> float | None:
    values = context.kill_distances()
    return mean(values) if values else None


def _combat_distance_distribution(context: MetricContext) -> dict[str, float] | None:
    values = context.kill_distances()
    if len(values) == 0:
        return None
    settings = context.experiment.get("analysis_settings", {})
    thresholds = settings.get("combat_distance_thresholds", [15.0, 35.0])
    close_limit = float(thresholds[0])
    medium_limit = float(thresholds[1])
    count = len(values)
    return {
        "close_ratio": sum(value < close_limit for value in values) / count,
        "medium_ratio": sum(close_limit <= value < medium_limit for value in values) / count,
        "long_ratio": sum(value >= medium_limit for value in values) / count,
        "standard_deviation": pstdev(values) if len(values) > 1 else 0.0,
    }


def _spawn_death_rate(context: MetricContext) -> float | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    spawns = canonical_map.cells_with({SPAWN})
    deaths = [position for bot in (1, 2) for position in context.death_positions(bot)]
    if len(spawns) == 0 or len(deaths) == 0:
        return None
    radius_tiles = float(
        context.experiment.get("analysis_settings", {}).get("spawn_death_radius_tiles", 3.0)
    )
    scale = context.map_scale()
    spawn_world = [
        ((x + 0.5) * scale, (canonical_map.height - 1 - y + 0.5) * scale)
        for x, y in spawns
    ]
    radius_world = radius_tiles * scale
    nearby = sum(
        any(math.dist(death, spawn) <= radius_world for spawn in spawn_world)
        for death in deaths
    )
    return nearby / len(deaths)


def _generation_time(context: MetricContext) -> float | None:
    value = _metadata_number(context, "generation_time_seconds")
    return float(value) if value is not None else None


def _repair_count(context: MetricContext) -> int:
    actions = context.record.get("repair", {}).get("actions", [])
    return len(actions) if isinstance(actions, list) else 0


def _constraint_violation_count(context: MetricContext) -> int:
    before = context.record.get("validation_before_repair", {})
    errors = before.get("errors", []) if isinstance(before, dict) else []
    return len(errors) if isinstance(errors, list) else 0


def _generator_method_label(context: MetricContext) -> str | None:
    value = context.record.get("generator") or context.experiment.get("generator")
    return str(value) if value is not None else None


def _genome_representation_type(context: MetricContext) -> str | None:
    canonical_map = context.canonical_map
    if canonical_map is None:
        return None
    value = canonical_map.metadata.get("genome_representation_type")
    return str(value) if value is not None else None


def _overall_map_quality(context: MetricContext) -> float | None:
    value = context.record.get("fitness_value")
    return float(value) if _is_number(value) else None


def _controllability_score(context: MetricContext) -> float | None:
    targets = context.experiment.get("generator_settings", {}).get("control_targets", {})
    if isinstance(targets, dict) is False or len(targets) == 0:
        return None
    scores: list[float] = []
    for raw_name, specification in targets.items():
        name = normalize_metric_name(raw_name)
        if name not in MAP_NUMERIC_METRIC_NAMES or isinstance(specification, dict) is False:
            continue
        target = specification.get("target")
        tolerance = specification.get("tolerance")
        value = calculate_metrics(context.match_records, [name], context).get(name)
        if (
            _is_number(target)
            and _is_number(tolerance)
            and float(tolerance) > 0
            and _is_number(value)
        ):
            error = abs(float(value) - float(target))
            scores.append(max(0.0, 1.0 - error / float(tolerance)))
    return mean(scores) if scores else None


def _population_map_diversity(context: PopulationMetricContext) -> float | None:
    """Mean pairwise tile Hamming distance inside the population.

    Duplicate population members are preserved and contribute a distance of zero,
    which correctly lowers diversity when the population contains clones.
    """

    maps = [item.canonical_map for item in context.population_contexts if item.canonical_map is not None]
    if len(maps) == 0:
        return None
    if len(maps) == 1:
        return 0.0
    distances: list[float] = []
    for index, first in enumerate(maps[:-1]):
        for second in maps[index + 1:]:
            if first.width != second.width or first.height != second.height:
                continue
            differences = sum(
                left != right
                for first_row, second_row in zip(first.grid, second.grid)
                for left, right in zip(first_row, second_row)
            )
            distances.append(differences / (first.width * first.height))
    return mean(distances) if distances else None


def _population_expressive_range(context: PopulationMetricContext) -> float | None:
    settings = context.experiment.get("analysis_settings", {})
    dimensions = [
        normalize_metric_name(value)
        for value in settings.get(
            "expressive_range_metrics",
            ["walkable_area_ratio", "pace"],
        )
    ]
    if len(dimensions) != 2 or any(name not in MAP_NUMERIC_METRIC_NAMES for name in dimensions):
        return None

    points: list[tuple[float, float]] = []
    for item in context.population_contexts:
        first = calculate_metrics(item.match_records, [dimensions[0]], item).get(dimensions[0])
        second = calculate_metrics(item.match_records, [dimensions[1]], item).get(dimensions[1])
        if _is_number(first) and _is_number(second):
            points.append((float(first), float(second)))
    if len(points) == 0:
        return None
    if len(points) == 1:
        return 0.0

    first_values = [point[0] for point in points]
    second_values = [point[1] for point in points]
    first_range = max(first_values) - min(first_values)
    second_range = max(second_values) - min(second_values)
    if first_range == 0 or second_range == 0:
        return 0.0

    bins = max(1, int(settings.get("expressive_range_bins", 10)))
    occupied = {
        (
            min(bins - 1, int((first - min(first_values)) / first_range * bins)),
            min(bins - 1, int((second - min(second_values)) / second_range * bins)),
        )
        for first, second in points
    }
    return len(occupied) / (bins * bins)


def _population_counts(context: PopulationMetricContext) -> tuple[int, int, int]:
    records = [item.record for item in context.evaluated_contexts]
    generated = len(records)
    valid = sum(bool(record.get("valid")) for record in records)
    return generated, valid, generated - valid


def _population_generator_success_rate(context: PopulationMetricContext) -> float | None:
    generated, valid, _ = _population_counts(context)
    return valid / generated if generated else None


def _population_generator_efficiency(context: PopulationMetricContext) -> float | None:
    times = [_generation_time(item) for item in context.evaluated_contexts]
    available = [value for value in times if value is not None]
    if len(available) == 0 or len(available) != len(context.evaluated_contexts):
        return None
    total_time = sum(available)
    if total_time <= 0:
        return None
    valid = sum(bool(item.record.get("valid")) for item in context.evaluated_contexts)
    return valid / total_time


def _population_overall_generator_score(context: PopulationMetricContext) -> float | None:
    qualities = [_overall_map_quality(item) for item in context.population_contexts]
    available_qualities = [value for value in qualities if value is not None]
    if len(available_qualities) == 0:
        return None

    quality = mean(available_qualities)
    success = _population_generator_success_rate(context)
    diversity = _population_map_diversity(context)
    weights = context.experiment.get("analysis_settings", {}).get(
        "overall_generator_score_weights",
        {"quality": 0.5, "success_rate": 0.3, "diversity": 0.2},
    )
    quality_weight = float(weights.get("quality", 0.5))
    success_weight = float(weights.get("success_rate", 0.3))
    diversity_weight = float(weights.get("diversity", 0.2))
    total = quality_weight + success_weight + diversity_weight
    if total <= 0:
        return None
    return (
        quality_weight * quality
        + success_weight * (success if success is not None else 0.0)
        + diversity_weight * (diversity if diversity is not None else 0.0)
    ) / total


def _population_generated_map_count(context: PopulationMetricContext) -> int:
    return _population_counts(context)[0]


def _population_valid_map_count(context: PopulationMetricContext) -> int:
    return _population_counts(context)[1]


def _population_invalid_map_count(context: PopulationMetricContext) -> int:
    return _population_counts(context)[2]


def _mean_numeric(match_records: list[dict[str, Any]], key: str) -> float | None:
    values = [
        float(record[key])
        for record in match_records
        if _is_number(record.get(key))
    ]
    return mean(values) if values else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and isinstance(value, bool) is False and math.isfinite(float(value))


def _read_decimal_comma_rows(path: Path, expected_values: int) -> list[tuple[float, ...]]:
    rows: list[tuple[float, ...]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        text = line.strip()
        if text == "":
            continue
        parts = [part.strip() for part in text.replace(";", ",").split(",")]
        try:
            if len(parts) == expected_values:
                values = tuple(float(part) for part in parts)
            elif len(parts) == expected_values * 2:
                values = tuple(
                    float(f"{parts[index * 2]}.{parts[index * 2 + 1]}")
                    for index in range(expected_values)
                )
            else:
                continue
        except ValueError:
            continue
        rows.append(values)
    return rows


def _direct_unity(key: str) -> MetricFunction:
    return lambda context: _mean_unity(context, key)


_METRIC_FUNCTIONS: dict[str, MetricFunction] = {
    "map_width": _map_width,
    "map_height": _map_height,
    "total_tile_count": _total_tile_count,
    "walkable_tile_count": _walkable_tile_count,
    "wall_tile_count": _wall_tile_count,
    "room_count": lambda context: _metadata_number(context, "room_count"),
    "corridor_count": lambda context: _metadata_number(context, "corridor_count"),
    "spawn_count": lambda context: _symbol_count(context, SPAWN),
    "pickup_count": lambda context: (
        (_symbol_count(context, HEALTH) or 0) + (_symbol_count(context, AMMO) or 0)
        if context.canonical_map else None
    ),
    "walkable_area_ratio": _walkable_area_ratio,
    "largest_navigable_region_ratio": _largest_region_ratio,
    "connectivity": _connectivity,
    "number_of_connected_components": _component_count,
    "symmetry_x": lambda context: _symmetry(context, "x"),
    "symmetry_y": lambda context: _symmetry(context, "y"),
    "max_symmetry": lambda context: max(
        value for value in (_symmetry(context, "x"), _symmetry(context, "y")) if value is not None
    ) if context.canonical_map else None,
    "average_eccentricity": _average_eccentricity,
    "graph_diameter": _graph_diameter,
    "graph_radius": _graph_radius,
    "graph_density": _graph_density,
    "degree_centrality": _degree_centrality,
    "closeness_centrality": _closeness_centrality,
    "betweenness_centrality": _betweenness_centrality,
    "chokepoint_count": _chokepoint_count,
    "loop_count": _loop_count,
    "alternative_path_count": _alternative_path_count,
    "average_visibility": _average_visibility,
    "maximum_visibility": _maximum_visibility,
    "visibility_local_maxima_count": _visibility_local_maxima_count,
    "maximum_sightline_length": _maximum_sightline_length,
    "spawn_distance_balance": _spawn_distance_balance,
    "spawn_exposure": _spawn_exposure,
    "spawn_escape_routes": _spawn_escape_routes,
    "number_of_frags_bot_1": _direct_unity("numberOfFrags1"),
    "number_of_frags_bot_2": _direct_unity("numberOfFrags2"),
    "number_of_shots_bot_1": _direct_unity("numberOfShots1"),
    "number_of_shots_bot_2": _direct_unity("numberOfShots2"),
    "number_of_hits_bot_1": _direct_unity("numberOfHits1"),
    "number_of_hits_bot_2": _direct_unity("numberOfHits2"),
    "accuracy_bot_1": lambda context: _pooled_accuracy(
        context, "numberOfHits1", "numberOfShots1", "accuracy1"
    ),
    "accuracy_bot_2": lambda context: _pooled_accuracy(
        context, "numberOfHits2", "numberOfShots2", "accuracy2"
    ),
    "number_of_fights_bot_1": _direct_unity("numberOfFights1"),
    "number_of_fights_bot_2": _direct_unity("numberOfFights2"),
    "time_in_fight_bot_1": _direct_unity("timeInFight1"),
    "time_in_fight_bot_2": _direct_unity("timeInFight2"),
    "time_to_engage_bot_1": _direct_unity("timeToEngage1"),
    "time_to_engage_bot_2": _direct_unity("timeToEngage2"),
    "number_of_sights_bot_1": _direct_unity("numberOfSights1"),
    "number_of_sights_bot_2": _direct_unity("numberOfSights2"),
    "time_between_sights_bot_1": _direct_unity("timeBetweenSights1"),
    "time_between_sights_bot_2": _direct_unity("timeBetweenSights2"),
    "number_of_retreats_bot_1": _direct_unity("numberOfRetreats1"),
    "number_of_retreats_bot_2": _direct_unity("numberOfRetreats2"),
    "time_to_surrender_bot_1": _direct_unity("timeToSurrender1"),
    "time_to_surrender_bot_2": _direct_unity("timeToSurrender2"),
    "number_of_suicides_bot_1": _direct_unity("numberOfSuicides1"),
    "number_of_suicides_bot_2": _direct_unity("numberOfSuicides2"),
    "kill_streak_average_bot_1": _direct_unity("killStreakAverage1"),
    "kill_streak_average_bot_2": _direct_unity("killStreakAverage2"),
    "kill_streak_max_bot_1": lambda context: _maximum_unity(context, "killStreakMax1"),
    "kill_streak_max_bot_2": lambda context: _maximum_unity(context, "killStreakMax2"),
    "entropy": _direct_unity("entropy"),
    "pace": _direct_unity("pace"),
    "fight_time": _direct_unity("fightTime"),
    "pursue_time": _direct_unity("pursueTime"),
    "sight_loss_rate": _direct_unity("sightLossRate"),
    "target_loss_rate": _direct_unity("targetLossRate"),
    "kill_difference": _kill_difference,
    "kill_ratio": _kill_ratio,
    "movement_position_count_bot_1": lambda context: _raw_count(
        context, "position_*_bot1.csv", context.positions(1)
    ),
    "movement_position_count_bot_2": lambda context: _raw_count(
        context, "position_*_bot2.csv", context.positions(2)
    ),
    "movement_heatmap_coverage": _movement_heatmap_coverage,
    "area_dominance": _area_dominance,
    "death_position_count_bot_1": lambda context: _raw_count(
        context, "death_positions_*_bot1.csv", context.death_positions(1)
    ),
    "death_position_count_bot_2": lambda context: _raw_count(
        context, "death_positions_*_bot2.csv", context.death_positions(2)
    ),
    "death_hotspot_concentration": _death_hotspot_concentration,
    "kill_distance_count": lambda context: _raw_count(
        context, "kill_distances_*_bot*.csv", context.kill_distances()
    ),
    "average_combat_distance": _average_combat_distance,
    "combat_distance_distribution": _combat_distance_distribution,
    "spawn_death_rate": _spawn_death_rate,
    "controllability_score": _controllability_score,
    "overall_map_quality_score": _overall_map_quality,
    "generation_time_per_map": _generation_time,
    "repair_count": _repair_count,
    "constraint_violation_count": _constraint_violation_count,
    "generator_method_label": _generator_method_label,
    "genome_representation_type": _genome_representation_type,
}


_POPULATION_METRIC_FUNCTIONS: dict[str, Callable[[PopulationMetricContext], MetricValue]] = {
    "map_diversity": _population_map_diversity,
    "expressive_range": _population_expressive_range,
    "generator_success_rate": _population_generator_success_rate,
    "generator_efficiency": _population_generator_efficiency,
    "overall_generator_score": _population_overall_generator_score,
    "generated_map_count": _population_generated_map_count,
    "valid_map_count": _population_valid_map_count,
    "invalid_map_count": _population_invalid_map_count,
}
