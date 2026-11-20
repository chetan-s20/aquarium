"""Audit trail for operator actions (Phase 6).

Write-through: one row per action, appended on the same session the action uses,
never updated or deleted (retention applies to readings, not to the audit trail).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, actor: Optional[str], action: str, entity_type: str,
          entity_id: Optional[str] = None, detail: Optional[str] = None) -> AuditLog:
    a = AuditLog(actor=actor, action=action, entity_type=entity_type,
                 entity_id=entity_id, detail=detail)
    db.add(a)
    return a
