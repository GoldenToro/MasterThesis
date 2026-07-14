from __future__ import annotations

from pathlib import Path
from typing import Any


def create_plots(records: list[dict[str, Any]], output_dir: Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    scores = [record.get("fitness", {}).get("score") for record in records]
    scores = [float(score) for score in scores if isinstance(score, (int, float))]
    if scores:
        figure, axis = plt.subplots()
        axis.hist(scores)
        axis.set_xlabel("Fitness score")
        axis.set_ylabel("Map count")
        axis.set_title("Fitness distribution")
        path = output_dir / "fitness_distribution.png"
        figure.savefig(path, bbox_inches="tight")
        plt.close(figure)
        created.append(path)

    entropy = []
    pace = []
    for record in records:
        simulation = record.get("simulation_metrics", {})
        if isinstance(simulation.get("entropy"), (int, float)) and isinstance(simulation.get("pace"), (int, float)):
            entropy.append(float(simulation["entropy"]))
            pace.append(float(simulation["pace"]))
    if entropy:
        figure, axis = plt.subplots()
        axis.scatter(entropy, pace)
        axis.set_xlabel("Entropy")
        axis.set_ylabel("Pace")
        axis.set_title("Entropy and pace")
        path = output_dir / "entropy_pace.png"
        figure.savefig(path, bbox_inches="tight")
        plt.close(figure)
        created.append(path)

    return created


def render_grid(grid: list[str] | tuple[str, ...], path: Path, title: str = "Map") -> Path | None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return None

    values = np.array([[0 if symbol == "#" else 1 for symbol in row] for row in grid])
    figure, axis = plt.subplots()
    axis.imshow(values, interpolation="nearest")
    axis.set_title(title)
    axis.set_axis_off()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path
