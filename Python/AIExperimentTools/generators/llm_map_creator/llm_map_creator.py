from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from experiment_session import ExperimentSession
from generators.llm_map_creator.grok_client import GrokMapCreator, MapResponseResult
from generators.llm_map_creator.map_processing import DirectMapProcessor
from generators.llm_map_creator.schemas import DirectCanonicalMapResponse
from map_schema.canonical_map import CanonicalMap
from map_schema.map_validator import MapValidator
from candidate import Candidate

LOGGER = logging.getLogger("FPS-EVALUATOR")


def run(base_generator: ExperimentSession) -> list[str]:
    """Generate complete canonical grid maps directly with Grok."""
    settings = base_generator.generator_settings
    map_count = int(settings.get("map_count", 4))
    width = int(settings.get("map_width", 48))
    height = int(settings.get("map_height", 48))
    if map_count < 1 or map_count > 32:
        raise ValueError("llm_map_creator map_count must be between 1 and 32")

    validation_settings = dict(settings.get("validation", {}))
    minimum_ratio = float(validation_settings.get("minimum_walkable_ratio", 0.0))
    maximum_ratio = float(validation_settings.get("maximum_walkable_ratio", 1.0))
    if minimum_ratio > maximum_ratio:
        raise ValueError("minimum_walkable_ratio must be at most maximum_walkable_ratio")

    rules_text = str(
        settings.get(
            "rules_text",
            "Create a balanced competitive FPS map with clear routes, "
            "distant spawns, one contested center, and at least one flank.",
        )
    ).strip()
    if rules_text == "":
        raise ValueError("generator_settings.rules_text requires text")

    examples = _load_examples(base_generator)
    creator = GrokMapCreator(dict(settings.get("grok", {})))
    processor = DirectMapProcessor(width, height, validation_settings)
    validator = MapValidator(validation_settings)
    maximum_attempts = max(1, min(5, int(settings.get("max_attempts_per_map", 2))))
    repair_enabled = bool(settings.get("repair_enabled", True))
    minimum_spawn_count = int(validation_settings.get("minimum_spawn_count", 2))

    generated_maps: list[CanonicalMap] = []
    generation_summary: list[dict[str, Any]] = []
    for map_index in range(map_count):
        desired_map_id = f"llm_map_{map_index:04d}"
        feedback: dict[str, Any] | None = None
        accepted_map: CanonicalMap | None = None
        accepted_attempt = 0
        attempt_summaries: list[dict[str, Any]] = []
        attempts = maximum_attempts

        for attempt in range(1, attempts + 1):
            assert creator is not None
            response_result = creator.create_map(
                rules_text=rules_text,
                map_id=desired_map_id,
                map_index=map_index,
                map_count=map_count,
                width=width,
                height=height,
                seed=base_generator.seed + map_index,
                validation=validation_settings,
                examples=examples,
                attempt=attempt,
                feedback=feedback,
            )

            metadata = {
                "generator": "llm_map_creator",
                "llm_provider": "xai",
                "llm_model": response_result.model,
                "llm_response_id": response_result.response_id,
                "llm_attempt": attempt,
                "llm_usage": response_result.usage,
                "rules_text": rules_text,
            }
            canonical_map, normalization = processor.normalize(
                response_result.response,
                map_id=desired_map_id,
                metadata=metadata,
            )
            validation_before = validator.validate(canonical_map)

            repair_actions: list[str] = []
            if repair_enabled:
                canonical_map, repair = processor.repair(
                    canonical_map,
                    minimum_spawn_count=minimum_spawn_count,
                )
                repair_actions = repair.actions
            combined_actions = normalization.actions + repair_actions
            if combined_actions:
                canonical_map = canonical_map.replace_grid(
                    canonical_map.grid,
                    {"generation_repair_actions": combined_actions},
                )
            validation_after = validator.validate(canonical_map)

            attempt_payload = {
                "map_index": map_index,
                "attempt": attempt,
                "provider": "xai",
                "model": response_result.model,
                "response_id": response_result.response_id,
                "usage": response_result.usage,
                "response": response_result.response.model_dump(mode="json"),
                "normalization_actions": normalization.actions,
                "validation_before_repair": validation_before.to_dict(),
                "repair_actions": repair_actions,
                "validation_after_repair": validation_after.to_dict(),
            }
            _save_attempt(base_generator, desired_map_id, attempt, attempt_payload)
            attempt_summaries.append(
                {
                    "attempt": attempt,
                    "response_id": response_result.response_id,
                    "valid": validation_after.valid,
                    "normalization_action_count": len(normalization.actions),
                    "repair_action_count": len(repair_actions),
                    "errors": validation_after.errors,
                }
            )

            accepted_map = canonical_map
            accepted_attempt = attempt
            if validation_after.valid:
                break

            feedback = {
                "validation_errors": validation_after.errors,
                "validation_warnings": validation_after.warnings,
                "measured": validation_after.measured,
                "previous_candidate": response_result.response.model_dump(mode="json"),
            }

        assert accepted_map is not None
        final_metadata = dict(accepted_map.metadata)
        final_metadata.update(
            {
                "llm_accepted_attempt": accepted_attempt,
                "llm_valid_after_generation": validator.validate(accepted_map).valid,
                "llm_attempt_count": len(attempt_summaries),
            }
        )
        accepted_map = CanonicalMap(
            map_id=accepted_map.map_id,
            width=accepted_map.width,
            height=accepted_map.height,
            grid=accepted_map.grid,
            metadata=final_metadata,
            schema_version=accepted_map.schema_version,
        )
        generated_maps.append(accepted_map)
        generation_summary.append(
            {
                "map_id": desired_map_id,
                "accepted_attempt": accepted_attempt,
                "valid": validator.validate(accepted_map).valid,
                "attempts": attempt_summaries,
            }
        )

    summary_path = base_generator.output_dir / "llm_map_generation.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generator": "llm_map_creator",
                "provider": "xai",
                "map_count": map_count,
                "width": width,
                "height": height,
                "rules_text": rules_text,
                "examples_used": len(examples),
                "maps": generation_summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    LOGGER.info("Created %s complete canonical maps with direct LLM output.", map_count)
    LOGGER.info(
        "Created %s complete canonical maps with direct LLM output.",
        map_count,
    )

    candidates = [
        Candidate(canonical_map=item)
        for item in generated_maps
    ]
    evaluated = base_generator.evaluate_candidates(candidates, epoch=0)
    final_map_ids = [
        candidate.map_id
        for candidate in evaluated
    ]

    epoch_dir = base_generator.output_dir / "epoch_0000"
    (epoch_dir / "checkpoint_summary.json").write_text(
        json.dumps(
            {
                "epoch": 0,
                "population_size": len(final_map_ids),
                "selected_map_ids": final_map_ids,
                "source": "llm_map_creator",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return final_map_ids


def _load_examples(base_generator: ExperimentSession) -> list[dict[str, Any]]:
    settings = base_generator.generator_settings
    examples: list[dict[str, Any]] = []
    inline = settings.get("examples", [])
    if isinstance(inline, list):
        examples.extend(dict(value) for value in inline if isinstance(value, dict))

    paths = settings.get("example_map_paths", [])
    if isinstance(paths, str):
        paths = [paths]
    for value in paths:
        path = _resolve_path(base_generator, value)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("maps"), list):
            examples.extend(dict(item) for item in payload["maps"])
        elif isinstance(payload, dict):
            examples.append(dict(payload))

    maximum_examples = max(0, int(settings.get("max_prompt_examples", 2)))
    return examples[:maximum_examples]

def _save_attempt(
    base_generator: ExperimentSession,
    map_id: str,
    attempt: int,
    payload: dict[str, Any],
) -> Path:
    directory = base_generator.output_dir / "llm_map_attempts"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{map_id}_attempt_{attempt:02d}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _resolve_path(base_generator: ExperimentSession, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute() is False:
        path = base_generator.framework_root / path
    if path.is_file() is False:
        raise FileNotFoundError(path)
    return path
