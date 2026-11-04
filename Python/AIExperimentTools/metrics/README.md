# Metric names

Common thesis names and their related keys in [metric_calculator.py](metric_calculator.py).
Use the code keys in experiment configs and result files.

| Thesis name | Code key |
|---|---|
| Kill balance entropy (KBE) | `entropy` |
| Pace (PAC) | `pace` |
| Geometric diversity (GDI) | `map_diversity` |
| Unique map ratio (UMR) | `unique_map_ratio` |
| Walkable area ratio (WAR) | `walkable_area_ratio` |
| Largest navigable region ratio (LNR) | `largest_navigable_region_ratio` |
| Layout symmetry (SYM) | `symmetry_x`, `symmetry_y`; `max_symmetry` takes their maximum, not their mean |
| Movement coverage (MCV) | `movement_heatmap_coverage` |
| Kill distance (KDI) | `average_combat_distance` |
| Visible-area fraction (VIS) | `average_visibility` (eight-ray approximation) |
