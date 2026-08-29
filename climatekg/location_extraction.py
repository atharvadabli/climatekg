from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


def _copy_key(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def enforce_copied_location_names(result: Any, source_texts: Iterable[str]) -> Any:
    """Remove unsupported lookup strings while preserving a visible extraction warning."""
    source = _copy_key("\n".join(source_texts))
    contexts = []
    warnings = list(result.ambiguities)
    for context in result.contexts:
        support = context.spatial_support
        location = support.enrichable_study_location_name if support else None
        if location and _copy_key(location) not in source:
            warnings.append(f"ENRICHABLE_STUDY_LOCATION_NOT_COPIED:{context.temp_id}:{location}")
            support = support.model_copy(update={"enrichable_study_location_name": None})
            context = context.model_copy(update={"spatial_support": support})
        contexts.append(context)
    return result.model_copy(update={"contexts": contexts, "ambiguities": warnings})
