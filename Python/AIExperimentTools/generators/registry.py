from __future__ import annotations

import importlib
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
