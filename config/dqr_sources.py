"""
DQR source identifiers.

A DQR source is the *origin* of a Data Quality Rule: the shelf catalog of 10
dimensions ("standard") or a data-product-specific rule defined in
``config.custom_dqr_catalog`` ("custom"). Each Data Product can opt into one
or both sources and assign a percentage weight to each one.
"""
from __future__ import annotations

from typing import Dict, List

SOURCE_STANDARD: str = "standard"
SOURCE_CUSTOM: str = "custom"

ALL_SOURCES: List[str] = [SOURCE_STANDARD, SOURCE_CUSTOM]

SOURCE_LABELS: Dict[str, str] = {
    SOURCE_STANDARD: "Standard DQR Rules",
    SOURCE_CUSTOM: "Custom DQR Rules",
}
