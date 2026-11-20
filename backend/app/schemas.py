from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# SQLite returns naive datetimes; everything stored is UTC, so say so on the way out (and in).
UTCDateTime = Annotated[datetime, AfterValidator(
    lambda d: d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    app: str
    env: str
    database: str
    simulation_mode: bool


class TankCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    species: Optional[str] = None
    life_stage: Optional[str] = None
    volume_liters: Optional[float] = Field(default=None, gt=0)
    location: Optional[str] = None
    notes: Optional[str] = None
    length_cm: Optional[float] = Field(default=None, gt=0)
    depth_cm: Optional[float] = Field(default=None, gt=0)


class TankRead(TankCreate, ORM):
    id: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class SensorRead(ORM):
    id: str
    tank_id: str
    device_id: str
    metric: str
    unit: str
    status: str
    physical_min: Optional[float]
    physical_max: Optional[float]


class ReadingCreate(BaseModel):
    """What a device sends. Tank, metric and unit come from the registered sensor."""
    sensor_id: str
    value: Optional[float] = None
    observed_at: UTCDateTime
    sequence_no: Optional[int] = None
    calibration_id: Optional[str] = None
    source: Literal["sensor", "camera"] = "sensor"
    raw_value: Optional[float] = None
    raw_payload: Optional[dict] = None


class ReadingRead(ORM):
    id: str
    tank_id: str
    device_id: Optional[str]
    sensor_id: str
    metric: str
    value: Optional[float]
    unit: str
    observed_at: UTCDateTime
    received_at: UTCDateTime
    sequence_no: Optional[int]
    quality_status: str
    source: str


class ThresholdRead(ORM):
    id: str
    tank_id: Optional[str]
    metric: str
    low_critical: Optional[float]
    low_warning: Optional[float]
    high_warning: Optional[float]
    high_critical: Optional[float]
    hysteresis: Optional[float]
    source: str
    reference: Optional[str]


class AlertRead(ORM):
    id: str
    tank_id: str
    sensor_id: Optional[str]
    device_id: Optional[str]
    metric: str
    severity: str
    status: str
    value: Optional[float]
    reason: str
    triggered_at: UTCDateTime
    resolved_at: Optional[UTCDateTime]
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[UTCDateTime]
