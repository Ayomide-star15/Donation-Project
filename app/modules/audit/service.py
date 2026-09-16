import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditOutcome
from app.modules.audit.models import AuditLog


def add_audit_log(
    db: Session,
    action: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    return entry
