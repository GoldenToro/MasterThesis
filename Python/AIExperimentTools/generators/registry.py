from __future__ import annotations

import importlib
import colorsys
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experiment_session import ExperimentSession

GeneratorRunner = Callable[["ExperimentSession"], list[str]]

_GENERATORS: dict[str, tuple[str, str]] = {
    "manual": (
        "generators.manual.manual_generator",
        "run",
    ),
    "llm_map_creator": (
        "generators.llm_based.llm_map_creator.llm_map_creator",
        "run",
    ),
    "nsga2": (
        "generators.search_based.nsga2.nsga2_generator",
        "run",
    ),
    "random_digger": (
        "generators.constructive.random_digger.random_digger_generator",
        "run",
    ),
    "cellular_automata": (
        "generators.constructive.cellular_automata.cellular_automata_generator",
        "run",
    ),
    "divisive": (
        "generators.constructive.divisive.divisive_generator",
        "run",
    ),
    "grid_graph": (
        "generators.constructive.grid_graph.grid_graph_generator",
        "run",
    ),
    "fps_pattern": (
        "generators.constructive.fps_pattern.fps_pattern_generator",
        "run",
    ),
    "all_black": (
        "generators.constructive.all_black.all_black_generator",
        "run",
    ),
    "map_elites": (
        "generators.search_based.map_elites.map_elites_generator",
        "run",
    ),
    "template_hybrid": (
        "generators.llm_based.template_hybrid.template_hybrid_generator",
        "run",
    ),
}

_ALIASES: dict[str, str] = {
    "digger": "random_digger",
    "cellular": "cellular_automata",
    "bsp": "divisive",
    "binary_space_partition": "divisive",
    "grid_graph_room": "grid_graph",
    "fps_pattern_rule": "fps_pattern",
    "all_black_constructive": "all_black",
}

# Shared plotting palette: each family has a hue, each generator its own shade.
GENERATOR_FAMILY_COLORS = {
    "constructive": "#D97706",
    "llm_based": "#2474B5",
    "search_based": "#2E7D32",
    "manual": "#808080",
}
GENERATOR_COLORS = {
    "random_digger": "#9A4D0B",
    "cellular_automata": "#D97706",
    "divisive": "#E68A18",
    "grid_graph": "#ED9C35",
    "fps_pattern": "#B8600A",
    "all_black": "#F2B45B",
    "llm_map_creator": "#2474B5",
    "template_hybrid": "#57A5D0",
    "nsga2": "#2E7D32",
    "map_elites": "#66A64A",
    "manual": "#808080",
}

def generator_family(name: str) -> str:
    """Return the registered family, accepting generator aliases."""
    canonical = _ALIASES.get(name, name)
    module = _GENERATORS.get(canonical, ("", ""))[0]
    return module.split(".")[1] if "." in module else "manual"


def generator_color(name: str, variant: int = 0, variants: int = 1) -> str:
    """Return the registry color, with distinct shades for config variants."""
    canonical = _ALIASES.get(name, name)
    if canonical in GENERATOR_COLORS:
        color = GENERATOR_COLORS[canonical]
    else:
        color = GENERATOR_FAMILY_COLORS.get(generator_family(name), GENERATOR_FAMILY_COLORS["manual"])
    if variants <= 1:
        return color
    rgb = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, _, saturation = colorsys.rgb_to_hls(*rgb)
    lightness = 0.25 + 0.4 * variant / (variants - 1)
    rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb)


def available_generators() -> tuple[str, ...]:
    """Return canonical generator names registered in this toolkit."""
    return tuple(sorted(_GENERATORS))


def load_generator(name: str) -> GeneratorRunner:
    """Load and return the registered generator entry function."""
    if name not in _GENERATORS:
        supported = ", ".join(available_generators())
        raise ValueError(
            f"Unknown generator '{name}'. Supported generators: {supported}"
        )

    module_name, function_name = _GENERATORS[name]
    module = importlib.import_module(module_name)
    run_function = getattr(module, function_name, None)
    if callable(run_function) is False:
        raise ValueError(
            f"Registered generator '{name}' must expose "
            f"{module_name}.{function_name}(base_generator)."
        )
    return run_function
