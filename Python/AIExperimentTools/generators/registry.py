from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from generators.base_generator import BaseGenerator


GeneratorRunner = Callable[["BaseGenerator"], list[str]]


_GENERATORS: dict[str, tuple[str, str]] = {
    "nsga2": (
        "generators.nsga2.nsga2_generator",
        "run",
    ),
}


def available_generators() -> tuple[str, ...]:
    """Return all generator names registered in this toolkit."""
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
