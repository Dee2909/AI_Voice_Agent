import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils import normalize_phone_number
from app.models.contact import (
    AliasSource,
    Contact,
    ContactAlias,
    NamingConvention,
    RelationshipSuggestion,
    RelationshipType,
    SuggestionStatus,
)
from app.schemas.contact import ContactIdentityResponse

logger = structlog.get_logger(__name__)

class ContactIdentityService:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def get_contact_by_phone(self, phone: str) -> Contact | None:
        normalized = normalize_phone_number(phone)
        return self.db.scalars(
            select(Contact)
            .where(Contact.user_id == self.user_id)
            .where(Contact.phone_number == normalized)
        ).first()

    def get_contact(self, contact_id: Any) -> Contact | None:
        return self.db.scalars(
            select(Contact)
            .where(Contact.user_id == self.user_id)
            .where(Contact.id == contact_id)
        ).first()

    def _resolve_relationship(self, contact: Contact) -> dict[str, Any]:
        """Resolves the relationship using the priority rules."""
        # 1 & 2: Explicit Relationship record
        rel_record = contact.relationship_record
        if rel_record:
            if rel_record.status == SuggestionStatus.CONFIRMED:
                return {
                    "relationship": rel_record.relationship_type.value,
                    "status": "CONFIRMED",
                    "confidence": rel_record.confidence,
                    "source": rel_record.source.value
                }
            # Fallback if UNCONFIRMED but explicitly set
            if rel_record.relationship_type != RelationshipType.UNKNOWN:
                 return {
                    "relationship": rel_record.relationship_type.value,
                    "status": "UNCONFIRMED",
                    "confidence": rel_record.confidence,
                    "source": rel_record.source.value
                }
                 
        # 3. Naming Conventions (e.g. "Arun Natpu" -> Natpu = FRIEND)
        conventions = self.db.scalars(
            select(NamingConvention)
            .where(NamingConvention.user_id == self.user_id)
            .where(NamingConvention.status == SuggestionStatus.CONFIRMED)
        ).all()
        
        if contact.saved_name:
            name_lower = contact.saved_name.lower()
            for conv in conventions:
                if conv.token.lower() in name_lower.split():
                    return {
                        "relationship": conv.meaning.value,
                        "status": "CONFIRMED",
                        "confidence": 1.0,
                        "source": "NAMING_CONVENTION"
                    }

        # 6. Suggestions
        suggestion = self.db.scalars(
            select(RelationshipSuggestion)
            .where(RelationshipSuggestion.contact_id == contact.id)
            .where(RelationshipSuggestion.status == SuggestionStatus.SUGGESTED)
            .order_by(RelationshipSuggestion.confidence.desc())
        ).first()
        
        if suggestion:
            return {
                "relationship": suggestion.suggested_relationship.value,
                "status": "SUGGESTED",
                "confidence": suggestion.confidence,
                "source": "SYSTEM"
            }

        # 7. UNKNOWN
        return {
            "relationship": RelationshipType.UNKNOWN.value,
            "status": "UNKNOWN",
            "confidence": 0.0,
            "source": "SYSTEM"
        }

    def resolve_identity(self, phone: str) -> ContactIdentityResponse:
        contact = self.get_contact_by_phone(phone)
        if not contact:
            return ContactIdentityResponse(
                contact_id=None,
                saved_name=None,
                real_name=None,
                aliases=[],
                relationship=RelationshipType.UNKNOWN.value,
                relationship_status="UNKNOWN",
                confidence=0.0,
                permissions=[]
            )

        aliases = self.db.scalars(
            select(ContactAlias)
            .where(ContactAlias.contact_id == contact.id)
            .where(ContactAlias.status == SuggestionStatus.CONFIRMED)
        ).all()
        
        rel_info = self._resolve_relationship(contact)
        
        return ContactIdentityResponse(
            contact_id=str(contact.id),
            saved_name=contact.saved_name, # type: ignore
            real_name=contact.real_name, # type: ignore
            aliases=[a.alias for a in aliases],
            relationship=rel_info["relationship"],
            relationship_status=rel_info["status"],
            confidence=rel_info["confidence"],
            permissions=["ANSWER", "SCREEN"] # mock permissions for now
        )

    def suggest_relationship(self, contact_id: uuid.UUID, suggested_name: str, suggested_relationship: RelationshipType, reason: str) -> RelationshipSuggestion:
        s = RelationshipSuggestion(
            contact_id=contact_id,
            suggested_name=suggested_name,
            suggested_relationship=suggested_relationship,
            confidence=0.8,
            reason=reason,
            status=SuggestionStatus.SUGGESTED
        )
        self.db.add(s)
        
        # also add as a suggested alias
        if suggested_name:
            a = ContactAlias(
                contact_id=contact_id,
                alias=suggested_name,
                alias_type="REAL_NAME",
                source=AliasSource.CALLER_IDENTIFICATION,
                status=SuggestionStatus.SUGGESTED
            )
            self.db.add(a)
        
        self.db.commit()
        self.db.refresh(s)
        return s
