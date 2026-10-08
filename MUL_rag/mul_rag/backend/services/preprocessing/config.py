from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


DEFAULT_PREPROCESS_CONFIG: Dict[str, Any] = {
    "standardVersion": "1.0",
    "datasetType": "generic_tabular",
    "headerDetection": True,
    "concatSheets": True,
    "addProvenanceColumns": True,
    "keepExtraColumns": True,
    "missingValues": ["", " ", "NA", "N/A", "null", "NULL", "None", "nan", "NaN", "--", "-", "/"],
    "dedupe": {"enabled": True, "subset": [], "keep": "first"},
    "textNormalization": {"strip": True, "collapseWhitespace": True},
    "columnSpecs": {},
}

SUPPORTED_PREPROCESS_SUFFIXES = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".las"}


def merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged
