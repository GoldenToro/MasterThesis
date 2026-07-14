from __future__ import annotations


from typing import Any


def calculate_score(
    static_metrics: dict[str, Any],
    simulation_metrics: dict[str, Any],
    fitness_config: dict[str, Any],
    valid: bool,
) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    weighted_sum = 0.0
    available_weight = 0.0

    for specification in fitness_config.get("metrics", []):
        name = str(specification["name"])
        value = simulation_metrics.get(name, static_metrics.get(name))
        if isinstance(value, (int, float)) is False:
            components.append({"name": name, "available": False})
            continue

        minimum = float(specification.get("minimum", 0.0))
        maximum = float(specification.get("maximum", 1.0))
        weight = float(specification.get("weight", 1.0))
        goal = str(specification.get("goal", "maximize"))
        normalized = _normalize(float(value), minimum, maximum)
        if goal == "minimize":
            normalized = 1.0 - normalized
        elif goal != "maximize":
            raise ValueError(f"Unsupported fitness goal '{goal}' for metric '{name}'")

        weighted_sum += weight * normalized
        available_weight += weight
        components.append(
            {
                "name": name,
                "available": True,
                "raw_value": float(value),
                "normalized_value": normalized,
                "weight": weight,
                "goal": goal,
            }
        )

    score = weighted_sum / available_weight if available_weight else None
    if valid is False and score is not None:
        score = 0.0
    return {
        "score": score,
        "validity_gate_applied": valid is False,
        "components": components,
    }


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        raise ValueError("Fitness maximum must be greater than minimum")
    return min(1.0, max(0.0, (value - minimum) / (maximum - minimum)))
