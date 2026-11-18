from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    volume_liters: Optional[float] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class TankRead(TankCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ReadingCreate(BaseModel):
    tank_id: str
    device_id: Optional[str] = None
    sensor_id: str
    metric: str
    value: Optional[float] = None
    unit: str
    observed_at: datetime
    sequence_no: Optional[int] = None
    quality_status: str = "unknown"
    quality_rule_version: Optional[str] = None
    calibration_id: Optional[str] = None
    source: str = "sensor"
    raw_value: Optional[float] = None
    raw_payload: Optional[dict] = None


class ReadingRead(ReadingCreate):
    id: str
    received_at: datetime
    created_at: datetime
