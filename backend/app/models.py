import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tank(Base):
    __tablename__ = "tanks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    species: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    life_stage: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    volume_liters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tank_id: Mapped[str] = mapped_column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_type: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    firmware_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id"), nullable=False, index=True)
    tank_id: Mapped[str] = mapped_column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    interface: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sampling_interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    physical_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    physical_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rate_of_change_max_per_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    persistence_max_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    calibration_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Calibration(Base):
    __tablename__ = "calibrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sensor_id: Mapped[str] = mapped_column(String(36), ForeignKey("sensors.id"), nullable=False, index=True)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    uncertainty_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uncertainty_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    performed_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tank_id: Mapped[str] = mapped_column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True, index=True)
    sensor_id: Mapped[str] = mapped_column(String(36), ForeignKey("sensors.id"), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    sequence_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    quality_rule_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    calibration_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("calibrations.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="sensor")
    raw_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    import_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("import_runs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("sensor_id", "observed_at", "sequence_no", name="uq_reading_sensor_time_seq"),
    )


class Threshold(Base):
    __tablename__ = "thresholds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tank_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tanks.id"), nullable=True, index=True)
    sensor_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sensors.id"), nullable=True, index=True)
    metric: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    low_critical: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    low_warning: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_warning: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_critical: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hysteresis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cooldown_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False, default="unconfirmed")
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uncertainty: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    overridden_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tank_id: Mapped[str] = mapped_column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    sensor_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sensors.id"), nullable=True, index=True)
    metric: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("thresholds.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="rule")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gap_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outlier_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mapping: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tank_id: Mapped[str] = mapped_column(String(36), ForeignKey("tanks.id"), nullable=False, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="image")
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="camera")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    media_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("media_assets.id"), nullable=True, index=True)
    reading_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("readings.id"), nullable=True, index=True)
    label_type: Mapped[str] = mapped_column(String(60), nullable=False)
    label_value: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    annotator: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
