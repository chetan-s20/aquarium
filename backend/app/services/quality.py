from datetime import datetime, timezone
from typing import Optional


def evaluate_reading(
    value: Optional[float],
    physical_min: Optional[float],
    physical_max: Optional[float],
) -> str:
    if value is None:
        return "missing"
    if physical_min is not None and value < physical_min:
        return "invalid"
    if physical_max is not None and value > physical_max:
        return "invalid"
    return "valid"
