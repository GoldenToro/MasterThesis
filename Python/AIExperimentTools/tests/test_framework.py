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

from analysis.experiment_analyzer import ExperimentAnalyzer
from experiment_manager import ExperimentManager
from generators.base_generator import BaseGenerator
from generators.manual.manual_generator import load_text_map
from generators.registry import available_generators, resolve_generator_name
from map_schema.canonical_map import CanonicalMap
from metrics.metric_calculator import MetricContext, calculate_metrics


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



    def test_pooled_accuracy_and_maximum_kill_streak(self):
        metrics = calculate_metrics(
            [
                {
                    "numberOfHits1": 1,
                    "numberOfShots1": 2,
                    "accuracy1": 0.5,
                    "killStreakMax1": 2,
                },
                {
                    "numberOfHits1": 9,
                    "numberOfShots1": 18,
                    "accuracy1": 0.5,
                    "killStreakMax1": 5,
                },
            ],
            ["accuracy_bot_1", "kill_streak_max_bot_1"],
        )
        self.assertAlmostEqual(metrics["accuracy_bot_1"], 0.5)
        self.assertEqual(metrics["kill_streak_max_bot_1"], 5.0)

    def test_missing_raw_logs_are_unavailable(self):
        grid = (
            "####",
            "#S.#",
            "#.S#",
            "####",
        )
        context = MetricContext(
            canonical_map=CanonicalMap("map", 4, 4, grid),
            raw_map_dir=Path("/path/that/does/not/exist"),
        )
        metrics = calculate_metrics(
            [],
            [
                "movement_position_count_bot_1",
                "movement_heatmap_coverage",
                "death_position_count_bot_1",
                "kill_distance_count",
            ],
            context,
        )
        self.assertIsNone(metrics["movement_position_count_bot_1"])
        self.assertIsNone(metrics["movement_heatmap_coverage"])
        self.assertIsNone(metrics["death_position_count_bot_1"])
        self.assertIsNone(metrics["kill_distance_count"])

    def test_population_metrics_are_written_by_epoch(self):
        map_zero = CanonicalMap(
            "map_0",
            5,
            5,
            (
                "#####",
                "#S..#",
                "#...#",
                "#..S#",
                "#####",
            ),
            metadata={"generation_time_seconds": 1.0},
        )
        map_one = CanonicalMap(
            "map_1",
            5,
            5,
            (
                "#####",
                "#S#.#",
                "#...#",
                "#..S#",
                "#####",
            ),
            metadata={"generation_time_seconds": 2.0},
        )
        experiment = {
            "experiment_name": "scope_test",
            "generator": "fake",
            "generator_settings": {
                "fitness": {
                    "metrics": [{"name": "entropy", "goal": "maximize"}]
                }
            },
            "analysis_settings": {
                "enabled": True,
                "calculate_all_metrics": False,
                "calculate_metric": [
                    "walkable_area_ratio",
                    "map_diversity",
                    "generated_map_count",
                    "valid_map_count",
                ],
                "create_diagram_fitness": False,
                "create_diagram_for_metric": [],
            },
        }

        def record(epoch, numeric_id, map_id):
            return {
                "experiment": "scope_test",
                "generator": "fake",
                "epoch": epoch,
                "id": numeric_id,
                "map_id": map_id,
                "valid": True,
                "status": "simulation_disabled",
                "simulations_requested": 0,
                "simulations_successful": 0,
                "simulations_failed": 0,
                "match_count": 0,
                "metrics": {"entropy": 0.0},
                "fitness_value": 0.0,
                "final_candidate": True,
                "repair": {"actions": []},
                "validation_before_repair": {"errors": []},
            }

        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            epoch_zero = run_dir / "epoch_0000"
            epoch_one = run_dir / "epoch_0001"
            epoch_zero.mkdir()
            epoch_one.mkdir()
            for epoch_dir, canonical_map, payload in (
                (epoch_zero, map_zero, record(0, 0, "map_0")),
                (epoch_one, map_one, record(1, 0, "map_1")),
            ):
                (epoch_dir / f"{canonical_map.map_id}.map.json").write_text(
                    json.dumps(canonical_map.to_dict()), encoding="utf-8"
                )
                (epoch_dir / f"{canonical_map.map_id}.result.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            (epoch_zero / "checkpoint_summary.json").write_text(
                json.dumps({"epoch": 0, "selected_map_ids": ["map_0"]}),
                encoding="utf-8",
            )
            (epoch_one / "checkpoint_summary.json").write_text(
                json.dumps(
                    {"epoch": 1, "selected_map_ids": ["map_0", "map_1"]}
                ),
                encoding="utf-8",
            )
            (run_dir / "results.csv").write_text("", encoding="utf-8")

            summary = ExperimentAnalyzer(run_dir, experiment).run()
            self.assertIn("map_diversity", summary["metric_scopes"]["population_or_generator"])
            with (run_dir / "results.csv").open(
                "r", newline="", encoding="utf-8"
            ) as handle:
                individual_rows = list(csv.DictReader(handle, delimiter=";"))
            self.assertNotIn("map_diversity", individual_rows[0])
            self.assertIn("walkable_area_ratio", individual_rows[0])

            with (run_dir / "results_by_epoch.csv").open(
                "r", newline="", encoding="utf-8"
            ) as handle:
                epoch_rows = list(csv.DictReader(handle, delimiter=";"))
            self.assertEqual(len(epoch_rows), 2)
            self.assertEqual(epoch_rows[1]["population_size"], "2")
            self.assertEqual(epoch_rows[1]["newly_evaluated_count"], "1")
            self.assertEqual(epoch_rows[1]["generated_map_count"], "1")
            self.assertNotEqual(epoch_rows[1]["map_diversity"], "")
            self.assertIn("walkable_area_ratio_mean", epoch_rows[1])

    def test_static_analysis_enriches_results_csv(self):
        grid = (
            "######",
            "#S...#",
            "#....#",
            "#....#",
            "#...S#",
            "######",
        )
        canonical_map = CanonicalMap("map_0", 6, 6, grid)
        experiment = {
            "experiment_name": "analysis_test",
            "generator": "fake",
            "generator_settings": {
                "fitness": {
                    "metrics": [
                        {"name": "entropy", "goal": "maximize"}
                    ]
                }
            },
            "analysis_settings": {
                "enabled": True,
                "calculate_all_metrics": False,
                "calculate_metric": [
                    "walkable_area_ratio",
                    "connectivity",
                    "spawn_count",
                ],
                "create_diagram_fitness": False,
                "create_diagram_for_metric": [],
            },
        }
        record = {
            "experiment": "analysis_test",
            "generator": "fake",
            "epoch": 0,
            "id": 0,
            "map_id": "map_0",
            "valid": True,
            "status": "simulation_disabled",
            "simulations_requested": 0,
            "simulations_successful": 0,
            "simulations_failed": 0,
            "match_count": 0,
            "metrics": {"entropy": 0.0},
            "fitness_value": 0.0,
            "final_candidate": True,
            "repair": {"actions": []},
            "validation_before_repair": {"errors": []},
        }

        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            epoch_dir = run_dir / "epoch_0000"
            epoch_dir.mkdir()
            (epoch_dir / "map_0.map.json").write_text(
                json.dumps(canonical_map.to_dict()),
                encoding="utf-8",
            )
            (epoch_dir / "map_0.result.json").write_text(
                json.dumps(record),
                encoding="utf-8",
            )
            (run_dir / "results.csv").write_text("", encoding="utf-8")

            summary = ExperimentAnalyzer(run_dir, experiment).run()
            self.assertEqual(summary["record_count"], 1)
            payload = json.loads(
                (epoch_dir / "map_0.result.json").read_text(encoding="utf-8")
            )
            self.assertAlmostEqual(payload["metrics"]["walkable_area_ratio"], 16 / 36)
            self.assertEqual(payload["metrics"]["connectivity"], 1.0)
            self.assertEqual(payload["metrics"]["spawn_count"], 2)
            self.assertTrue((run_dir / "export" / "analysis_summary.json").is_file())

    def test_final_candidate_unity_maps_are_copied_to_export(self):
        experiment = {
            "experiment_name": "copy_test",
            "generator": "fake",
            "seed": 7,
            "generator_settings": {
                "copy_final_candidate_maps": True,
                "fitness": {
                    "metrics": [{"name": "entropy", "goal": "maximize"}]
                },
            },
            "simulator_settings": {"enabled": False},
        }

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            epoch_dir = output / "epoch_0002"
            epoch_dir.mkdir()
            source = epoch_dir / "candidate_a.unity.json"
            payload = {"experiment_name": "candidate_a", "map": {"id": "a"}}
            source.write_text(json.dumps(payload), encoding="utf-8")

            base = BaseGenerator(ROOT, output, {}, experiment)
            copied = base.copy_final_candidate_maps(
                ["candidate_a", "candidate_a", "missing_candidate"]
            )

            self.assertEqual(len(copied), 1)
            destination = output / "export" / "candidate_a.unity.json"
            self.assertTrue(destination.is_file())
            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                payload,
            )
            self.assertTrue(source.is_file())

    def test_fps_pattern_selects_values_from_configured_ranges(self):
        import random

        from generators.constructive.fps_pattern_generator import _generate

        settings = {
            "route_count_min": 2,
            "route_count_max": 5,
            "corridor_width_min": 1,
            "corridor_width_max": 3,
        }
        generated = [
            _generate(64, 64, random.Random(seed), settings, f"fps_{seed}")
            for seed in range(10)
        ]

        self.assertTrue(
            all(2 <= item.metadata["route_count"] <= 5 for item in generated)
        )
        self.assertTrue(
            all(1 <= item.metadata["corridor_width"] <= 3 for item in generated)
        )
        self.assertGreater(len({item.grid for item in generated}), 1)

    def test_constructive_generators_create_valid_epoch_zero_populations(self):
        generator_names = [
            "random_digger",
            "cellular_automata",
            "divisive",
            "grid_graph",
            "fps_pattern",
            "all_black",
        ]
        technical = {"execution": {"max_parallel_map_evaluations": 1}}

        for generator_name in generator_names:
            with self.subTest(generator=generator_name):
                experiment = {
                    "experiment_name": generator_name,
                    "generator": generator_name,
                    "seed": 17,
                    "only_keep_result_summary": False,
                    "generator_settings": {
                        "population_size": 2,
                        "map_width": 32,
                        "map_height": 24,
                        "repair_enabled": True,
                        "copy_final_candidate_maps": False,
                        "validation": {
                            "minimum_spawn_count": 2,
                            "minimum_walkable_ratio": 0.05,
                            "maximum_walkable_ratio": 1.0,
                            "require_single_connected_region": True,
                        },
                        "fitness": {
                            "metrics": [
                                {
                                    "name": "walkable_area_ratio",
                                    "goal": "maximize",
                                }
                            ]
                        },
                    },
                    "simulator_settings": {"enabled": False},
                }

                with tempfile.TemporaryDirectory() as temp:
                    framework_root = Path(temp)
                    output = framework_root / "results"
                    output.mkdir()
                    base = BaseGenerator(
                        framework_root,
                        output,
                        technical,
                        experiment,
                    )
                    final_ids = base.start()
                    self.assertEqual(len(final_ids), 2)
                    with (output / "results.csv").open(
                        "r", newline="", encoding="utf-8"
                    ) as handle:
                        rows = list(csv.DictReader(handle, delimiter=";"))
                    self.assertEqual(len(rows), 2)
                    self.assertTrue(all(row["valid"] == "true" for row in rows))
                    checkpoint = json.loads(
                        (output / "epoch_0000" / "checkpoint_summary.json")
                        .read_text(encoding="utf-8")
                    )
                    self.assertEqual(checkpoint["selected_map_ids"], final_ids)
                    map_payload = json.loads(
                        next((output / "epoch_0000").glob("*.map.json"))
                        .read_text(encoding="utf-8")
                    )
                    self.assertIn(
                        "generation_time_seconds",
                        map_payload["metadata"],
                    )
                    self.assertIn(
                        "genome_representation_type",
                        map_payload["metadata"],
                    )

    def test_constructive_generator_aliases(self):
        self.assertEqual(resolve_generator_name("bsp"), "divisive")
        self.assertEqual(
            resolve_generator_name("all_black_constructive"),
            "all_black",
        )

    def test_manual_generator_loads_and_evaluates_text_maps(self):
        experiment = {
            "experiment_name": "manual",
            "generator": "manual",
            "seed": 7,
            "only_keep_result_summary": False,
            "generator_settings": {
                "repair_enabled": True,
                "copy_final_candidate_maps": False,
                "validation": {
                    "minimum_spawn_count": 2,
                    "minimum_walkable_ratio": 0.08,
                    "maximum_walkable_ratio": 1.0,
                    "require_single_connected_region": True,
                },
                "fitness": {
                    "metrics": [
                        {
                            "name": "walkable_area_ratio",
                            "goal": "maximize",
                        }
                    ]
                },
            },
            "simulator_settings": {"enabled": False},
        }
        technical = {
            "paths": {"manual_maps_root": "manual_maps"},
            "execution": {"max_parallel_map_evaluations": 1},
        }

        with tempfile.TemporaryDirectory() as temp:
            framework_root = Path(temp)
            maps_dir = framework_root / "manual_maps" / "manual"
            maps_dir.mkdir(parents=True)
            (maps_dir / "needs repair.txt").write_text(
                "#####\n#...#\n#...#\n#...#\n#####\n",
                encoding="utf-8",
            )
            (maps_dir / "ready.txt").write_text(
                "#####\n#S..#\n#...#\n#..S#\n#####\n",
                encoding="utf-8",
            )
            output = framework_root / "results"
            output.mkdir()

            base = BaseGenerator(framework_root, output, technical, experiment)
            final_ids = base.start()

            self.assertEqual(
                final_ids,
                ["manual_needs_repair", "manual_ready"],
            )
            self.assertIn("manual", available_generators())
            with (output / "results.csv").open(
                "r", newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle, delimiter=";"))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["valid"] == "true" for row in rows))
            repaired = json.loads(
                (output / "epoch_0000" / "manual_needs_repair.result.json")
                .read_text(encoding="utf-8")
            )
            self.assertTrue(repaired["repair"]["changed"])
            checkpoint = json.loads(
                (output / "epoch_0000" / "checkpoint_summary.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(checkpoint["selected_map_ids"], final_ids)

    def test_manual_text_map_rejects_non_rectangular_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.txt"
            path.write_text("####\n#..#\n###\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row 3 has width"):
                load_text_map(path)

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
