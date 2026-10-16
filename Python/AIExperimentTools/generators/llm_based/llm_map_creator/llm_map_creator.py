from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic, sleep

from candidate import Candidate
from experiment_session import ExperimentSession
from generators.llm_based.grok_client import GrokMapCreator
from generators.llm_based.response_parser import repair_errors
from map_schema.canonical_map import ALLOWED_SYMBOLS, CanonicalMap
from map_schema.map_validator import MapValidationError, MapValidator

LOGGER = logging.getLogger("FPS-EVALUATOR")


def run(session: ExperimentSession):
    """Request, validate, and repair maps independently in parallel."""
    from openai import APIError

    settings = session.generator_settings
    map_count = int(settings.get("map_count", 4))
    attempts = int(settings.get("max_attempts_per_map", 2))
    workers = int(settings.get("concurrent_requests", 1))
    delay = float(settings.get("request_delay_seconds", 6))
    if min(map_count, attempts, workers) < 1:
        raise ValueError("map_count, max_attempts_per_map, and concurrent_requests must be positive")
    if not math.isfinite(delay) or delay < 0:
        raise ValueError("request_delay_seconds must be finite and non-negative")
    rules = settings.get("rules_text")
    if not isinstance(rules, str) or not rules.strip():
        raise ValueError("generator_settings.rules_text requires text")

    prompt = rules
    examples = _load_examples(session)
    if examples:
        prompt += "\n\nExamples:\n" + "\n\nor\n\n".join(examples)

    width = int(settings.get("map_width", 48))
    height = int(settings.get("map_height", 48))
    layout_only = settings["map_completion"]["mode"] == "generic"
    validation_settings = dict(settings.get("validation", {}))
    validation_settings["minimum_spawn_count"] = (
        0 if layout_only else max(2, int(validation_settings.get("minimum_spawn_count", 2)))
    )
    if validation_settings.get("minimum_walkable_ratio", 0) > validation_settings.get("maximum_walkable_ratio", 1):
        raise ValueError("minimum_walkable_ratio must be at most maximum_walkable_ratio")
    creator = GrokMapCreator(dict(settings.get("grok", {})))
    request_lock = Lock()
    next_start = 0.0

    def generate_map(index):
        nonlocal next_start
        request_id = f"llm_map_{index:04d}"
        current_prompt = prompt
        maps = []
        summary = {"request_id": request_id, "map_id": None, "valid": False, "attempts": [], "status": "not_started"}
        validator = MapValidator(validation_settings)
        for attempt in range(1, attempts + 1):
            with request_lock:
                if not session.production_time_expired():
                    sleep(max(0, next_start - monotonic()))
                if session.production_time_expired():
                    summary["status"] = "deadline_reached"
                    break
                next_start = monotonic() + delay

            payload = None
            usage = {}
            try:
                result = creator.create_map(
                    rules_text=current_prompt, map_id=request_id,
                    width=width, height=height, attempt=attempt,
                    raw_output_dir=session.output_dir / "_raw" / "llm",
                )
                payload = result.response
                usage = result.usage
                rows = payload.splitlines()
                errors = validator.validate_grid(
                    width, height, rows,
                    allowed_symbols=frozenset({"#", "."}) if layout_only else ALLOWED_SYMBOLS,
                )
                if errors:
                    raise MapValidationError(errors)
                canonical_map = CanonicalMap(
                    map_id=f"{request_id}_attempt_{attempt:02d}",
                    width=width, height=height, grid=tuple(rows),
                    metadata={"generator": "llm_map_creator", "llm_model": result.model,
                              "llm_response_id": result.response_id, "llm_attempt": attempt,
                              "llm_usage": usage},
                )
                maps.append(canonical_map)
                summary["map_id"] = canonical_map.map_id
                errors = validator.validate(canonical_map).errors
                status = "invalid_layout" if errors else "accepted"
            except APIError as exc:
                errors = [f"Provider request failed: {type(exc).__name__}"]
                status = "provider_error"
            except ValueError as exc:
                errors = exc.errors if isinstance(exc, MapValidationError) else [str(exc)]
                status = "malformed_response"

            record = {"attempt": attempt, "response": payload, "status": status, "errors": errors, "usage": usage}

            summary["attempts"].append(record)
            summary["status"] = status
            if status == "accepted":
                summary["valid"] = True
                break
            if status == "provider_error":
                break  # Provider failures are not map repairs and are not retried.

            if payload is not None:
                current_prompt = "Please repair the following map:\n\n" + payload
            else:
                current_prompt = prompt  # No parsed map to repair; request a replacement.
            current_prompt += "\n\nErrors:\n" + "\n".join(
                f"- {error}" for error in repair_errors(errors, width)
            )
            current_prompt += "\n\nReturn only the complete corrected map as plain text, without code fences or explanations."

        if not summary["valid"]:
            LOGGER.warning("Map request '%s': %s after %s attempts.", request_id, summary["status"], len(summary["attempts"]))
        return maps, summary

    generated_maps = []
    summaries = []
    with ThreadPoolExecutor(max_workers=min(workers, map_count)) as executor:
        for maps, summary in executor.map(generate_map, range(map_count)):
            generated_maps.extend(maps)
            summaries.append(summary)

    # Keep experiment analysis and evaluation on the calling thread.
    (session.output_dir / "llm_map_generation.json").write_text(json.dumps({
        "map_count": map_count, "generated_layout_count": len(generated_maps),
        "started_request_count": sum(bool(item["attempts"]) for item in summaries),
        "maps": summaries,
    }, indent=2), encoding="utf-8")
    session.evaluate_candidates([Candidate(canonical_map=item) for item in generated_maps], epoch=0)
    final_ids = [item["map_id"] for item in summaries if item["map_id"] is not None]
    epoch_dir = session.output_dir / "epoch_0000"
    epoch_dir.mkdir(parents=True, exist_ok=True)
    (epoch_dir / "checkpoint_summary.json").write_text(json.dumps({
        "epoch": 0, "population_size": len(final_ids), "selected_map_ids": final_ids,
        "source": "llm_map_creator",
    }, indent=2), encoding="utf-8")
    yield final_ids


def _load_examples(session):
    """Read configured examples and return only their grid text."""
    settings = session.generator_settings
    examples = list(settings.get("examples", []))
    paths = settings.get("example_map_paths", [])
    if isinstance(paths, str):
        paths = [paths]
    for path in paths:
        payload = json.loads((session.framework_root / path).read_text(encoding="utf-8"))
        examples.extend(payload["maps"] if "maps" in payload else [payload])
    limit = max(0, int(settings.get("max_prompt_examples", 2)))
    return ["\n".join(example["grid"]) for example in examples[:limit]]
