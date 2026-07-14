from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generators.base_generator import GeneratorContext
from map_schema.map_validator import MapValidator
from simulation.unity_map_converter import canonical_to_area_genome


class FrameworkTest(unittest.TestCase):
    def test_rule_based_map_and_converter(self):
        settings = json.loads((ROOT / "generators/rule_based/rule_based_default.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            context = GeneratorContext(
                experiment_name="test",
                map_width=32,
                map_height=32,
                num_epochs=1,
                population_size=4,
                seed=7,
                output_dir=Path(temp),
                framework_root=ROOT,
                technical_settings={},
                experiment={},
            )
            canonical_map = RuleBasedGenerator(settings).generate_maps(context)[0]
            report = MapValidator(
                {
                    "minimum_spawn_count": 2,
                    "minimum_walkable_ratio": 0.05,
                    "maximum_walkable_ratio": 0.90,
                    "require_single_connected_region": True,
                }
            ).validate(canonical_map)
            self.assertTrue(report.valid, report.errors)
            genome = canonical_to_area_genome(canonical_map)
            self.assertEqual(genome["width"], 32)
            self.assertGreater(len(genome["areas"]), 0)

            from map_schema.canonical_map import CanonicalMap, WALKABLE_SYMBOLS
            reconstructed = CanonicalMap.from_area_rectangles(
                map_id="reconstructed",
                width=genome["width"],
                height=genome["height"],
                areas=genome["areas"],
            )
            original_mask = [
                symbol in WALKABLE_SYMBOLS
                for row in canonical_map.grid
                for symbol in row
            ]
            reconstructed_mask = [
                symbol in WALKABLE_SYMBOLS
                for row in reconstructed.grid
                for symbol in row
            ]
            self.assertEqual(original_mask, reconstructed_mask)


if __name__ == "__main__":
    unittest.main()
