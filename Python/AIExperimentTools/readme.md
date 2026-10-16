# Thesis Framework

This folder adds a Python-side experiment framework while leaving the existing Unity project and `AIExperimentTools` unchanged.

## Implemented flow

Generator implementations are grouped under `generators/constructive`,
`generators/search_based` (NSGA-II and MAP-Elites), `generators/llm_based`,
and `generators/manual`. Experiment JSON generator names are unchanged.
The LLM `response_parser.py` converts provider responses and attaches metadata;
`CanonicalMap` checks grid shape, and `MapValidator` owns shared dimension,
symbol, and gameplay checks.

```text
experiment JSON
  -> ExperimentManager
  -> generator
  -> canonical grid map JSON
  -> validation and optional repair
  -> static metric extraction
  -> conversion to Project Arena AreaGenome JSON
  -> Unity command-line simulation
  -> Unity JSON/CSV extraction
  -> simulation metrics and fitness score
  -> ranked CSV, JSON summary, plots
```

The framework currently provides:

- A complete rule-based generator.
- An NSGA-II adapter that reuses the legacy All-Black genome implementation from `AIExperimentTools` while routing evaluation through the new pipeline.
- An LLM import adapter for canonical map JSON files produced outside this repository.
- A simple hybrid adapter that combines imported layouts with rule-based repair and decoration.
- A canonical grid representation, validator, repairer, and Project Arena AreaGenome converter.
- Static metrics, simulation metric aggregation, diversity metrics, scoring, and reporting.

## Important current Unity limitation

The existing Unity `AreaGenomeMapGenerator` accepts rectangles describing walkable areas. It does not receive canonical object markers such as cover, pickups, or exact spawn positions. The Python converter therefore preserves the exact walkable layout but treats every non-wall grid symbol as walkable when creating the AreaGenome file.

The canonical JSON remains the authoritative thesis representation. A later Unity-side canonical grid loader is required to transport exact cover, pickup, and spawn markers into the simulation.

## Setup

1. Copy `thesis_framework` into the repository's `Python` folder so it sits next to `AIExperimentTools`.
2. Edit `configs/settings.json` and set `unity.build_path` and `unity.working_directory`.
3. Keep the bot JSON files in `configs/Bots`.
4. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run one experiment

```powershell
cd Python/thesis_framework
python experiment_manager.py --config experiments/rule_based_test.json
```

## Run every experiment JSON

```powershell
python experiment_manager.py
```

The manager scans `experiments/*.json` in filename order.

To repeat a configuration, add `"no_of_experiments": 2` beside
`experiment_name` and `generator`. Both single-file and folder commands run
the requested number of repetitions. This overrides `generator_settings.seed`
with `-1` (a fresh random seed for each run) and names the run folders
`<experiment_name>_1`, `<experiment_name>_2`, etc. The resolved random seed is
saved in `experiment_evaluated.json`. Omit the field to keep the existing
single-run behavior. Python callers can use `run_experiments()` for repetitions;
`run_config()` still executes one run.

## Static-only smoke test

```powershell
python experiment_manager.py --config experiments/rule_based_static_test.json
```

This creates maps, validation reports, static metrics, rankings, and figures without starting Unity.

## Output layout

```text
results/<experiment_name>/<timestamp>/
  experiment.json
  resolved_experiment.json
  _raw/
  _maps/
  _unity_exports/
  _metrics/
  _figures/
```

`experiment.json` is the unchanged source configuration. `resolved_experiment.json` contains generator defaults, experiment overrides, technical settings, timestamps, and run status.

For the direct LLM generator, set `generator_settings.concurrent_requests` to the
maximum number of simultaneous map requests (default: `1`). For example, `10`
runs up to ten maps concurrently using a thread pool. Each map's repair attempts
remain sequential, and results are collected in map order. The production deadline
prevents new attempts from starting; requests already in flight finish or time out.

The direct LLM generator saves each attempt under `_raw/llm/`, using names such as
`llm_map_0000_attempt_01.prompt.txt`, `.request.json`, and `.response.json`.
These contain the exact prompt text, the SDK's outgoing JSON body (including the
output schema), and the provider's response body before parsing. Headers and API
keys are not recorded. A request that receives no response has no response file.
As with other raw output, these files are removed when
`analysis_settings.only_keep_result_summary` is enabled.

## Configuration priority

```text
generator default JSON
  < experiment.generator_settings
```

Technical settings such as the Unity executable path remain in `configs/settings.json`.

## Canonical symbols

| Symbol | Meaning |
|---|---|
| `#` | wall |
| `.` | walkable floor |
| `S` | spawn marker on walkable floor |
| `C` | cover marker on walkable floor |
| `H` | health pickup marker |
| `A` | ammunition pickup marker |

All symbols except `#` are treated as walkable by the current Python topology analysis and AreaGenome converter.
