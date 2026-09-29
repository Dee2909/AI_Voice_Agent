"""
Conversation Memory Service: stores and retrieves reusable contact-level facts.
Enforces selective memory retrieval and privacy filtering (Section 17).
"""

from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import ConversationMemory, PrivacyLevel
from app.models.security import ContactPermission
from app.security.privacy_firewall import PrivacyFirewall


class MemoryService:
    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def store_fact(
        self,
        contact_id: uuid.UUID,
        key: str,
        value: str,
        privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE,
        confidence: float = 1.0,
        source: str = "CALL_CONVERSATION",
    ) -> ConversationMemory:
        # Sanitize sensitive secrets before storing
        clean_value = PrivacyFirewall.redact_secrets(value)

        # Check existing fact with same key for this contact
        existing = self.db.scalars(
            select(ConversationMemory).where(
                ConversationMemory.user_id == self.user_id,
                ConversationMemory.contact_id == contact_id,
                ConversationMemory.fact_key == key,
            )
        ).first()

        if existing:
            existing.fact_value = clean_value
            existing.confidence = confidence
            existing.privacy_level = privacy_level
            existing.source = source
            self.db.commit()
            self.db.refresh(existing)
            return existing

        fact = ConversationMemory(
            user_id=self.user_id,
            contact_id=contact_id,
            fact_key=key,
            fact_value=clean_value,
            confidence=confidence,
            privacy_level=privacy_level,
            source=source,
        )
        self.db.add(fact)
        self.db.commit()
        self.db.refresh(fact)
        return fact

    def get_contact_context(
        self,
        contact_id: uuid.UUID,
        relationship: str = "UNKNOWN",
        permission: ContactPermission | None = None,
    ) -> dict[str, str]:
        """
        Retrieves relevant memory facts for a contact, strictly respecting
        privacy levels and contact permissions.
        """
        query = select(ConversationMemory).where(
            ConversationMemory.user_id == self.user_id,
            ConversationMemory.contact_id == contact_id,
        )

        # If relationship is OWNER, retrieve all
        if relationship == "OWNER":
            pass
        elif relationship == "UNKNOWN":
            query = query.where(ConversationMemory.privacy_level == PrivacyLevel.PUBLIC)
        else:
            # Do not retrieve SENSITIVE facts by default
            query = query.where(ConversationMemory.privacy_level != PrivacyLevel.SENSITIVE)

        facts = self.db.scalars(query).all()

        context_dict: dict[str, str] = {}
        for f in facts:
            context_dict[f.fact_key] = f.fact_value

        # Run through PrivacyFirewall
        sanitized = PrivacyFirewall.sanitize_context(
            context=context_dict,
            relationship_type=relationship,
            permission=permission,
            db=self.db,
            user_id=self.user_id,
        )
        return sanitized
