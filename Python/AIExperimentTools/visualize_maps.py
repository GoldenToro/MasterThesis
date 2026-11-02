"""Arrange selected maps in a PNG, using the experiment analysis style.

Usage: python visualize_maps.py [--horizontal] [--mode movement] [--output folder] map1.unity.json map2.unity.json
Repeat --mode to include multiple heatmaps. The basic map is always included.
Maps are stacked vertically by default; --horizontal places them left to right.
Use --hide-objects to draw spawn, health, and ammo tiles as ordinary floor.
"""
import argparse
import json
import sys
from pathlib import Path

from analysis.map_visualizer import draw_generator
from map_schema.canonical_map import ALLOWED_SYMBOLS, CanonicalMap
from metrics.metric_calculator import MetricContext


MODES = {"basic": 0, "movement": 1, "deaths": 2, "visibility": 3}


def load_context(path):
    """Read the requested map and locate its sibling experiment logs, if present."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    map_data = payload.get("map", payload)
    canonical_map = CanonicalMap.from_dict(map_data)
    if "map_scale" in map_data:
        canonical_map = canonical_map.replace_grid(
            canonical_map.grid, {"map_scale": map_data["map_scale"]},
        )
    unknown = set("".join(canonical_map.grid)) - ALLOWED_SYMBOLS
    if unknown:
        raise ValueError(f"Unsupported map symbols: {', '.join(sorted(unknown))}")
    result_path = path.parent / f"{canonical_map.map_id}.result.json"
    record = json.loads(result_path.read_text(encoding="utf-8-sig")) if result_path.is_file() else {}
    record["map_id"] = canonical_map.map_id
    return MetricContext(
        canonical_map=canonical_map,
        record=record,
        raw_map_dir=path.parent.parent / "_raw" / path.parent.name / canonical_map.map_id,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", nargs="+", type=Path, help="Unity or canonical map JSON files, in display order")
    parser.add_argument(
        "--mode", choices=MODES, action="append", default=[],
        help="Additional view; repeat for multiple modes. Basic is always included.",
    )
    parser.add_argument("--output", type=Path, default=Path.cwd(), help="Output folder (default: current folder)")
    parser.add_argument(
        "--horizontal", action="store_true",
        help="Arrange maps left to right, with modes top to bottom and basic first.",
    )
    parser.add_argument(
        "--hide-objects", action="store_true",
        help="Draw spawns, health, and ammo as floor and omit them from the legend.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG resolution (default: 300 DPI)")
    args = parser.parse_args(argv)
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    modes = list(dict.fromkeys(["basic", *args.mode]))
    maps = []
    for path in args.maps:
        try:
            context = load_context(path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            parser.error(f"Cannot load {path}: {error}")
        maps.append(("", context))
        for mode, prefix in (("movement", "position"), ("deaths", "death_positions")):
            if mode in modes and not any(context.raw_files(f"{prefix}_*_bot{bot}.csv") for bot in (1, 2)):
                print(f"Warning: {path.name}: {mode} logs unavailable in {context.raw_map_dir}", file=sys.stderr)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        args.output.mkdir(parents=True, exist_ok=True)
        output = draw_generator(
            plt, "selected", maps, args.output, args.dpi,
            death_log_scale=False, color="#263238", title="Selected maps",
            plot_name="_".join(modes) + ("_horizontal" if args.horizontal else "")
                      + ("_no_objects" if args.hide_objects else ""),
            columns=tuple(MODES[mode] for mode in modes),
            deduplicate=False, horizontal=args.horizontal, hide_objects=args.hide_objects,
        )
    except OSError as error:
        parser.error(f"Cannot write PNG to {args.output}: {error}")
    print(output.resolve())
    return output


if __name__ == "__main__":
    main()
