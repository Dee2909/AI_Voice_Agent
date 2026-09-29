"""
Conversation Memory API: manage contact facts and preferences with privacy boundaries.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.contact import Contact
from app.models.memory import PrivacyLevel
from app.services.memory import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


class FactCreateRequest(BaseModel):
    key: str = Field(..., description="Unique key for the fact, e.g. 'preferred_time'")
    value: str = Field(..., description="The factual detail")
    privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE
    confidence: float = 1.0


@router.get("/{contact_id}")
def get_contact_memory(
    contact_id: uuid.UUID,
    relationship: str = Query("OWNER", description="Relationship of the requester"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    contact = db.get(Contact, contact_id)
    if not contact or contact.user_id != user_id:
        raise HTTPException(status_code=404, detail="Contact not found")

    svc = MemoryService(db, user_id)
    context = svc.get_contact_context(contact_id, relationship=relationship)
    return {"contact_id": str(contact_id), "facts": context}


@router.post("/{contact_id}")
def store_contact_fact(
    contact_id: uuid.UUID,
    fact_in: FactCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    contact = db.get(Contact, contact_id)
    if not contact or contact.user_id != user_id:
        raise HTTPException(status_code=404, detail="Contact not found")

    svc = MemoryService(db, user_id)
    saved = svc.store_fact(
        contact_id=contact_id,
        key=fact_in.key,
        value=fact_in.value,
        privacy_level=fact_in.privacy_level,
        confidence=fact_in.confidence,
    )
    return {
        "id": str(saved.id),
        "contact_id": str(contact_id),
        "key": saved.fact_key,
        "value": saved.fact_value,
        "privacy_level": saved.privacy_level.value,
    }
