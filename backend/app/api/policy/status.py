
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.policy import UserStatus
from app.schemas.policy import UserStatusBase, UserStatusOut
from app.services.policy import UserStatusService

router = APIRouter(prefix="/status", tags=["Status"])


@router.get("", response_model=UserStatusOut)
def get_status(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> UserStatus:
    svc = UserStatusService(db, user_id)
    status = svc.get_current_status()
    if not status:
        raise HTTPException(status_code=404, detail="No active status")
    return status


@router.post("", response_model=UserStatusOut)
def set_status(
    status_in: UserStatusBase,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> UserStatus:
    svc = UserStatusService(db, user_id)
    return svc.set_status(status_in.status, status_in.source, status_in.expires_at)


@router.delete("")
def clear_status(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    svc = UserStatusService(db, user_id)
    svc.clear_status()
    return {"status": "cleared"}
