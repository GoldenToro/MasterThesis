# Analysis metrics, scope, and viability

`analysis_settings.calculate_metric` and `create_diagram_for_metric` use the snake_case keys below. `calculate_all_metrics: true` calculates every key exposed by `metrics/metric_calculator.py`.

Metrics now have two explicit scopes:

- **Individual-map metrics** are written to `results.csv` and each `*.result.json`. They describe one generated map, with Unity values aggregated across that map's matches.
- **Population/generator metrics** are written once per epoch to `results_by_epoch.csv` and once for the complete run in `export/analysis_summary.json`. They are no longer repeated on every map row.

`results_by_epoch.csv` uses the full selected NSGA-II population from `checkpoint_summary.json`, including carried-over individuals and duplicates. For generators without a population checkpoint, it uses the maps evaluated in that epoch. Numeric individual metrics are summarized with count, mean, minimum, maximum, population standard deviation, and a best value when an optimization goal is configured.

## Diagram design

Epoch diagrams use a mixed view:

- every evaluated map as a faint point
- epoch average as the main line
- epoch minimum and maximum as a shaded range
- epoch best as a dashed line when the metric has a configured fitness goal

This keeps the population spread visible while giving a readable trend line.

## Static and topology metrics

| Nr. | Metric key | Viability | Definition / requirement |
|---:|---|---|---|
| 9 | `map_width`, `map_height` | Implemented | Canonical map dimensions. |
| 10 | `total_tile_count` | Implemented | Width multiplied by height. |
| 11 | `walkable_tile_count` | Implemented | All symbols except `#`. |
| 12 | `wall_tile_count` | Implemented | Number of `#` tiles. |
| 13 | `room_count` | Conditional | Read from generator metadata. The NSGA-II adapter now records it. Other generators should add the same metadata key. |
| 14 | `corridor_count` | Conditional | Read from generator metadata. The NSGA-II adapter now records it. |
| 15 | `spawn_count` | Implemented | Number of `S` markers. |
| 16 | `cover_object_count` | Implemented | Number of `C` markers. Maps without explicit cover markers return 0. |
| 17 | `pickup_count` | Implemented | Number of `H` and `A` markers. |
| 18 | `walkable_area_ratio` | Implemented | Walkable tiles divided by all tiles. |
| 19 | `largest_navigable_region_ratio` | Implemented | Largest four-neighbour component divided by all walkable tiles. |
| 20 | `connectivity` | Implemented | Fraction of all walkable tile pairs that are mutually reachable. |
| 21 | `number_of_connected_components` | Implemented | Four-neighbour walkable components. |
| 22 | `symmetry_x` | Implemented | Left/right equality of the binary wall/walkable grid. |
| 23 | `symmetry_y` | Implemented | Top/bottom equality of the binary wall/walkable grid. |
| 24 | `max_symmetry` | Implemented | Maximum of X and Y symmetry. |
| 25 | `average_eccentricity` | Implemented | Mean node eccentricity in the largest component. |
| 26 | `graph_diameter` | Implemented | Maximum eccentricity in the largest component. |
| 27 | `graph_radius` | Implemented | Minimum eccentricity in the largest component. |
| 28 | `graph_density` | Implemented | NetworkX density of the largest component. |
| 29 | `degree_centrality` | Implemented | Mean degree centrality in the largest component. |
| 30 | `closeness_centrality` | Implemented | Mean closeness centrality in the largest component. |
| 31 | `betweenness_centrality` | Approximate | Mean normalized betweenness, sampled with up to 100 deterministic source nodes for runtime control. |
| 32 | `chokepoint_count` | Implemented | Articulation points in the largest component. |
| 33 | `loop_count` | Implemented | Independent cycle rank `E - V + C`. |
| 34 | `alternative_path_count` | Implemented proxy | Number of biconnected regions containing at least three nodes. |
| 35 | `average_visibility` | Implemented approximation | Mean normalized visible-tile count using eight-direction ray casting. |
| 36 | `maximum_visibility` | Implemented approximation | Highest normalized eight-direction visibility. |
| 37 | `visibility_local_maxima_count` | Implemented approximation | Four-neighbour local maxima of the visibility score. |
| 38 | `maximum_sightline_length` | Implemented approximation | Longest unobstructed eight-direction ray in tile units. |
| 39 | `spawn_distance_balance` | Implemented | Balance between each spawn's average shortest-path distance to the map. 1 means equal accessibility. |
| 40 | `spawn_exposure` | Implemented approximation | Mean visibility score at spawn tiles. |
| 41 | `spawn_escape_routes` | Implemented | Mean number of walkable cardinal exits from spawns, normalized by four. |
| 42 | `cover_density` | Implemented | Cover markers divided by walkable tiles. |
| 43 | `cover_distribution_balance` | Implemented | Normalized Shannon entropy of covers across four map quadrants. |

## Unity and log-derived metrics

