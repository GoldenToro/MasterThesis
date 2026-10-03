from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from experiment_session import ExperimentSession
from generators.llm_map_creator.grok_client import GrokMapCreator
from generators.llm_map_creator.map_processing import parse_response
from map_schema.canonical_map import CanonicalMap
from map_schema.map_validator import MapValidator, ValidationReport
from candidate import Candidate

LOGGER = logging.getLogger("FPS-EVALUATOR")


def run(base_generator: ExperimentSession) -> list[str]:
    from openai import APIError
    """Generate maps with bounded corrective attempts and strict parsing."""
    settings = base_generator.generator_settings
    generic_placement = settings["map_completion"]["mode"] == "generic"
    map_count = int(settings.get("map_count", 4))
    width = int(settings.get("map_width", 48))
    height = int(settings.get("map_height", 48))

    if map_count < 1 or map_count > 32:
        raise ValueError("llm_map_creator map_count must be between 1 and 32")

    validation_settings = dict(settings.get("validation", {}))
    validation_settings["minimum_spawn_count"] = (
        0 if generic_placement
        else max(2, int(validation_settings.get("minimum_spawn_count", 2)))
    )
    minimum_ratio = float(validation_settings.get("minimum_walkable_ratio", 0.0))
    maximum_ratio = float(validation_settings.get("maximum_walkable_ratio", 1.0))
    if minimum_ratio > maximum_ratio:
        raise ValueError(
            "minimum_walkable_ratio must be at most maximum_walkable_ratio"
        )

    rules_text = str(
        settings.get(
            "rules_text",
            "Create a balanced competitive FPS map with clear routes, "
            "one contested center, and at least one flank.",
        )
    ).strip()
    if not rules_text:
        raise ValueError("generator_settings.rules_text requires text")

    examples = _load_examples(base_generator)
    creator = GrokMapCreator(
        dict(settings.get("grok", {})),
        layout_only=generic_placement,
    )
    validator = MapValidator(validation_settings)
    maximum_attempts = max(
        1, min(5, int(settings.get("max_attempts_per_map", 2)))
    )

    generated_maps: list[CanonicalMap] = []
    output_map_ids: list[str] = []
    generation_summary: list[dict[str, Any]] = []

    for map_index in range(map_count):
        desired_map_id = f"llm_map_{map_index:04d}"
        feedback: dict[str, Any] | None = None
        last_map: CanonicalMap | None = None
        accepted_attempt = 0
        attempt_summaries: list[dict[str, Any]] = []
        request_status = "attempts_exhausted"

        for attempt in range(1, maximum_attempts + 1):
            if base_generator.production_time_expired():
                request_status = (
                    "deadline_reached" if attempt_summaries else "not_started"
                )
                break

            provider_error = None
            response_result = None
            response_payload = None
            canonical_map = None

            try:
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
                response_payload = response_result.response.model_dump(
                    mode="json"
                )
                canonical_map = parse_response(
                    response_result.response,
                    map_id=f"{desired_map_id}_attempt_{attempt:02d}",
                    width=width,
                    height=height,
                    layout_only=generic_placement,
                    metadata={
                        "generator": "llm_map_creator",
                        "llm_provider": "xai",
                        "llm_model": response_result.model,
                        "llm_request_id": desired_map_id,
                        "llm_response_id": response_result.response_id,
                        "llm_attempt": attempt,
                        "llm_usage": response_result.usage,
                        "rules_text": rules_text,
                    },
                )

                last_map = canonical_map
                generated_maps.append(canonical_map)
                validation = validator.validate(canonical_map)
            except APIError as exc:
                provider_error = {
                    "type": type(exc).__name__,
                    "status_code": getattr(exc, "status_code", None),
                }
                validation = ValidationReport(
                    valid=False,
                    errors=[f"Provider request failed: {type(exc).__name__}"],
                )
            except ValueError as exc:
                validation = ValidationReport(
                    valid=False,
                    errors=[str(exc)],
                )
            attempt_status = (
                "provider_error" if provider_error is not None
                else "accepted" if validation.valid
                else "invalid_layout" if canonical_map is not None
                else "malformed_response"
            )
            response_id = (
                response_result.response_id
                if response_result is not None
                else None
            )
            _save_attempt(
                base_generator,
                desired_map_id,
                attempt,
                {
                    "map_index": map_index,
                    "attempt": attempt,
                    "provider": "xai",
                    "model": (
                        response_result.model
                        if response_result is not None
                        else creator.model
                    ),
                    "response_id": response_id,
                    "usage": (
                        response_result.usage
                        if response_result is not None
                        else {}
                    ),
                    "response": response_payload,
                    "normalization_actions": [],
                    "validation_before_repair": validation.to_dict(),
                    "repair_actions": [],
                    "validation_after_repair": validation.to_dict(),
                    "status": attempt_status,
                    "provider_error": provider_error,
                },
            )
            attempt_summaries.append({
                "attempt": attempt,
                "response_id": response_id,
                "map_id": canonical_map.map_id if canonical_map is not None else None,
                "valid": validation.valid,
                "normalization_action_count": 0,
                "repair_action_count": 0,
                "errors": validation.errors,
            })

            if provider_error is not None:
                request_status = "provider_error"
                break

            if validation.valid:
                request_status = "accepted"
                accepted_attempt = attempt
                break

            feedback = {
                "validation_errors": validation.errors,
                "validation_warnings": validation.warnings,
                "measured": validation.measured,
            }
            if response_payload is not None:
                feedback["previous_candidate"] = response_payload

        valid_after_generation = accepted_attempt > 0
        generation_summary.append({
            "request_id": desired_map_id,
            "map_id": last_map.map_id if last_map is not None else None,
            "accepted_attempt": accepted_attempt,
            "valid": valid_after_generation,
            "attempts": attempt_summaries,
            "status": request_status,
        })

        if last_map is None:
            LOGGER.warning(
                "Map request '%s': %s after %s attempts; no well-formed grid.",
                desired_map_id,
                request_status,
                len(attempt_summaries),
            )
            continue

        if not valid_after_generation:
            LOGGER.warning(
                "Map request '%s' failed generator validation; "
                "submit its last well-formed grid for shared evaluation.",
                desired_map_id,
            )

        last_map = last_map.replace_grid(
            last_map.grid,
            {
                "llm_accepted_attempt": accepted_attempt,
                "llm_valid_after_generation": valid_after_generation,
                "llm_attempt_count": len(attempt_summaries),
            },
        )
        generated_maps[-1] = last_map
        output_map_ids.append(last_map.map_id)

    summary_path = base_generator.output_dir / "llm_map_generation.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generator": "llm_map_creator",
                "provider": "xai",
                "map_count": map_count,
                "generated_layout_count": len(generated_maps),
                "width": width,
                "height": height,
                "rules_text": rules_text,
                "examples_used": len(examples),
                "maps": generation_summary,
                "started_request_count": sum(
                    bool(item["attempts"]) for item in generation_summary
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    LOGGER.info(
        "Created %s complete canonical maps with direct LLM output.",
        len(generated_maps),
    )
    LOGGER.info(
        "Recorded %s generated layouts from %s map requests.",
        len(generated_maps),
        map_count,
    )

    candidates = [
        Candidate(canonical_map=item)
        for item in generated_maps
    ]
    base_generator.evaluate_candidates(candidates, epoch=0)
    final_map_ids = output_map_ids

    epoch_dir = base_generator.output_dir / "epoch_0000"
    epoch_dir.mkdir(parents=True, exist_ok=True)
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

    yield final_map_ids

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
