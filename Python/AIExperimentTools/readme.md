# AIExperimentTools

Generate FPS maps, validate them, run Unity simulations, and compare generators.

## Setup

Run commands from `Python/AIExperimentTools` with your Python environment active:

```powershell
python -m pip install -r requirements.txt
```

Set `unity.EXPERIMENT_RUNNER_PATH` (build folder) and
`unity.EXPERIMENT_RUNNER_FILE` (executable) in `configs/settings.json`.
Bot configurations live in `configs/Bots`. LLM generators also need an API key
through `XAI_API_KEY` or the provider settings.

## Run experiments

```powershell
python experiment_manager.py experiments/example/fps_pattern_example.json
python experiment_manager.py experiments/tests_for_proposal_5
```

A folder runs its JSON files in filename order, without searching subfolders.
Omit the path to use the configured experiments folder. `--config` is an
alternative to the positional path. Add `--dry-run` to skip Unity; generation
and file writing still run, including any LLM requests.

Useful experiment settings:

- `no_of_experiments`: repetitions with a fresh random seed each time. Run folders
  get `_1`, `_2`, etc.; `experiment_evaluated.json` records the resolved seed.
  Omit this setting for one run using the configured seed.
- `generator_settings`: generator parameters. `final_map_count` limits final
  selection; increasing it does not automatically generate more candidates.
- `simulator_settings.bot_matches`: named bot pairs. Each pair runs
  `matches_per_simulation` matches per simulation, alternating starting positions.
  This match count must be positive and even.
- `analysis_settings.enabled`: enables per-run analysis exports.
- `analysis_settings.calculate_metric`: metrics to export; use
  `calculate_all_metrics: true` for all metrics.
- `analysis_settings.only_keep_result_summary`: removes raw logs when enabled.
  Keep it `false` if you need movement and death heatmaps later.

Generators are grouped in `generators/`:

| Type | Names |
|---|---|
| Constructive | `random_digger`, `cellular_automata`, `divisive`, `grid_graph`, `fps_pattern`, `all_black` |
| Search based | `nsga2`, `map_elites` |
| LLM based | `llm_map_creator`, `template_hybrid` |
| Manual | `manual` |

Canonical maps use `#` for walls, `.` for floor, `S` for spawns, `H` for health,
and `A` for ammo. All except walls are walkable. The Unity loader reads these
layout and object markers.

## Results

```text
results/<timestamp>/
  <experiment_name>[_<repetition>]/
    experiment.json              original configuration
    experiment_evaluated.json    resolved configuration and run metadata
    epoch_XXXX/                  maps and candidate results
    _raw/                        simulation and LLM logs
    results.csv
    results_by_epoch.csv
    export/                      per-run summaries and plots
  experiment_analysis/           comparisons across runs
```

The manager runs the comparison analyzer after the batch finishes.
`analysis/experiment_postprocessor.py` handles the individual run's exports;
`experiment_analyzer.py` controls comparisons across runs.

## Compare saved runs

```powershell
python experiment_analyzer.py results/<timestamp>
```

Outputs go to `experiment_analysis/`, or the folder given by `--output`.
The analyzer uses the saved final map selection and does not rewrite experiment
results. Duplicate final slots still contribute to metrics, even when omitted
from map images.

Edit the settings at the top of `experiment_analyzer.py`:

| Setting | Purpose |
|---|---|
| `score_metrics` | Score components, normalization limits and weights |
| `average_multiple_runs` | Combine repetitions of the same configuration |
| `create_overview` | Write the star overview |
| `epoch_metrics` | Write a separate epoch plot for each selected metric |
| `show_epoch_maximum` | Add a horizontal maximum line per configuration |
| `do_map_visualization` | Show maps, movement, deaths and visibility |
| `movement_log_scale`, `death_log_scale` | Switch heatmaps between log and linear scales |
| `do_graph_visualization` | Export four diagnostic graph views per unique final map; off by default |

The star currenty shows Gameplay, Consistency, Efficiency, Reliability and Diversity,
clockwise from the top. This can be easily edited in the top of experiment_analyzer.py and rerun without si


## Export selected maps

```powershell
python visualize_maps.py first.unity.json second.unity.json
python visualize_maps.py --mode movement --mode deaths --mode visibility --output figures first.unity.json second.unity.json
```

Canonical `.map.json` files also work. Maps appear in argument order, one per
row, with the basic map first and requested views to its right. Repeated inputs
are kept. Movement and deaths need the map's original sibling raw logs; basic
maps and visibility also work with standalone files.

Use `--horizontal` for maps across columns, `--hide-objects` to display pickups
and spawns as floor, and `--dpi` to change the default 300 DPI. PNGs go to
`--output` or the current folder. Repeating the same export options replaces
that PNG. Each heatmap view shares a scale across the supplied maps.

Optional analyzer graph views show region outlines, tiles, regions, and regions
with game elements. Regions are rectangles derived from floor runs, not inferred
rooms. The tile view uses eight neighbours; spatial metrics still use four.
