import enum
from typing import Any

from sqlalchemy import Column, Float, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum

from app.models.base import BaseModel


class PrivacyLevel(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SENSITIVE = "SENSITIVE"


class ConversationMemory(BaseModel):
    __tablename__ = "conversation_memory"

    user_id = Column(String, index=True, nullable=False)
    contact_id = Column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_key = Column(String, nullable=False, index=True)
    fact_value = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    privacy_level = Column(SQLEnum(PrivacyLevel), default=PrivacyLevel.PRIVATE, nullable=False)
    source = Column(String, default="CALL_CONVERSATION", nullable=False)
