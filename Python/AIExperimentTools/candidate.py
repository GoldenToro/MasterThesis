from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from map_schema.canonical_map import CanonicalMap


@dataclass
class Candidate:
    """A generated map together with its search state and evaluation.

    evaluation is None until the evaluation procedure produces a result.
    A result may describe a successful, skipped, or failed evaluation.

    This object groups data in memory. Existing map and result files
    remain responsible for storing that data.
    """

    canonical_map: CanonicalMap
    genome: Any | None = None
    evaluation: dict[str, Any] | None = None

    @property
    def map_id(self) -> str:
        return self.canonical_map.map_id