| Nr. | Metric key | Viability | Definition / requirement |
|---:|---|---|---|
| 44 | `number_of_frags_bot_1`, `number_of_frags_bot_2` | Implemented | Mean Unity output across matches. |
| 45 | `number_of_shots_bot_1`, `number_of_shots_bot_2` | Implemented | Mean Unity output. |
| 46 | `number_of_hits_bot_1`, `number_of_hits_bot_2` | Implemented | Mean Unity output. |
| 47 | `accuracy_bot_1`, `accuracy_bot_2` | Implemented | Pooled hits divided by pooled shots across the map's matches, with Unity accuracy as fallback. |
| 48 | `number_of_fights_bot_1`, `number_of_fights_bot_2` | Implemented | Mean Unity output. |
| 49 | `time_in_fight_bot_1`, `time_in_fight_bot_2` | Implemented | Mean Unity output. |
| 50 | `time_to_engage_bot_1`, `time_to_engage_bot_2` | Implemented | Mean Unity output. |
| 51 | `number_of_sights_bot_1`, `number_of_sights_bot_2` | Implemented | Mean Unity output. |
| 52 | `time_between_sights_bot_1`, `time_between_sights_bot_2` | Implemented | Mean Unity output. |
| 53 | `number_of_retreats_bot_1`, `number_of_retreats_bot_2` | Implemented | Mean Unity output. |
| 54 | `time_to_surrender_bot_1`, `time_to_surrender_bot_2` | Implemented | Mean Unity output. |
| 55 | `number_of_suicides_bot_1`, `number_of_suicides_bot_2` | Implemented | Mean Unity output. |
| 56 | `kill_streak_average_bot_1`, `kill_streak_average_bot_2` | Implemented | Mean Unity output. |
| 57 | `kill_streak_max_bot_1`, `kill_streak_max_bot_2` | Implemented | Maximum observed kill-streak maximum across the map's matches. |
| 58 | `entropy` | Implemented | Mean Unity output. |
| 59 | `pace` | Implemented | Mean Unity output. |
| 60 | `fight_time` | Implemented | Mean Unity output. |
| 61 | `pursue_time` | Implemented | Mean Unity output. |
| 62 | `sight_loss_rate` | Implemented | Mean Unity output. |
| 63 | `target_loss_rate` | Implemented | Mean Unity output. |
| 64 | `kill_difference` | Implemented | Mean absolute frag difference. |
| 65 | `kill_ratio` | Implemented | Mean lower-frag count divided by higher-frag count, range 0 to 1. |
| 66 | `movement_position_count_bot_1`, `movement_position_count_bot_2` | Implemented summary | Raw positions remain in Unity CSV files; results.csv stores row counts. |
| 67 | `movement_heatmap_coverage` | Implemented | Unique walkable cells visited by either bot divided by all walkable cells. Requires position logging. |
| 68 | `area_dominance` | Implemented proxy | Absolute difference in unique cells visited by the bots divided by their combined coverage. |
| 69 | `death_position_count_bot_1`, `death_position_count_bot_2` | Implemented summary | Raw death positions remain in Unity CSV files; results.csv stores row counts. |
| 70 | `death_hotspot_concentration` | Implemented | Largest death-cell count divided by all logged deaths. |
| 71 | `kill_distance_count` | Implemented summary | Raw distances remain in Unity CSV files; results.csv stores the count. |
| 72 | `average_combat_distance` | Implemented | Mean logged kill distance. |
| 73 | `combat_distance_distribution` | Implemented, non-scalar | JSON object with close, medium and long ratios plus standard deviation. Default thresholds are 15 and 35 world units. |
| 74 | `spawn_death_rate` | Implemented proxy | Fraction of deaths within a configurable radius of any spawn. Default radius is three tiles. Death logs contain positions rather than timestamps, so this is spatial. |

Missing raw Unity log files now produce an unavailable value rather than a misleading zero. An existing but empty log file still produces a count of zero.

## Generator and aggregate metrics

| Nr. | Metric key | Viability | Definition / requirement |
|---:|---|---|---|
| 1 | `generated_map_count` | Implemented epoch metric | Number of maps newly evaluated in the epoch. |
| 2 | `valid_map_count` | Implemented epoch metric | Number of valid maps newly evaluated in the epoch. |
| 3 | `invalid_map_count` | Implemented epoch metric | Number of invalid maps newly evaluated in the epoch. |
| 4 | `generation_time_per_map` | Conditional | Read from map metadata. The NSGA-II adapter now measures phenotype-to-canonical-map time. Other generators should record `generation_time_seconds`. |
| 5 | `repair_count` | Implemented | Number of repair actions recorded for the map. |
| 6 | `constraint_violation_count` | Implemented | Validation errors before repair. |
| 7 | `generator_method_label` | Implemented | Generator name. |
| 8 | `genome_representation_type` | Conditional | Read from map metadata. NSGA-II now records `all_black`. |
| 75 | `map_diversity` | Implemented population metric | Mean pairwise normalized tile-wise Hamming distance inside the epoch population. Duplicate individuals lower the score. |
| 76 | `expressive_range` | Implemented population metric | Occupied-bin ratio in a configurable 10x10 feature space. Defaults to `walkable_area_ratio` and `pace`. |
| 77 | `generator_success_rate` | Implemented epoch metric | Valid newly evaluated maps divided by newly evaluated maps in the epoch. |
| 78 | `generator_efficiency` | Conditional epoch metric | Valid newly evaluated maps per second of summed generation time in the epoch. Requires timing for every evaluated map. |
| 79 | `controllability_score` | Conditional | Available when `generator_settings.control_targets` defines target and tolerance values. |
| 80 | `overall_map_quality_score` | Implemented | Current configured normalized fitness value. |
| 81 | `overall_generator_score` | Implemented population metric | Configurable weighted mean of population mean quality, epoch success rate, and population diversity. Defaults: 0.5, 0.3, 0.2. |

## Optional settings used by advanced metrics

```json
{
  "analysis_settings": {
    "combat_distance_thresholds": [15.0, 35.0],
    "spawn_death_radius_tiles": 3.0,
    "expressive_range_metrics": ["walkable_area_ratio", "pace"],
    "expressive_range_bins": 10,
    "overall_generator_score_weights": {
      "quality": 0.5,
      "success_rate": 0.3,
      "diversity": 0.2
    }
  },
  "generator_settings": {
    "control_targets": {
      "walkable_area_ratio": {"target": 0.3, "tolerance": 0.1}
    }
  }
}
```