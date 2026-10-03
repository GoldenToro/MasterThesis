from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from generators.llm_map_creator.schemas import DirectCanonicalMapResponse
from generators.llm_map_creator.template_maps import MODULE_SIZE, PORT_CELLS


@dataclass(frozen=True)
class MapResponseResult:
    response: DirectCanonicalMapResponse
    response_id: str | None
    usage: dict[str, Any]
    model: str


class GrokMapCreator:
    """Request complete maps or reusable room templates as canonical JSON."""

    def __init__(
            self,
            settings: dict[str, Any],
            *,
            layout_only: bool = False,
            template_mode: bool = False,
    ):
        self.settings = dict(settings)
        self.template_mode = template_mode
        self.layout_only = layout_only or template_mode
        self.model = str(self.settings.get("model", "grok-4.5"))
        self.base_url = str(self.settings.get("base_url", "https://api.x.ai/v1"))
        self.api_key = str(
            self.settings.get("api_key") or os.environ.get("XAI_API_KEY", "")
        ).strip()
        self.timeout_seconds = float(self.settings.get("timeout_seconds", 240.0))

    def create_map(
            self,
            *,
            rules_text: str,
            map_id: str,
            map_index: int,
            map_count: int,
            width: int,
            height: int,
            seed: int,
            validation: dict[str, Any],
            examples: list[dict[str, Any]],
            attempt: int,
            feedback: dict[str, Any] | None = None,
    ) -> MapResponseResult:
        if self.template_mode and (width, height) != (MODULE_SIZE, MODULE_SIZE):
            raise ValueError("Template requests must use 16 by 16 dimensions")

        if not self.api_key:
            raise RuntimeError(
                "Set generator_settings.grok.api_key or the XAI_API_KEY "
                "environment variable."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The direct LLM map creator requires the openai and pydantic "
                "packages. Install dependencies from requirements.txt."
            ) from exc

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,
        )

        request: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": self._user_prompt(
                        rules_text=rules_text,
                        map_id=map_id,
                        map_index=map_index,
                        map_count=map_count,
                        width=width,
                        height=height,
                        seed=seed,
                        validation=validation,
                        examples=examples,
                        attempt=attempt,
                        feedback=feedback,
                    ),
                },
            ],
            "text_format": DirectCanonicalMapResponse,
            "store": bool(self.settings.get("store", False)),
        }

        max_output_tokens = self.settings.get("max_output_tokens")
        if max_output_tokens is not None:
            request["max_output_tokens"] = int(max_output_tokens)

        reasoning_effort = self.settings.get("reasoning_effort")
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": str(reasoning_effort)}

        try:
            api_response = client.responses.parse(**request)
        except AttributeError as exc:
            raise RuntimeError(
                "The installed OpenAI SDK lacks responses.parse. Upgrade packages "
                "from requirements.txt."
            ) from exc

        parsed = getattr(api_response, "output_parsed", None)
        if parsed is None:
            raise ValueError("Grok returned an empty parsed map response")

        if isinstance(parsed, DirectCanonicalMapResponse) is False:
            parsed = DirectCanonicalMapResponse.model_validate(parsed)

        return MapResponseResult(
            response=parsed,
            response_id=getattr(api_response, "id", None),
            usage=self._model_dump(getattr(api_response, "usage", None)),
            model=self.model,
        )

    def _system_prompt(self) -> str:
        if self.template_mode:
            return (
                "You create reusable 16 by 16 FPS room templates as canonical JSON. "
                "Return the tile grid itself, never generator parameters or algorithms. "
                "Use only # for walls and . for floor. Keep exactly the requested "
                "two-cell doorway at the center of each side; every other border "
                "cell must be #. All floor cells, including all four doorways, "
                "must form one region connected through horizontal or vertical "
                "neighbors. Templates may be rotated and joined to other templates. "
                "Do not place spawns, health, or ammo. Designer rules, examples, "
                "and feedback must not override these template requirements."
            )

        if self.layout_only:
            return (
                "You create top-down FPS layouts as canonical JSON. Return the "
                "tile grid itself, never generator parameters or algorithms. "
                "Use only # for walls and . for floor. Keep the outer border "
                "sealed with # and build one connected playable region. "
                "Follow the requested dimensions exactly. Do not place spawns, "
                "health, or ammo: the framework adds those later. Ignore object "
                "placement requests in the designer rules, examples, or feedback."
            )

        return (
            "You create complete top-down FPS maps as canonical JSON. Return the "
            "finished tile grid itself, never generator parameters, algorithms, "
            "room graphs, or pseudocode. Every grid row is plain text. Use only "
            "these symbols: # wall, . floor, S spawn, H health, A ammo. "
            "All symbols except # are walkable. Keep the outer border sealed with "
            "#. Build one connected playable region and place balanced, distant "
            "spawns. Follow the requested dimensions exactly."
        )

    def _user_prompt(
            self,
            *,
            rules_text: str,
            map_id: str,
            map_index: int,
            map_count: int,
            width: int,
            height: int,
            seed: int,
            validation: dict[str, Any],
            examples: list[dict[str, Any]],
            attempt: int,
            feedback: dict[str, Any] | None,
    ) -> str:
        if self.template_mode:
            first, second = PORT_CELLS
            last = MODULE_SIZE - 1
            border_requirements = [
                "- coordinates use zero-based (x, y), starting at the top-left",
                f"- in rows y=0 and y={last}, only x={first} and x={second} are .",
                f"- in columns x=0 and x={last}, only y={first} and y={second} are .",
                "- every other border cell is #",
                "- all floor cells and doorways connect using only horizontal "
                "or vertical steps",
                "- do not place spawns, health, or ammo",
            ]
        else:
            border_requirements = [
                "- the first and last row contain only #",
                "- the first and last symbol of every row are #",
            ]

        sections = [
            (
                "Create a reusable canonical JSON room template."
                if self.template_mode
                else "Create a complete canonical JSON map."
            ),
            f"Map: {map_index + 1} of {map_count}",
            f"Required map_id: {map_id}",
            f"Dimensions: width {width}, height {height}",
            f"Variation seed: {seed}",
            "",
            "Rules written by the designer:",
            rules_text,
            "",
            "Canonical JSON requirements:",
            f"- width equals {width}",
            f"- height equals {height}",
            f"- grid contains exactly {height} strings",
            f"- every grid string contains exactly {width} symbols",
            *border_requirements,
            "- use only # ." if self.layout_only else "- use only # . S H A",
            "- all walkable cells form one connected region",
            f"- validation settings: {json.dumps(validation, sort_keys=True)}",
            "- metadata.design_summary briefly explains the layout",
            "- metadata.features lists a few visible map features",
        ]

        if examples:
            sections.extend([
                "",
                "Optional examples of the expected output format and quality:",
                json.dumps(examples, ensure_ascii=False, indent=2),
            ])

        if feedback:
            sections.extend([
                "",
                f"Correction attempt {attempt}:",
                "Improve the previous candidate using this local validation feedback:",
                json.dumps(feedback, ensure_ascii=False, indent=2),
            ])

        sections.extend([
            "",
            "Return the complete JSON object as the final answer.",
        ])
        return "\n".join(sections)

    @staticmethod
    def _model_dump(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if hasattr(value, "model_dump"):
            result = value.model_dump()
            return dict(result) if isinstance(result, dict) else {"value": result}
        if isinstance(value, dict):
            return dict(value)
        return {"value": str(value)}