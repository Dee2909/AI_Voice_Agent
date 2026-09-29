import enum
from typing import Any
import datetime
import uuid

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped
from app.models.base import BaseModel
from app.models.contact import RelationshipType

class UserStatusType(enum.Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    MEETING = "MEETING"
    SLEEPING = "SLEEPING"
    DRIVING = "DRIVING"
    DND = "DND"
    AWAY = "AWAY"
    DELEGATED = "DELEGATED"

class StatusSource(enum.Enum):
    MANUAL = "MANUAL"
    DELEGATION = "DELEGATION"
    DEVICE = "DEVICE"
    CALENDAR = "CALENDAR"
    SYSTEM = "SYSTEM"
    INFERRED = "INFERRED"

class PolicyDecision(enum.Enum):
    ANSWER = "ANSWER"
    SCREEN = "SCREEN"
    NOTIFY = "NOTIFY"
    HANDOFF = "HANDOFF"
    ASK_IDENTITY = "ASK_IDENTITY"
    SAFE_FALLBACK = "SAFE_FALLBACK"
    REJECT = "REJECT"

class DelegationSource(enum.Enum):
    USER = "USER"
    ANDROID = "ANDROID"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
    AUTOMATION = "AUTOMATION"

class UserStatus(BaseModel):
    __tablename__ = "user_statuses"
    
    user_id = Column(String, nullable=False, index=True)
    status = Column(SQLEnum(UserStatusType), nullable=False)
    source = Column(SQLEnum(StatusSource), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

class Delegation(BaseModel):
    __tablename__ = "delegations"
    
    user_id = Column(String, nullable=False, index=True)
    mode = Column(SQLEnum(UserStatusType), nullable=False)
    active = Column(Boolean, default=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(SQLEnum(DelegationSource), nullable=False)
    
    rules: Mapped[list["DelegationRule"]] = relationship(
        "DelegationRule", back_populates="delegation", cascade="all, delete-orphan"
    )

class DelegationRule(BaseModel):
    __tablename__ = "delegation_rules"
    
    delegation_id = Column(ForeignKey("delegations.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(SQLEnum(RelationshipType), nullable=False)
    action = Column(SQLEnum(PolicyDecision), nullable=False)
    
    delegation: Mapped["Delegation"] = relationship("Delegation", back_populates="rules")

class UserPreference(BaseModel):
    __tablename__ = "user_preferences"
    
    user_id = Column(String, nullable=False, unique=True, index=True)
    allow_family_answer = Column(Boolean, default=True)
    allow_friend_screening = Column(Boolean, default=True)
    allow_unknown_screening = Column(Boolean, default=True)
    allow_work_screening = Column(Boolean, default=True)
    allow_human_handoff = Column(Boolean, default=True)
    allow_urgent_notifications = Column(Boolean, default=True)

class ContactPolicyRule(BaseModel):
    __tablename__ = "contact_policy_rules"
    
    user_id = Column(String, nullable=False, index=True)
    contact_id = Column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    action = Column(SQLEnum(PolicyDecision), nullable=False)
    # Stored as JSON list of statuses when this rule applies (e.g. ["MEETING", "BUSY"])
    # If empty or null, applies always
    conditions = Column(JSON, nullable=True)

class PolicyAuditLog(BaseModel):
    __tablename__ = "policy_audit_logs"
    
    event = Column(String, nullable=False)
    call_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    contact_id = Column(String, nullable=True)
    relationship = Column(String, nullable=True)
    user_status = Column(String, nullable=True)
    decision = Column(String, nullable=False)
    policy_source = Column(String, nullable=False)
