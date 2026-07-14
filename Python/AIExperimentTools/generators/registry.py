from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from generators.base_generator import BaseGenerator


_GENERATORS = {
    "rule_based": (
        "generators.rule_based.rule_based_generator",
        "RuleBasedGenerator",
        "generators/rule_based/rule_based_default.json",
    ),
    "nsga2": (
        "generators.nsga2.nsga2_generator",
        "NSGA2Generator",
        "generators/nsga2/nsga2_default.json",
    ),
    "llm": (
        "generators.llm.llm_generator",
        "LLMImportGenerator",
        "generators/llm/llm_default.json",
    ),
    "hybrid": (
        "generators.hybrid.hybrid_generator",
        "HybridGenerator",
        "generators/hybrid/hybrid_default.json",
    ),
}


def available_generators() -> tuple[str, ...]:
    return tuple(sorted(_GENERATORS))


def load_generator(
    name: str,
    framework_root: Path,
    overrides: dict[str, Any] | None = None,
) -> tuple[BaseGenerator, dict[str, Any]]:
    if name not in _GENERATORS:
        supported = ", ".join(available_generators())
        raise ValueError(f"Unknown generator '{name}'. Supported generators: {supported}")

    module_name, class_name, default_path = _GENERATORS[name]
    with (framework_root / default_path).open("r", encoding="utf-8") as handle:
        defaults = json.load(handle)

    resolved = _deep_merge(defaults, overrides or {})

    module = __import__(module_name, fromlist=[class_name])
    generator_class = getattr(module, class_name)
    return generator_class(resolved), resolved


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
