# Project Arena Thesis

Generate FPS maps and compare them using spatial metrics and simulated bot matches.

- [AIExperimentTools](Python/AIExperimentTools/readme.md): Python generators, experiment configs, metrics and analysis. Includes setup and usage instructions.
- [Project Arena](Unity/Project%20Arena/): Unity simulation for bot matches and gameplay logging. Uses Unity **2021.3.45f2**.

Build the Unity simulation, then follow the Python README to install dependencies
and configure the Unity executable in `Python/AIExperimentTools/configs/settings.json`.

Run an example from the repository root:

```powershell
cd Python/AIExperimentTools
python experiment_manager.py experiments/example/fps_pattern_example.json
```

Results, saved maps, logs and comparison plots are written to
`Python/AIExperimentTools/results/<timestamp>/`.
