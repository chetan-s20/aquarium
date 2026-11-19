from typing import Optional

QUALITY_RULE_VERSION = "range-v1"


def evaluate_reading(value: Optional[float], physical_min: Optional[float], physical_max: Optional[float]) -> str:
    """valid / invalid (outside what the sensor can physically read) / missing."""
    if value is None:
        return "missing"
    if physical_min is not None and value < physical_min:
        return "invalid"
    if physical_max is not None and value > physical_max:
        return "invalid"
    return "valid"
