from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiment_manager import ExperimentManager
from generators.base_generator import BaseGenerator
from map_schema.canonical_map import CanonicalMap
from metrics.metric_calculator import calculate_metrics


class FrameworkTest(unittest.TestCase):
    def test_seed_resolution(self):
        self.assertGreater(ExperimentManager._resolve_seed(None), 0)
        self.assertGreater(ExperimentManager._resolve_seed(""), 0)
        self.assertGreater(ExperimentManager._resolve_seed(-1), 0)
        self.assertEqual(ExperimentManager._resolve_seed(123), 123)

    def test_metric_averages(self):
        metrics = calculate_metrics(
            [
                {"entropy": 0.2, "pace": 0.4},
                {"entropy": 0.6, "pace": 0.8},
            ],
            ["entropy", "pace"],
        )
        self.assertAlmostEqual(metrics["entropy"], 0.4)
        self.assertAlmostEqual(metrics["pace"], 0.6)

    def test_epoch_results_are_sorted_and_numpy_friendly(self):
        experiment = {
            "experiment_name": "test",
            "generator": "fake",
            "seed": 7,
            "only_keep_result_summary": False,
            "generator_settings": {
                "num_epochs": 0,
                "population_size": 4,
                "map_width": 8,
                "map_height": 8,
                "repair_enabled": False,
                "validation": {
                    "minimum_spawn_count": 2,
                    "minimum_walkable_ratio": 0.05,
                    "maximum_walkable_ratio": 0.95,
                    "require_single_connected_region": True,
                },
                "fitness": {
                    "metrics": [
                        {
                            "name": "entropy",
                            "weight": 0.75,
                            "goal": "maximize",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        {
                            "name": "pace",
                            "weight": 0.25,
                            "goal": "maximize",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                    ]
                },
            },
            "simulator_settings": {"enabled": False},
        }
        technical = {
            "execution": {"max_parallel_map_evaluations": 2},
        }
        grid = (
            "########",
            "#S.....#",
            "#......#",
            "#......#",
            "#......#",
            "#......#",
            "#.....S#",
            "########",
        )
        maps = [
            CanonicalMap("map_b", 8, 8, grid),
            CanonicalMap("map_a", 8, 8, grid),
        ]

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            base = BaseGenerator(ROOT, output, technical, experiment)
            epoch_dir = base.save_epoch_maps(3, maps)
            table = base.evaluate_epoch(epoch_dir)

            self.assertEqual(list(table["id"]), [0, 1])
            self.assertEqual(list(table["map_id"]), ["map_b", "map_a"])
            self.assertEqual(list(table["entropy"]), [0.0, 0.0])
            self.assertEqual(list(table["fitness_value"]), [0.0, 0.0])

            with (output / "results.csv").open(
                "r", newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle, delimiter=";"))
            self.assertEqual([int(row["id"]) for row in rows], [0, 1])
            self.assertEqual(rows[0]["status"], "simulation_disabled")
            self.assertTrue((epoch_dir / "map_b.result.json").is_file())


if __name__ == "__main__":
    unittest.main()
