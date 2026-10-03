import datetime
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class CallStatus(str, enum.Enum):
    INCOMING = "INCOMING"
    ACTIVE = "ACTIVE"
    SCREENING = "SCREENING"
    COMPLETED = "COMPLETED"
    HANDOFF = "HANDOFF"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class CallDirection(str, enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class SpeakerType(str, enum.Enum):
    CALLER = "CALLER"
    ASSISTANT = "ASSISTANT"
    USER = "USER"
    SYSTEM = "SYSTEM"


class UrgencyLevel(str, enum.Enum):
    NORMAL = "NORMAL"
    IMPORTANT = "IMPORTANT"
    POTENTIALLY_URGENT = "POTENTIALLY_URGENT"
    EMERGENCY_CLAIM = "EMERGENCY_CLAIM"


class ActionType(str, enum.Enum):
    CALLBACK = "CALLBACK"
    TASK = "TASK"
    FOLLOW_UP = "FOLLOW_UP"


class ActionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class Call(BaseModel):
    __tablename__ = "calls"

    user_id = Column(String, index=True, nullable=False)
    caller_phone = Column(String, index=True, nullable=False)
    callee_phone = Column(String, nullable=True)
    contact_id = Column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    status = Column(SQLEnum(CallStatus), default=CallStatus.INCOMING, nullable=False)
    direction = Column(SQLEnum(CallDirection), default=CallDirection.INBOUND, nullable=False)
    started_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)

    transcripts = relationship("CallTranscript", back_populates="call", cascade="all, delete-orphan")
    summary = relationship("CallSummary", uselist=False, back_populates="call", cascade="all, delete-orphan")
    actions = relationship("CallAction", back_populates="call", cascade="all, delete-orphan")
    urgency_events = relationship("UrgencyEvent", back_populates="call", cascade="all, delete-orphan")
    participants = relationship("CallParticipant", back_populates="call", cascade="all, delete-orphan")


class CallParticipant(BaseModel):
    __tablename__ = "call_participants"

    call_id = Column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    participant_type = Column(SQLEnum(SpeakerType), nullable=False)
    phone_number = Column(String, nullable=True)
    name = Column(String, nullable=True)

    call = relationship("Call", back_populates="participants")


class CallTranscript(BaseModel):
    __tablename__ = "call_transcripts"

    call_id = Column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    speaker = Column(SQLEnum(SpeakerType), nullable=False)
    text = Column(Text, nullable=False)
    language = Column(String, default="en", nullable=False)
    timestamp = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    call = relationship("Call", back_populates="transcripts")


class CallSummary(BaseModel):
    __tablename__ = "call_summaries"

    call_id = Column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True)
    caller_phone = Column(String, nullable=True)
    summary_text = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    urgency_level = Column(SQLEnum(UrgencyLevel), default=UrgencyLevel.NORMAL, nullable=False)
    relationship_type = Column(String, nullable=True)
    relationship_confidence = Column(Float, default=1.0)
    extra_metadata = Column(JSON, nullable=True)

    call = relationship("Call", back_populates="summary")


class CallAction(BaseModel):
    __tablename__ = "call_actions"

    call_id = Column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(SQLEnum(ActionType), default=ActionType.TASK, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(SQLEnum(ActionStatus), default=ActionStatus.PENDING, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)

    call = relationship("Call", back_populates="actions")


class UrgencyEvent(BaseModel):
    __tablename__ = "urgency_events"

    call_id = Column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    urgency_level = Column(SQLEnum(UrgencyLevel), nullable=False)
    reason = Column(Text, nullable=False)
    alert_dispatched = Column(Boolean, default=False, nullable=False)
    reviewed_by_user = Column(Boolean, default=False, nullable=False)

    call = relationship("Call", back_populates="urgency_events")


class Callback(BaseModel):
    __tablename__ = "callbacks"

    user_id = Column(String, index=True, nullable=False)
    contact_id = Column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    call_id = Column(ForeignKey("calls.id", ondelete="SET NULL"), nullable=True)
    phone_number = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    preferred_time = Column(String, nullable=True)
    status = Column(SQLEnum(ActionStatus), default=ActionStatus.PENDING, nullable=False)
