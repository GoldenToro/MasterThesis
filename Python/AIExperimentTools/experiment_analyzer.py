"""Plot selected metrics for every experiment in a results folder.

Usage: python experiment_analyzer.py results/2026-10-16_23-40-37
Outputs go to <results folder>/experiment_analysis (or --output).
Saved map metrics are reused; missing values and population metrics are calculated
with the metrics package. Original experiment files are never rewritten.
"""
from __future__ import annotations

# These are time/cost limits are
# keep them fixed across compared experiments.
generation_time_max_seconds = 480.0
generation_cost_max_usd = 0.10

score_metrics = [
    {
        "name": "gameplay",
        "label": "Gameplay",
        "weight": 1.0,
        # Equal weights; fewer zero-kill matches is better.
        "components": [
            ("entropy", 0.0, 1.0, False, 1.0),
            ("pace", 0.0, 1.0, False, 1.0),
            ("zero_kill_match_frequency", 0.0, 1.0, True, 1.0),
        ],
    },
    {
        "name": "performance_consistency",
        "label": "Consistency",
        "weight": 1.0,
        # Across repeated runs: 1 - 2 * max(population SD of the other axes).
        # At least two runs with all other axis scores are required.
        "components": [],
    },
    {
        "name": "production_efficiency",
        "label": "Efficiency",
        "weight": 1.0,
        "components": [
            ("generation_time_per_output_map", 0.0, generation_time_max_seconds, True, 0.5),
            ("generation_cost_per_output_map", 0.0, generation_cost_max_usd, True, 0.5),
        ],
    },
    {
        "name": "reliability",
        "label": "Reliability",
        "weight": 1.0,
        # Per evaluated candidate: clean valid = 1, corrected valid = .5, invalid = 0.
        "components": [("generator_reliability", 0.0, 1.0, False, 1.0)],
    },
    {
        "name": "diversity",
        "label": "Diversity",
        "weight": 1.0,
        "components": [
            ("map_diversity", 0.0, 1.0, False, 1.0),
            ("expressive_range", 0.0, 1.0, False, 1.0),
            ("unique_map_ratio", 0.0, 1.0, False, 1.0),
        ],
    },
]
average_multiple_runs = True
create_overview = True
# Raw metric values over epochs; separate from the normalized score axes.
# Each tuple is (package metric name, plot label).
epoch_metrics = [
    ("entropy", "Combat balance (entropy)"),
    ("pace", "Pace"),
    ("map_diversity", "Map diversity"),
]
show_epoch_maximum = False  # Horizontal observed maximum per config, across its runs/epochs.
do_map_visualization = True
do_graph_visualization = False  # True: four graph views per unique selected map.
movement_log_scale = True  # False uses linear movement heatmaps.
death_log_scale = False  # False uses linear death heatmaps.
bottom_padding = 0.65  # Inches below each radar chart.
chart_size = 5.2
image_dpi = 160

from analysis.experiment_comparison import ExperimentComparison


def main(argv=None):
    ExperimentComparison(
        score_metrics=score_metrics,
        epoch_metrics=epoch_metrics,
        average_multiple_runs=average_multiple_runs,
        create_overview=create_overview,
        show_epoch_maximum=show_epoch_maximum,
        do_map_visualization=do_map_visualization,
        do_graph_visualization=do_graph_visualization,
        movement_log_scale=movement_log_scale,
        death_log_scale=death_log_scale,
        bottom_padding=bottom_padding,
        chart_size=chart_size,
        image_dpi=image_dpi,
    ).run(argv)


if __name__ == "__main__":
    main()
