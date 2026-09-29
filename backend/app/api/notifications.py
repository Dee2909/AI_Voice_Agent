"""
Notifications API: manage user alerts, urgent events, callback tasks, and summaries.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.call import UrgencyLevel
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = Query(False, description="Filter only unread notifications"),
    urgency: str | None = Query(None, description="Filter by urgency level"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    query = select(Notification).where(Notification.user_id == user_id)

    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712

    if urgency:
        query = query.where(Notification.urgency == UrgencyLevel(urgency.upper()))

    query = query.order_by(Notification.created_at.desc()).limit(limit)
    notifs = db.scalars(query).all()

    return [
        {
            "id": str(n.id),
            "call_id": str(n.call_id) if n.call_id else None,
            "title": n.title,
            "body": n.body,
            "notification_type": n.notification_type.value,
            "urgency": n.urgency.value,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    notif = db.get(Notification, notification_id)
    if not notif or notif.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    db.commit()
    return {"id": str(notif.id), "is_read": True}


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, int]:
    count = db.scalar(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id)
        .where(Notification.is_read == False)  # noqa: E712
    )
    return {"unread_count": count or 0}
