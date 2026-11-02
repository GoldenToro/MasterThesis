import json
import logging
import random
from pathlib import Path
from time import monotonic

from candidate import Candidate
from map_schema.canonical_map import CanonicalMap
from generators.llm_based.grok_client import GrokMapCreator
from generators.llm_based.template_hybrid.prompts import build_prompt
from generators.llm_based.schemas import DirectCanonicalMapResponse
from generators.llm_based.response_parser import parse_response
from generators.llm_based.template_hybrid.template_maps import (
    MODULE_SIZE,
    assemble_templates,
    validate_template,
)


LOGGER = logging.getLogger("FPS-EVALUATOR")


def run(session):
    settings = session.generator_settings
    width = settings["map_width"]
    height = settings["map_height"]
    template_count = settings.get("template_count", 8)
    maps_per_epoch = settings.get("maps_per_epoch", 10)
    max_attempts = settings.get("max_attempts_per_template", 2)
    room_count = settings.get("room_count")

    for name, value in (
            ("template_count", template_count),
            ("maps_per_epoch", maps_per_epoch),
            ("max_attempts_per_template", max_attempts),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")

    for name, value in (("map_width", width), ("map_height", height)):
        if type(value) is not int or value < MODULE_SIZE or value % MODULE_SIZE:
            raise ValueError(f"{name} must be a positive multiple of 16")

    total_rooms = (width // MODULE_SIZE) * (height // MODULE_SIZE)
    if room_count is not None and (
        type(room_count) is not int or not 1 <= room_count <= total_rooms
    ):
        raise ValueError(f"room_count must be an integer from 1 to {total_rooms}")

    if settings["map_completion"]["mode"] != "generic":
        raise ValueError("template_hybrid requires generic map completion")

    rules_text = str(settings.get(
        "template_rules_text",
        "Create a new room with useful interior obstacles and one to four "
        "centered doorways. Use the supplied parts as examples, without copying them.",
    )).strip()
    if not rules_text:
        raise ValueError("template_rules_text must not be empty")

    pool_path = settings.get("template_pool_path")
    if pool_path is not None:
        templates = _load_templates(session, pool_path)
    else:
        templates = _prepare_templates(
            session, template_count, max_attempts, rules_text
        )
    rng = random.Random(session.seed)
    all_map_ids = []
    epoch = 0

    if not templates:
        LOGGER.warning("No valid templates; no maps can be assembled.")

    while True:
        evaluated_count = 0
        candidates = []

        if templates:
            for index in range(maps_per_epoch):
                if session.production_time_expired():
                    break

                started = monotonic()
                canonical_map = assemble_templates(
                    templates,
                    rng,
                    map_id=f"hybrid_e{epoch:04d}_i{index:04d}",
                    width=width,
                    height=height,
                    room_count=room_count,
                )
                canonical_map = canonical_map.replace_grid(
                    canonical_map.grid,
                    {
                        "assembly_time_seconds": monotonic() - started,
                        "template_source": "saved_pool" if pool_path is not None else "llm",
                    },
                )
                candidate = Candidate(canonical_map=canonical_map)
                candidates.append(candidate)
                all_map_ids.append(candidate.map_id)
                evaluated_count += 1

        if candidates:
            session.evaluate_candidates(candidates, epoch=epoch)

        _write_json(
            session.output_dir / f"epoch_{epoch:04d}" / "checkpoint_summary.json",
            {
                "epoch": epoch,
                "population_size": len(all_map_ids),
                "selected_map_ids": list(all_map_ids),
                "evaluated_candidate_count": evaluated_count,
                "source": "template_hybrid",
            },
            )
        yield list(all_map_ids)

        if not templates or session.production_time_expired():
            return
        epoch += 1


def _read_templates(session, pool_path):
    if not isinstance(pool_path, str) or not pool_path.strip():
        raise ValueError("Template library path must be nonempty")
    path = Path(pool_path)
    if not path.is_absolute():
        path = session.framework_root / path
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Also accept older saved pools containing canonical map objects.
    if isinstance(payload, dict):
        payload = payload.get("templates")
    if not isinstance(payload, list) or not payload:
        raise ValueError("Template library must be a nonempty JSON list of map parts")
    templates = []
    for index, item in enumerate(payload):
        if isinstance(item, dict):
            template = CanonicalMap.from_dict(item)
        elif isinstance(item, list) and all(isinstance(row, str) for row in item):
            template = CanonicalMap(
                map_id=f"example_{index:04d}", width=MODULE_SIZE,
                height=MODULE_SIZE, grid=tuple(item),
            )
        else:
            raise ValueError(f"Map part {index} must be a list of grid rows")
        validate_template(template, require_connected_interior=True)
        if not any(template.grid == other.grid for other in templates):
            templates.append(template)
    return templates


def _load_templates(session, pool_path):
    started = monotonic()
    templates = _read_templates(session, pool_path)
    _write_json(session.output_dir / "_raw" / "template_pool.json",
                [list(template.grid) for template in templates])
    _write_json(session.output_dir / "template_generation.json", {
        "generator": "template_hybrid",
        "source": "saved_pool",
        "source_pool": str(pool_path),
        "requested_template_count": 0,
        "started_request_count": 0,
        "generated_template_count": 0,
        "loaded_template_count": len(templates),
        "accepted_template_count": len(templates),
        "preparation_seconds": monotonic() - started,
        "requests": [],
    })
    return templates


def _prepare_templates(session, count, max_attempts, rules_text):
    from openai import APIError

    creator = GrokMapCreator(
        dict(session.generator_settings.get("grok", {})),
    )
    validation_settings = {
        "minimum_spawn_count": 0,
        "require_single_connected_region": True,
    }
    examples_path = session.generator_settings.get(
        "template_examples_path", "configs/examples/map_parts/initial_parts.json"
    )
    templates = _read_templates(session, examples_path)
    example_count = len(templates)
    requests = []
    generated_count = 0
    preparation_started = monotonic()

    for index in range(count):
        if session.production_time_expired():
            break

        request_id = f"template_{index:04d}"
        feedback = None
        attempts = []
        request_status = "attempts_exhausted"

        for attempt in range(1, max_attempts + 1):
            if session.production_time_expired():
                request_status = "deadline_reached"
                break

            started = monotonic()
            response_result = None
            response_payload = None
            canonical_map = None
            errors = []
            provider_error = None

            try:
                response_result = creator.create_map(
                    rules_text=build_prompt(
                        template=True, layout_only=True,
                        rules_text=rules_text,
                        map_id=request_id,
                        map_index=index,
                        map_count=count,
                        width=MODULE_SIZE,
                        height=MODULE_SIZE,
                        seed=session.seed + index,
                        validation=validation_settings,
                        examples=[list(template.grid) for template in templates],
                        attempt=attempt,
                        feedback=feedback,
                    ),
                    map_id=request_id, width=MODULE_SIZE, height=MODULE_SIZE, attempt=attempt,
                    raw_output_dir=session.output_dir / "_raw" / "llm",
                    response_format=DirectCanonicalMapResponse,
                )
                response_payload = response_result.response.model_dump(mode="json")
                canonical_map = parse_response(
                    response_result.response,
                    map_id=f"{request_id}_attempt_{attempt:02d}",
                    width=MODULE_SIZE,
                    height=MODULE_SIZE,
                    layout_only=True,
                    metadata={
                        "generator": "template_hybrid",
                        "role": "room_template",
                        "llm_request_id": request_id,
                        "llm_response_id": response_result.response_id,
                        "llm_model": response_result.model,
                        "llm_usage": response_result.usage,
                        "llm_attempt": attempt,
                    },
                )
                generated_count += 1
                validate_template(canonical_map, require_connected_interior=True)
                if any(canonical_map.grid == template.grid for template in templates):
                    raise ValueError("This part already exists in the library; create a different layout")

            except APIError as exc:
                provider_error = {
                    "type": type(exc).__name__,
                    "status_code": getattr(exc, "status_code", None),
                }
                errors = [f"Provider request failed: {type(exc).__name__}"]

            except ValueError as exc:
                errors = [str(exc)]

            valid = canonical_map is not None and not errors
            status = (
                "provider_error" if provider_error is not None
                else "accepted" if valid
                else "invalid_template" if canonical_map is not None
                else "malformed_response"
            )
            attempt_record = {
                "attempt": attempt,
                "map_id": canonical_map.map_id if canonical_map else None,
                "content_hash": canonical_map.content_hash() if canonical_map else None,
                "status": status,
                "valid": valid,
                "errors": errors,
                "seconds": monotonic() - started,
                "response_id": response_result.response_id if response_result else None,
                "model": response_result.model if response_result else creator.model,
                "usage": response_result.usage if response_result else {},
                "provider_error": provider_error,
            }
            attempts.append(attempt_record)

            _write_json(
                session.output_dir / "llm_map_attempts"
                / f"{request_id}_attempt_{attempt:02d}.json",
                {
                    **attempt_record,
                    "response": response_payload,
                    "canonical_map": canonical_map.to_dict() if canonical_map else None,
                },
                )

            if provider_error is not None:
                request_status = "provider_error"
                break

            if valid:
                templates.append(canonical_map)
                request_status = "accepted"
                break

            feedback = {"validation_errors": errors}
            if response_payload is not None:
                feedback["previous_candidate"] = response_payload

        requests.append({
            "request_id": request_id,
            "status": request_status,
            "attempts": attempts,
        })
        if request_status != "accepted":
            LOGGER.warning(
                "Template request %s: %s.", request_id, request_status
            )

    _write_json(
        session.output_dir / "template_generation.json",
        {
            "generator": "template_hybrid",
            "requested_template_count": count,
            "started_request_count": sum(
                bool(item["attempts"]) for item in requests
            ),
            "generated_template_count": generated_count,
            "example_template_count": example_count,
            "accepted_template_count": len(templates) - example_count,
            "library_template_count": len(templates),
            "preparation_seconds": monotonic() - preparation_started,
            "rules_text": rules_text,
            "requests": requests,
        },
        )
    _write_json(
        session.output_dir / "_raw" / "template_pool.json",
        [list(template.grid) for template in templates],
        )
    return templates


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
