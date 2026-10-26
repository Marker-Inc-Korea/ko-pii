"""Shared metadata boundary for optional RAG adapters."""
from __future__ import annotations

from typing import Any

from ko_pii.anonymizer import Anonymizer
from ko_pii.structured import anonymize_json


def mask_metadata(metadata: dict[str, Any], anon: Anonymizer) -> dict[str, Any]:
    """Mask bounded JSON string values; refuse keys that would need masking.

    Keys stay stable for framework metadata-exclusion lists. Numeric identifiers
    must be provided as strings. Unsupported values fail instead of passing raw.
    """
    result = anonymize_json(metadata, anonymizer=anon).data

    def check_keys(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if anon.process(key).text != key:
                    raise ValueError("RAG metadata keys must not contain values requiring masking")
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)

    check_keys(result)
    if not isinstance(result, dict):
        raise ValueError("RAG metadata must be a JSON object")
    return result
