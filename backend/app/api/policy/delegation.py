import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.policy import Delegation
from app.schemas.policy import DelegationCreate, DelegationOut
from app.services.policy import DelegationService

router = APIRouter(prefix="/delegations", tags=["Delegation"])


@router.get("", response_model=list[DelegationOut])
def list_delegations(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> list[Delegation]:
    return db.query(Delegation).filter(Delegation.user_id == user_id).all()


@router.post("", response_model=DelegationOut)
def create_delegation(
    del_in: DelegationCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> Delegation:
    svc = DelegationService(db, user_id)
    rules = [{"relationship_type": r.relationship_type.value, "action": r.action.value} for r in del_in.rules]
    return svc.create_delegation(del_in.mode, del_in.source, del_in.expires_at, rules)


@router.get("/{id}", response_model=DelegationOut)
def get_delegation(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> Delegation:
    d = db.query(Delegation).filter(Delegation.id == id, Delegation.user_id == user_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Delegation not found")
    return d


@router.post("/{id}/cancel")
def cancel_delegation(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    svc = DelegationService(db, user_id)
    if not svc.cancel_delegation(id):
        raise HTTPException(status_code=404, detail="Delegation not found or already inactive")
    return {"status": "cancelled"}
