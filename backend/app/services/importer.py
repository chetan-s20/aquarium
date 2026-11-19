"""Bulk CSV import of historical readings: preview (validate only) then commit."""
import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import ImportRun, Reading, Sensor
from app.services.quality import QUALITY_RULE_VERSION, evaluate_reading

REQUIRED = ["sensor_id", "value", "observed_at"]
OPTIONAL = ["sequence_no"]


def _parse_dt(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def validate_csv(content: bytes, mapping: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """mapping = {our_column: their_column} for files with different headers."""
    text = content.decode("utf-8-sig", errors="replace")
    delimiter = _detect_delimiter(text[:2048])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    mapping = mapping or {}
    errors: list[dict] = []
    rows: list[dict] = []
    seen: set = set()
    duplicates = 0
    line = 1
    for raw in reader:
        line += 1
        rec = {c: (raw.get(mapping.get(c, c)) or "").strip() for c in REQUIRED + OPTIONAL}
        problems = [f"missing {c}" for c in ("sensor_id", "observed_at") if not rec[c]]
        observed = _parse_dt(rec["observed_at"]) if rec["observed_at"] else None
        if rec["observed_at"] and observed is None:
            problems.append(f"invalid timestamp: {rec['observed_at']}")
        value = None
        if rec["value"]:
            try:
                value = float(rec["value"])
            except ValueError:
                problems.append(f"invalid value: {rec['value']}")
        seq = None
        if rec["sequence_no"]:
            try:
                seq = int(rec["sequence_no"])
            except ValueError:
                problems.append(f"invalid sequence_no: {rec['sequence_no']}")
        key = (rec["sensor_id"], observed, seq)
        if observed and key in seen:
            duplicates += 1
            problems.append("duplicate (sensor, observed_at) in file")
        seen.add(key)

        if problems:
            errors.append({"row": line, "errors": problems, "raw": raw})
        else:
            rows.append({"sensor_id": rec["sensor_id"], "value": value, "observed_at": observed, "sequence_no": seq})

    return {
        "delimiter": delimiter,
        "fieldnames": reader.fieldnames or [],
        "row_count": line - 1,
        "accepted_count": len(rows),
        "rejected_count": len(errors),
        "duplicate_count": duplicates,
        "errors": errors[:50],
        "preview": [{**r, "observed_at": r["observed_at"].isoformat()} for r in rows[:10]],
        "rows": rows,
    }


def commit_import(db: Session, content: bytes, filename: str, mapping: Optional[dict[str, str]] = None) -> ImportRun:
    result = validate_csv(content, mapping)
    run = ImportRun(
        filename=filename, sha256=hashlib.sha256(content).hexdigest(), status="processing",
        row_count=result["row_count"], mapping=mapping, duplicate_count=result["duplicate_count"],
    )
    db.add(run)
    db.flush()

    sensors: dict[str, Optional[Sensor]] = {}
    inserted, rejected = 0, result["rejected_count"]
    for row in result["rows"]:
        sid = row["sensor_id"]
        if sid not in sensors:
            sensors[sid] = db.get(Sensor, sid)
        sensor = sensors[sid]
        exists = sensor and db.query(Reading.id).filter(
            Reading.sensor_id == sid, Reading.observed_at == row["observed_at"]
        ).first()
        if not sensor or exists:
            rejected += 1
            continue
        db.add(Reading(
            tank_id=sensor.tank_id, device_id=sensor.device_id, sensor_id=sid,
            metric=sensor.metric, unit=sensor.unit, value=row["value"], raw_value=row["value"],
            observed_at=row["observed_at"], sequence_no=row["sequence_no"],
            quality_status=evaluate_reading(row["value"], sensor.physical_min, sensor.physical_max),
            quality_rule_version=QUALITY_RULE_VERSION, source="import", import_run_id=run.id,
        ))
        inserted += 1

    run.accepted_count = inserted
    run.rejected_count = rejected
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
