# Thesis Framework

This folder adds a Python-side experiment framework while leaving the existing Unity project and `AIExperimentTools` unchanged.

## Implemented flow

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
