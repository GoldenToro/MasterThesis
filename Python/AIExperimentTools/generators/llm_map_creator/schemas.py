from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMMapMetadata(BaseModel):
    """Small, human-readable design notes returned beside the grid."""

    model_config = ConfigDict(extra="forbid")

    design_summary: str = Field(min_length=1, max_length=500)
    features: list[str] = Field(default_factory=list, max_length=12)


class DirectCanonicalMapResponse(BaseModel):
    """The complete map JSON returned by Grok.

    Geometry checks such as exact row count and row width run locally. Keeping
    those checks outside the response schema lets the framework preserve and
    repair imperfect research outputs instead of losing the whole attempt during
    response parsing.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    map_id: str = Field(min_length=1, max_length=120)
    width: int = Field(ge=1, le=256)
    height: int = Field(ge=1, le=256)
    grid: list[str] = Field(min_length=1, max_length=256)
    metadata: LLMMapMetadata
