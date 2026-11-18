import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import ImportRun, Reading, Sensor, Tank

REQUIRED = ["tank_id", "sensor_id", "metric", "value", "unit", "observed_at"]


def _parse_dt(value: str) -> Tuple[Optional[datetime], Optional[str]]:
    value = value.strip()
    try:
        # ISO 8601
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), None
    except ValueError:
        return None, f"invalid timestamp: {value}"


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def validate_csv(
    content: bytes,
    mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    text = content.decode("utf-8-sig", errors="replace")
    delimiter = _detect_delimiter(text[:2048])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    mapping = mapping or {}
    # apply mapping: mapping[target]=source
    errors: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    seen: set = set()
    duplicates = 0
    gaps = 0
    outliers = 0
    accepted = 0
    rejected = 0
    row_number = 1
    for raw in reader:
        row_number += 1
        record = {}
        for target in REQUIRED + ["device_id", "sequence_no"]:
            src = mapping.get(target, target)
            record[target] = raw.get(src)
        # validate required
        row_errors = []
        for col in REQUIRED:
            if record.get(col) in (None, ""):
                row_errors.append(f"missing {col}")
        tank_id = record.get("tank_id")
        sensor_id = record.get("sensor_id")
        tank = None
        sensor = None
        if tank_id:
            # defer DB checks to caller? We'll leave existence checks here if session passed; for pure validate, skip
            pass
        dt, err = _parse_dt(str(record.get("observed_at") or ""))
        if err:
            row_errors.append(err)
        value = None
        try:
            if record.get("value") not in (None, ""):
                value = float(record["value"])
        except (ValueError, TypeError):
            row_errors.append(f"invalid value: {record.get('value')}")
            value = None

        # duplicate detection
        if sensor_id and dt:
            key = (sensor_id, dt.isoformat())
            if key in seen:
                duplicates += 1
                row_errors.append("duplicate (sensor, observed_at)")
            seen.add(key)

        # physical limits / outliers (best-effort if sensor known later) -> basic range for value
        if value is not None and (value < -1e9 or value > 1e9):
            outliers += 1
            row_errors.append("implausible magnitude")

        if row_errors:
            rejected += 1
            errors.append({"row": row_number, "errors": row_errors, "raw": raw})
        else:
            accepted += 1
            rows.append({
                "tank_id": tank_id,
                "sensor_id": sensor_id,
                "device_id": record.get("device_id"),
                "metric": record.get("metric"),
                "value": value,
                "unit": record.get("unit"),
                "observed_at": dt.isoformat(),
                "sequence_no": int(record["sequence_no"]) if record.get("sequence_no") not in (None, "") else None,
            })

    return {
        "delimiter": delimiter,
        "fieldnames": fieldnames,
        "row_count": row_number - 1,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "duplicate_count": duplicates,
        "gap_count": gaps,
        "outlier_count": outliers,
        "errors": errors[:50],
        "preview": rows[:10],
        "rows": rows,
    }


def commit_import(db: Session, content: bytes, filename: str, mapping: Optional[Dict[str, str]] = None, original_path: Optional[str] = None) -> ImportRun:
    sha = hashlib.sha256(content).hexdigest()
    result = validate_csv(content, mapping)
    run = ImportRun(
        filename=filename,
        original_path=original_path,
        sha256=sha,
        status="processing",
        row_count=result["row_count"],
        mapping=mapping,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    inserted = 0
    rejected = result["rejected_count"]
    for row in result["rows"]:
        tank = db.get(Tank, row["tank_id"])
        sensor = db.get(Sensor, row["sensor_id"])
        if not tank or not sensor:
            rejected += 1
            continue
        # unit check
        if sensor.unit and row["unit"] and sensor.unit != row["unit"]:
            rejected += 1
            continue
        observed = datetime.fromisoformat(row["observed_at"])
        reading = Reading(
            tank_id=row["tank_id"],
            device_id=row["device_id"],
            sensor_id=row["sensor_id"],
            metric=row["metric"],
            value=row["value"],
            unit=row["unit"],
            observed_at=observed,
            sequence_no=row["sequence_no"],
            quality_status="unknown",
            quality_rule_version="import-v1",
            source="import",
            raw_payload={"import_run_id": run.id, "original_row": row},
            import_run_id=run.id,
        )
        db.add(reading)
        inserted += 1

    run.accepted_count = inserted
    run.rejected_count = rejected
    run.duplicate_count = result["duplicate_count"]
    run.gap_count = result["gap_count"]
    run.outlier_count = result["outlier_count"]
    run.status = "completed"
    from datetime import datetime as _dt, timezone as _tz
    run.finished_at = _dt.now(_tz.utc)
    db.commit()
    db.refresh(run)
    return run
