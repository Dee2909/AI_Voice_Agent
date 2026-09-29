import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.contacts import get_current_user_id
from app.core.database import get_db
from app.models.contact import (
    AliasSource,
    ContactRelationship,
    NamingConvention,
    RelationshipSuggestion,
    SuggestionStatus,
)
from app.schemas.contact import (
    NamingConventionBase,
    NamingConventionOut,
    RelationshipSuggestionOut,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="", tags=["relationships"])

@router.get("/relationships/suggestions", response_model=list[RelationshipSuggestionOut])
def get_suggestions(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Any:
    # Requires joining to ensure they belong to user
    from app.models.contact import Contact
    suggestions = db.query(RelationshipSuggestion).join(Contact).filter(
        Contact.user_id == user_id,
        RelationshipSuggestion.status == SuggestionStatus.SUGGESTED
    ).all()
    return suggestions

@router.post("/relationships/{suggestion_id}/confirm")
def confirm_relationship(suggestion_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Any:
    from app.models.contact import Contact
    s = db.query(RelationshipSuggestion).join(Contact).filter(
        Contact.user_id == user_id,
        RelationshipSuggestion.id == uuid.UUID(suggestion_id)
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
        
    s.status = SuggestionStatus.CONFIRMED
    
    # Update or create explicit relationship
    rel = db.query(ContactRelationship).filter(ContactRelationship.contact_id == s.contact_id).first()
    if not rel:
        rel = ContactRelationship(
            contact_id=s.contact_id,
            relationship_type=s.suggested_relationship,
            status=SuggestionStatus.CONFIRMED,
            confidence=1.0,
            source=AliasSource.USER
        )
        db.add(rel)
    else:
        rel.relationship_type = s.suggested_relationship
        rel.status = SuggestionStatus.CONFIRMED
        rel.source = AliasSource.USER
        
    db.commit()
    return {"status": "CONFIRMED"}

@router.post("/relationships/{suggestion_id}/reject")
def reject_relationship(suggestion_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Any:
    from app.models.contact import Contact
    s = db.query(RelationshipSuggestion).join(Contact).filter(
        Contact.user_id == user_id,
        RelationshipSuggestion.id == uuid.UUID(suggestion_id)
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    s.status = SuggestionStatus.REJECTED
    db.commit()
    return {"status": "REJECTED"}

@router.post("/relationships/{suggestion_id}/keep-unknown")
def keep_unknown_relationship(suggestion_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Any:
    from app.models.contact import Contact
    s = db.query(RelationshipSuggestion).join(Contact).filter(
        Contact.user_id == user_id,
        RelationshipSuggestion.id == uuid.UUID(suggestion_id)
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    s.status = SuggestionStatus.UNKNOWN
    db.commit()
    return {"status": "UNKNOWN"}

@router.post("/naming-conventions", response_model=NamingConventionOut)
def create_naming_convention(conv_in: NamingConventionBase, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)) -> Any:
    nc = NamingConvention(
        user_id=user_id,
        token=conv_in.token,
        meaning=conv_in.meaning,
        scope=conv_in.scope,
        status=conv_in.status,
        created_by=conv_in.created_by
    )
    db.add(nc)
    db.commit()
    db.refresh(nc)
    return nc
