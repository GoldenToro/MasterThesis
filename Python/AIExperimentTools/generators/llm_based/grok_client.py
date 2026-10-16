from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class MapResponseResult:
    response: str | BaseModel
    response_id: str | None
    usage: dict[str, Any]
    model: str


class GrokMapCreator:
    """Send a caller-built prompt and return text or a supplied response schema."""

    def __init__(
            self,
            settings: dict[str, Any],
    ):
        self.settings = dict(settings)
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
            width: int,
            height: int,
            attempt: int,
            raw_output_dir: Path | None = None,
            response_format: type[BaseModel] | None = None,
    ) -> MapResponseResult:
        if not self.api_key:
            raise RuntimeError(
                "Set generator_settings.grok.api_key or the XAI_API_KEY "
                "environment variable."
            )

        try:
            from openai import DefaultHttpxClient, OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The direct LLM map creator requires the openai and pydantic "
                "packages. Install dependencies from requirements.txt."
            ) from exc

        http_options = {}
        if raw_output_dir is not None:
            raw_output_dir.mkdir(parents=True, exist_ok=True)
            prefix = raw_output_dir / f"{map_id}_attempt_{attempt:02d}"

            def save_request(request):
                # Capture the SDK's actual request body.
                prefix.with_suffix(".request.json").write_bytes(request.content)
                prompt = json.loads(request.content)["input"][0]["content"]
                prefix.with_suffix(".prompt.txt").write_bytes(prompt.encode("utf-8"))

            def save_response(response):
                # Read before SDK parsing so malformed and error replies survive.
                prefix.with_suffix(".response.json").write_bytes(response.read())

            http_options["http_client"] = DefaultHttpxClient(
                event_hooks={"request": [save_request], "response": [save_response]},
            )

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,
            **http_options,
        )

        request: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": rules_text,
                },
            ],
            "store": bool(self.settings.get("store", False)),
        }

        max_output_tokens = self.settings.get("max_output_tokens")
        if max_output_tokens is not None:
            request["max_output_tokens"] = int(max_output_tokens)

        reasoning_effort = self.settings.get("reasoning_effort")
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": str(reasoning_effort)}

        try:
            if response_format is not None:
                api_response = client.responses.parse(
                    **request, text_format=response_format,
                )
            else:
                api_response = client.responses.create(**request)
        except AttributeError as exc:
            raise RuntimeError(
                "The installed OpenAI SDK lacks responses.parse. Upgrade packages "
                "from requirements.txt."
            ) from exc
        finally:
            client.close()

        if response_format is not None:
            parsed = getattr(api_response, "output_parsed", None)
            if parsed is None:
                raise ValueError("Grok returned an empty parsed map response")
            if not isinstance(parsed, response_format):
                parsed = response_format.model_validate(parsed)
        else:
            parsed = api_response.output_text
            if raw_output_dir is not None:
                prefix.with_suffix(".response.txt").write_bytes(parsed.encode("utf-8"))

        return MapResponseResult(
            response=parsed,
            response_id=getattr(api_response, "id", None),
            usage=self._model_dump(getattr(api_response, "usage", None)),
            model=self.model,
        )

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
